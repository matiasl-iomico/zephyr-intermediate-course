#include <zephyr/kernel.h>
#include <zephyr/zbus/zbus.h>
#include "sensor_msg.h"

/* Listener: runs inside zbus_chan_pub(), so keep it short. */
static void display_cb(const struct zbus_channel *chan)
{
	const struct sensor_msg *m = zbus_chan_const_msg(chan);

	printk("[DISPLAY] seq=%u t=%u\n", m->seq, k_uptime_get_32());
k_msleep(20);
}

ZBUS_LISTENER_DEFINE(display_lis, display_cb);
ZBUS_SUBSCRIBER_DEFINE(logger_sub, 4);

ZBUS_CHAN_DEFINE(sensor_chan, struct sensor_msg, NULL, NULL,
		 ZBUS_OBSERVERS(display_lis, logger_sub), ZBUS_MSG_INIT(0));

/* Subscriber: slow work in its own thread. */
static void logger_fn(void *p1, void *p2, void *p3)
{
	const struct zbus_channel *chan;

	while (zbus_sub_wait(&logger_sub, &chan, K_FOREVER) == 0) {
		struct sensor_msg m;

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
		struct sensor_msg m = { .seq = seq, .temp_mc = 21000 + (seq % 10) * 100 };

		printk("[PUB] seq=%u t=%u\n", seq, k_uptime_get_32());
		zbus_chan_pub(&sensor_chan, &m, K_MSEC(10));
	}
}
K_THREAD_DEFINE(publisher, 1024, publisher_fn, NULL, NULL, NULL, 5, 0, 0);
