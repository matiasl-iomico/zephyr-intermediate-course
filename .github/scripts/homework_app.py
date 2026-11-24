"""Helpers shared by the L1-L7 checkers: read C sources, build an app and run it.

C helpers work on comment-free text (strip_comments keeps offsets, so line numbers
stay right). Calls are split into top-level arguments, so checkers can read a
thread's priority from K_THREAD_DEFINE or k_thread_create.

build() runs `west build`; run_native() runs a native_sim binary for a fixed
simulated time (--stop_at) and returns everything it printed.
"""
import os
import re
import subprocess

SKIP_DIRS = {".git", ".github", "build", "twister-out", "deps", ".west"}
NUM_COOP_PRIORITIES = 16  # Zephyr's default CONFIG_NUM_COOP_PRIORITIES


# ---------------------------------------------------------------- reading C

def strip_comments(src, strings=False):
    """Blank out comments (and string contents when `strings`), keeping offsets intact."""
    def blank(m):
        text = m.group(0)
        if text.startswith('"') and not strings:
            return text
        return re.sub(r"[^\n]", " ", text)
    return re.sub(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"', blank, src, flags=re.S)


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def sources(root, app_dir, exts=(".c", ".h")):
    """{repo-relative path: text} of every C file under app_dir."""
    out = {}
    base = os.path.join(root, app_dir)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for f in sorted(filenames):
            if f.endswith(exts):
                path = os.path.join(dirpath, f)
                out[os.path.relpath(path, root)] = read(path) or ""
    return out


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def matching(text, open_pos):
    """Index just past the bracket that closes the one at open_pos."""
    pairs = {"(": ")", "{": "}", "[": "]"}
    close = pairs[text[open_pos]]
    depth, i = 1, open_pos + 1
    while i < len(text) and depth:
        if text[i] == text[open_pos]:
            depth += 1
        elif text[i] == close:
            depth -= 1
        i += 1
    return i


def split_args(text):
    """'a, f(b, c), d' -> ['a', 'f(b, c)', 'd'] (top-level commas only)."""
    args, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            args.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        args.append(cur.strip())
    return args


def calls(code, name):
    """[(args, line, start)] for every call or macro use `name(...)` in comment-free code."""
    out = []
    for m in re.finditer(r"\b%s\s*\(" % re.escape(name), code):
        open_pos = m.end() - 1
        end = matching(code, open_pos)
        out.append((split_args(code[open_pos + 1:end - 1]), line_of(code, m.start()), m.start()))
    return out


def function_body(code, name):
    """(body, line) of the C function definition `name(...) {`, or (None, None)."""
    for m in re.finditer(r"\b%s\s*\(" % re.escape(name), code):
        end = matching(code, m.end() - 1)
        rest = code[end:]
        brace = re.match(r"\s*\{", rest)
        if brace:
            start = end + brace.end() - 1
            return code[start + 1:matching(code, start) - 1], line_of(code, m.start())
    return None, None


def defines(code):
    """{NAME: value} for simple object-like #defines."""
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"^\s*#\s*define\s+(\w+)[ \t]+([^\n]+)", code, re.M)}


def eval_int(expr, defs, depth=0):
    """Integer value of a priority-like expression, or None: 7, -1, PRIO_A, K_PRIO_PREEMPT(3), K_PRIO_COOP(15)."""
    expr = (expr or "").strip()
    while expr.startswith("(") and expr.endswith(")") and matching(expr, 0) == len(expr):
        expr = expr[1:-1].strip()
    if re.fullmatch(r"[-+]?\s*\d+[uUlL]*", expr):
        return int(re.sub(r"[uUlL\s]", "", expr))
    m = re.fullmatch(r"K_PRIO_PREEMPT\s*\((.*)\)", expr)
    if m:
        return eval_int(m.group(1), defs, depth + 1)
    m = re.fullmatch(r"K_PRIO_COOP\s*\((.*)\)", expr)
    if m:
        v = eval_int(m.group(1), defs, depth + 1)
        return None if v is None else -(NUM_COOP_PRIORITIES - v)
    if expr in defs and depth < 5:
        return eval_int(defs[expr], defs, depth + 1)
    return None


