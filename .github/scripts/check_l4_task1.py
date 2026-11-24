#!/usr/bin/env python3
"""Check l4-task1: a zbus channel with a listener and a subscriber (see TASKS.md, L4).

Static: CONFIG_ZBUS=y; app/src/sensor_msg.h holds `struct sensor_msg` and
ZBUS_CHAN_DECLARE(sensor_chan); the channel is defined once; the listener
`display_lis` and the subscriber `logger_sub` (or a message subscriber) observe it;
the listener callback doesn't block or publish.
Run: builds app/ for native_sim, runs it for 2 s and reads the fixed log lines
  [PUB] seq=<n> t=<ms>   [DISPLAY] seq=<n> t=<ms>   [LOGGER] seq=<n> t=<ms>
Samples are published about every 100 ms, the display shows each one in the same
instant (the listener runs inside the publish), and the logger runs later.

    python3 .github/scripts/check_l4_task1.py --root zephyr-course --json result.json

Exit code 0 when approved, 1 otherwise.
"""
import argparse
import os
import re
import statistics
import sys

from homework_report import Report
import homework_app as app

APP = "app"
HEADER = f"{APP}/src/sensor_msg.h"
SECONDS = 2
BLOCKING = ("k_msleep", "k_sleep", "k_usleep", "k_busy_wait", "zbus_chan_pub", "zbus_chan_read", "k_yield")


def static_checks(report, root):
    files = app.sources(root, APP)
    if not report.check(files, f"`{APP}/` has the app's sources", fix=f"Put the app in `{APP}/` (TASKS.md, L4)."):
        return False
    ok = report.check(app.kconfig(root, APP, "ZBUS") == "y", "`CONFIG_ZBUS=y`", path=f"{APP}/prj.conf",
                      fix=f"Enable zbus: add `CONFIG_ZBUS=y` to `{APP}/prj.conf`.")
    header = app.strip_comments(files.get(HEADER, ""))
    ok &= report.check(re.search(r"\bstruct\s+sensor_msg\s*\{", header), "`struct sensor_msg` is in `sensor_msg.h`",
                       path=HEADER, fix=f"Define `struct sensor_msg` in `{HEADER}`, shared by every module.")
    ok &= report.check(re.search(r"\bZBUS_CHAN_DECLARE\s*\([^)]*\bsensor_chan\b", header),
                       "`sensor_chan` is declared in `sensor_msg.h`", path=HEADER,
                       fix=f"Declare the channel in `{HEADER}` with `ZBUS_CHAN_DECLARE(sensor_chan);`.")
    code = {p: app.strip_comments(t) for p, t in files.items() if p.endswith(".c")}
    chan = [(p, a, ln) for p, c in code.items() for a, ln, _ in app.calls(c, "ZBUS_CHAN_DEFINE") if a and a[0] == "sensor_chan"]
    ok &= report.check(len(chan) == 1, "`sensor_chan` is defined once", path=chan[0][0] if chan else None,
                       fix="Define the channel once, in a `.c` file: `ZBUS_CHAN_DEFINE(sensor_chan, struct sensor_msg, "
                           "...)`." if not chan else "Define `sensor_chan` in one `.c` file only; the others include "
                           "`sensor_msg.h`.")
    if chan:
        report.check(chan[0][1][1:2] == ["struct sensor_msg"], "`sensor_chan` carries `struct sensor_msg`",
                     path=chan[0][0], line=chan[0][2],
                     fix="Make `struct sensor_msg` the channel's message type in `ZBUS_CHAN_DEFINE`.")
    listener = [(p, a, ln) for p, c in code.items() for a, ln, _ in app.calls(c, "ZBUS_LISTENER_DEFINE")
                if a and a[0] == "display_lis"]
    ok &= report.check(listener, "`display_lis` is a listener",
                       fix="Define the display observer as a listener: `ZBUS_LISTENER_DEFINE(display_lis, display_cb);`.")
    msg_sub = any(a and a[0] == "logger_sub" for c in code.values() for a, _, _ in app.calls(c, "ZBUS_MSG_SUBSCRIBER_DEFINE"))
    sub = msg_sub or any(a and a[0] == "logger_sub" for c in code.values() for a, _, _ in app.calls(c, "ZBUS_SUBSCRIBER_DEFINE"))
    ok &= report.check(sub, "`logger_sub` is a subscriber",
                       fix="Define the logger observer as a subscriber: `ZBUS_SUBSCRIBER_DEFINE(logger_sub, 4);`.")
    if msg_sub:
        ok &= report.check(app.kconfig(root, APP, "ZBUS_MSG_SUBSCRIBER") == "y", "`CONFIG_ZBUS_MSG_SUBSCRIBER=y`",
                           path=f"{APP}/prj.conf",
                           fix="A message subscriber needs `CONFIG_ZBUS_MSG_SUBSCRIBER=y` in `prj.conf`.")
    all_code = "\n".join(code.values())
    for obs in ("display_lis", "logger_sub"):
        in_chan = chan and re.search(r"\b%s\b" % obs, ", ".join(chan[0][1][2:]))
        added = re.search(r"\bZBUS_CHAN_ADD_OBS\s*\(\s*sensor_chan\s*,\s*%s\b|\bzbus_chan_add_obs\s*\(\s*&\s*sensor_chan\s*,"
                          r"\s*&\s*%s\b" % (obs, obs), all_code)
        ok &= report.check(in_chan or added, f"`{obs}` observes `sensor_chan`", path=chan[0][0] if chan else None,
                           fix=f"Add `{obs}` to the channel's observers: `ZBUS_OBSERVERS(display_lis, logger_sub)` in "
                               "`ZBUS_CHAN_DEFINE`.")
    if listener:
        p, args, ln = listener[0]
        cb = args[1] if len(args) > 1 else ""
        path, body, line = app.find_function(files, cb)
        blocking = [b for b in BLOCKING if body and re.search(r"\b%s\s*\(" % b, body)]
        ok &= report.check(body is not None and not blocking, "the listener callback is short",
                           path=path or p, line=line or ln,
                           fix=f"Keep `{cb}()` short: it runs inside the publisher's `zbus_chan_pub()`. Move "
                               f"{', '.join(f'`{b}()`' for b in blocking) or 'slow work'} to the subscriber's thread.")
    return bool(ok)


