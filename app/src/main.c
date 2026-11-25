#include <zephyr/kernel.h>
#include "counter.h"

#define N 100000

K_THREAD_STACK_ARRAY_DEFINE(stacks, 2, 1024);
static struct k_thread threads[2];

static void worker(void *use_mutex, void *p2, void *p3)
{
	for (int i = 0; i < N; i++) {
		if (use_mutex) {
			counter_increment();
		} else {
			counter_increment_unsafe();
		}
	}
}

static void run(const char *mode, bool use_mutex)
{
	counter_reset();
	for (int i = 0; i < 2; i++) {
		k_thread_create(&threads[i], stacks[i], K_THREAD_STACK_SIZEOF(stacks[i]),
				worker, (void *)use_mutex, NULL, NULL, 5, 0, K_NO_WAIT);
	}
	/* Read the result only after both workers finished. */
	for (int i = 0; i < 2; i++) {
		k_thread_join(&threads[i], K_FOREVER);
	}
	printk("[RESULT] mode=%s total=%d expected=%d\n", mode, counter_get(), 2 * N);
}

int main(void)
{
	run("unsafe", false);
	run("mutex", true);
	return 0;
}
