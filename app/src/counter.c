#include <zephyr/kernel.h>
#include "counter.h"

static int counter;
K_MUTEX_DEFINE(counter_lock);

/* Read-modify-write with no protection: updates can be lost. */
void counter_increment_unsafe(void)
{
	int value = counter;

	value++;
	counter = value;
}

/* The whole update under the same mutex in every caller. */
void counter_increment(void)
{
	k_mutex_lock(&counter_lock, K_FOREVER);
	counter++;
	k_mutex_unlock(&counter_lock);
}

int counter_get(void)
{
	return counter;
}

void counter_reset(void)
{
	counter = 0;
}
