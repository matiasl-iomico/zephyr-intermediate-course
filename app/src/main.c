#include <zephyr/kernel.h>

#define STACK 1024

/* Same body for the three preemptible threads. */
static void worker(void *name, void *period_ms, void *unused)
{
	ARG_UNUSED(unused);

	for (uint32_t n = 0;; n++) {
		printk("[%s] tick=%u t=%u\n", (const char *)name, n, k_uptime_get_32());
		k_msleep((int)(intptr_t)period_ms);
	}
}

K_THREAD_DEFINE(t7, STACK, worker, "T7", (void *)150, NULL, 7, 0, 0);
K_THREAD_DEFINE(t5, STACK, worker, "T5", (void *)200, NULL, 5, 0, 0);
K_THREAD_DEFINE(t3, STACK, worker, "T3", (void *)100, NULL, 3, 0, 0);

/* Cooperative thread: 5 busy iterations, then k_yield(). */
static void coop_fn(void *p1, void *p2, void *p3)
{
	for (int i = 0; i < 5; i++) {
		printk("[COOP] iter=%d t=%u\n", i, k_uptime_get_32());
		k_busy_wait(10000); /* 10 ms of busy work */
	}
	printk("[COOP] yield t=%u\n", k_uptime_get_32());
	k_yield();
	printk("[COOP] done t=%u\n", k_uptime_get_32());
}

K_THREAD_DEFINE(coop, STACK, coop_fn, NULL, NULL, NULL, -1, 0, 500);