def entries(out, tag):
    return [(i, app.field(ln, "seq"), app.field(ln, "t")) for i, ln in app.tagged(out, tag)]


def run_checks(report, root, work):
    build_dir = os.path.join(work, "build")
    ok, log = app.build(os.path.join(root, APP), build_dir)
    if not report.check(ok, "the app builds for `native_sim`",
                        fix=f"Fix the build: {app.build_error(log)}. Try `west build -b native_sim {APP}`."):
        return
    out, _ = app.run_native(build_dir, SECONDS)
    pub, disp, logger = entries(out, "PUB"), entries(out, "DISPLAY"), entries(out, "LOGGER")
    for tag, items in (("PUB", pub), ("DISPLAY", disp), ("LOGGER", logger)):
        if not report.check(items and all(s is not None and t is not None for _, s, t in items),
                            f"`[{tag}] seq=<n> t=<ms>` lines are printed",
                            fix=f"Print `[{tag}] seq=<n> t=<ms>` (TASKS.md, L4); `t` is `k_uptime_get_32()`."):
            return
    gaps = [b[2] - a[2] for a, b in zip(pub, pub[1:])]
    period = statistics.median(gaps) if gaps else 0
    report.check(len(pub) >= SECONDS * 1000 // 120 and 90 <= period <= 120,
                 f"a sample is published about every 100 ms ({len(pub)} in {SECONDS} s)",
                 fix=f"Publish a sample every 100 ms; the run published {len(pub)} in {SECONDS} s"
                     + (f", {period:.0f} ms apart." if gaps else "."))
    shown = {s: t for _, s, t in disp}
    missing = [s for _, s, t in pub if s not in shown or not 0 <= shown[s] - t <= 1]
    report.check(not missing, "the display shows each sample as it is published",
                 fix=f"Sample {missing[0] if missing else ''} has no `[DISPLAY]` line in the same instant as its "
                     "`[PUB]`. The listener runs inside the publish: log `[DISPLAY]` from its callback.")
    pub_t = {s: t for _, s, t in pub}
    wrong = [s for _, s, t in logger if s not in pub_t or t < pub_t[s]]
    report.check(not wrong, "the logger handles published samples after they are published",
                 fix="`[LOGGER]` printed a sample before it was published or one that never was. Read the channel "
                     "in the subscriber's thread after `zbus_sub_wait()` returns.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repository root (default: current directory)")
    ap.add_argument("--work", default=".", help="folder for the build and its log (default: current directory)")
    ap.add_argument("--no-run", action="store_true", help="only read the sources")
    ap.add_argument("--json", help="write the result JSON here")
    args = ap.parse_args()
    report = Report("l4-task1", "zbus listener and subscriber")
    if static_checks(report, os.path.abspath(args.root)) and not args.no_run:
        run_checks(report, os.path.abspath(args.root), os.path.abspath(args.work))
    return report.finish(args.json)


if __name__ == "__main__":
    sys.exit(main())
