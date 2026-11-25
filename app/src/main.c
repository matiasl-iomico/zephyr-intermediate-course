#include <zephyr/kernel.h>
#include <zephyr/zbus/zbus.h>
#include "reading.h"

/* Listener: runs inside zbus_chan_pub(), so keep it short. */
static void on_reading(const struct zbus_channel *chan)
{
	const struct reading *m = zbus_chan_const_msg(chan);

	printk("[DISPLAY] seq=%u t=%u\n", m->seq, k_uptime_get_32());
}

ZBUS_LISTENER_DEFINE(screen_obs, on_reading);
ZBUS_SUBSCRIBER_DEFINE(log_obs, 4);

ZBUS_CHAN_DEFINE(temp_ch, struct reading, NULL, NULL,
		 ZBUS_OBSERVERS(screen_obs, log_obs), ZBUS_MSG_INIT(0));

/* Subscriber: slow work in its own thread. */
static void logger_fn(void *p1, void *p2, void *p3)
{
	const struct zbus_channel *chan;

	while (zbus_sub_wait(&log_obs, &chan, K_FOREVER) == 0) {
		struct reading m;

		zbus_chan_read(chan, &m, K_MSEC(10));
		k_msleep(50); /* pretend logging is slow */
		printk("[LOGGER] seq=%u t=%u\n", m.seq, k_uptime_get_32());
	}
}
K_THREAD_DEFINE(logger, 1024, logger_fn, NULL, NULL, NULL, 7, 0, 0);

static void publisher_fn(void *p1, void *p2, void *p3)
{
	for (uint32_t seq = 0;; seq++) {
		k_msleep(100);
		struct reading m = { .seq = seq, .temp_mc = 21000 + (seq % 10) * 100 };

		printk("[PUB] seq=%u t=%u\n", seq, k_uptime_get_32());
		zbus_chan_pub(&temp_ch, &m, K_MSEC(10));
	}
}
K_THREAD_DEFINE(publisher, 1024, publisher_fn, NULL, NULL, NULL, 5, 0, 0);
