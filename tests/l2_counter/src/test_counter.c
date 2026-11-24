/*
 * Course test for l2-task1 (see TASKS.md, L2). Two threads of the same priority
 * call counter_increment() N times each; with the mutex the total is exact.
 */
#include <zephyr/kernel.h>
#include <zephyr/ztest.h>

#include "counter.h"

#define N 100000
#define STACK 1024

K_THREAD_STACK_ARRAY_DEFINE(stacks, 2, STACK);
static struct k_thread threads[2];

static void worker(void *p1, void *p2, void *p3)
{
	ARG_UNUSED(p1);
	ARG_UNUSED(p2);
	ARG_UNUSED(p3);

	for (int i = 0; i < N; i++) {
		counter_increment();
	}
}

ZTEST(l2_counter, test_reset_clears_counter)
{
	counter_increment();
	counter_reset();
	zassert_equal(counter_get(), 0, "counter_get() must be 0 after counter_reset(), got %d",
		      counter_get());
}

ZTEST(l2_counter, test_two_threads_mutex_total)
{
	counter_reset();
	for (int i = 0; i < 2; i++) {
		k_thread_create(&threads[i], stacks[i], K_THREAD_STACK_SIZEOF(stacks[i]), worker,
				NULL, NULL, NULL, K_PRIO_PREEMPT(5), 0, K_NO_WAIT);
	}
	for (int i = 0; i < 2; i++) {
		k_thread_join(&threads[i], K_FOREVER);
	}
	zassert_equal(counter_get(), 2 * N, "two threads x %d counter_increment() gave %d", N,
		      counter_get());
}

ZTEST_SUITE(l2_counter, NULL, NULL, NULL, NULL, NULL);