def threads(files):
    """Every thread the app defines: [{name, entry, prio, options, path, line}].

    K_THREAD_DEFINE(name, stack, entry, p1, p2, p3, prio, options, delay) and
    k_thread_create(thread, stack, size, entry, p1, p2, p3, prio, options, delay).
    """
    all_defs = {}
    for text in files.values():
        all_defs.update(defines(strip_comments(text)))
    out = []
    for path, text in files.items():
        code = strip_comments(text)
        for args, line, _ in calls(code, "K_THREAD_DEFINE"):
            if len(args) >= 9:
                out.append({"name": args[0], "entry": args[2], "args": args[3:6], "prio": eval_int(args[6], all_defs),
                            "options": args[7], "path": path, "line": line})
        for args, line, _ in calls(code, "k_thread_create"):
            if len(args) >= 10:
                out.append({"name": args[0].lstrip("&"), "entry": args[3], "args": args[4:7],
                            "prio": eval_int(args[7], all_defs), "options": args[8], "path": path, "line": line})
    return out


def find_function(files, name):
    """(path, body, line) of the function `name` in any file, or (None, None, None)."""
    for path, text in files.items():
        body, line = function_body(strip_comments(text), name)
        if body is not None:
            return path, body, line
    return None, None, None


def kconfig(root, app_dir, name):
    """The value of CONFIG_<name> in the app's prj.conf (last assignment wins), or None."""
    text = read(os.path.join(root, app_dir, "prj.conf")) or ""
    value = None
    for m in re.finditer(r"^\s*CONFIG_%s\s*=\s*(\S+)" % re.escape(name), text, re.M):
        value = m.group(1).strip('"')
    return value


# ---------------------------------------------------------------- build and run

def build(source, build_dir, board="native_sim", cmake_args=(), timeout=900):
    """`west build` the app. Returns (ok, log tail)."""
    cmd = ["west", "build", "-p", "always", "-b", board, "-d", build_dir, source]
    if cmake_args:
        cmd += ["--"] + list(cmake_args)
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, "the build took too long"
    with open(os.path.join(os.path.dirname(os.path.abspath(build_dir)) or ".", "build.log"), "a") as f:
        f.write(p.stdout)
    return p.returncode == 0, p.stdout[-3000:]


def build_error(log):
    """The first compiler or CMake error line of a build log, for a short message."""
    for pat in (r"^.*\berror: .*$", r"^CMake Error.*$", r"^.*undefined reference.*$", r"^FAILED: .*$"):
        m = re.search(pat, log, re.M)
        if m:
            return m.group(0).strip()[:300]
    return "the build failed"


def config_value(build_dir, name):
    text = read(os.path.join(build_dir, "zephyr", ".config")) or ""
    m = re.search(r"^CONFIG_%s=(.*)$" % re.escape(name), text, re.M)
    return m.group(1).strip('"') if m else None


def run_native(build_dir, seconds, timeout=120):
    """Run build_dir's native_sim binary for `seconds` of simulated time. Returns (output, exit code or None)."""
    exe = os.path.join(build_dir, "zephyr", "zephyr.exe")
    cmd = [exe, f"--stop_at={seconds}"]
    # A console on the native UART goes to its own pseudo-terminal unless it is moved to stdout.
    if config_value(build_dir, "UART_NATIVE_PTY_0_ON_OWN_PTY") == "y":
        cmd.append("--uart_stdinout")
    try:
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, errors="replace", timeout=timeout, cwd=build_dir)
        return p.stdout, p.returncode
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode(errors="replace")
        return out, None


def run_twister(test_dir, outdir, platform="native_sim", timeout=900):
    """Run a course test with twister. Returns ({case name: status}, problem or None)."""
    import json
    cmd = ["west", "twister", "-T", test_dir, "-p", platform, "--outdir", outdir, "--inline-logs",
           "--disable-warnings-as-errors"]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {}, "the course's test took too long"
    try:
        with open(os.path.join(outdir, "twister.json")) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}, "twister produced no results"
    cases, problem = {}, None
    for suite in data.get("testsuites", []):
        ran = [c for c in suite.get("testcases") or [] if c.get("status") not in ("blocked", "skipped")]
        if suite.get("status") in ("error", "failed") and not ran:
            problem = (suite.get("reason") or "the test didn't build")[:300]
        for c in suite.get("testcases") or []:
            name = c.get("identifier", "").rsplit(".", 1)[-1]
            cases[name if name.startswith("test_") else f"test_{name}"] = c.get("status")
    return cases, problem


def tagged(output, tag):
    """Lines that contain `[TAG]`, with their index in the output (LOG_* prefixes are fine)."""
    return [(i, line) for i, line in enumerate(output.splitlines()) if f"[{tag}]" in line]


def field(line, name):
    """Integer value of `name=<n>` in a log line, or None."""
    m = re.search(r"\b%s\s*=\s*(-?\d+)" % re.escape(name), line)
    return int(m.group(1)) if m else None
