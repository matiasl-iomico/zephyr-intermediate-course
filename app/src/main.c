#include <zephyr/kernel.h>
#include <zephyr/task_wdt/task_wdt.h>

#define Q_LEN       8
#define WARN_PCT    75
#define WDT_MS      1000
#define STALL_SEQ   20

struct sample {
	uint32_t seq;
};
K_MSGQ_DEFINE(data_q, sizeof(struct sample), Q_LEN, 4);

static void wdt_cb(int channel_id, void *user_data)
{
	printk("[WDT] consumer stalled t=%u\n", k_uptime_get_32());
}

static void producer_fn(void *p1, void *p2, void *p3)
{
	for (uint32_t seq = 0;; seq++) {
		struct sample s = { .seq = seq };

		if (k_msgq_put(&data_q, &s, K_NO_WAIT) != 0) {
			printk("[PROD] queue full, dropped seq=%u t=%u\n", seq, k_uptime_get_32());
		}
		k_msleep(50);
	}
}

static void consumer_fn(void *p1, void *p2, void *p3)
{
	task_wdt_init(NULL);
	int wdt_id = task_wdt_add(WDT_MS, wdt_cb, NULL);
	struct sample s;

	while (1) {
		k_msgq_get(&data_q, &s, K_FOREVER);
		if (s.seq == STALL_SEQ) {
			printk("[CONS] simulating stall t=%u\n", k_uptime_get_32());
			k_msleep(5000);
		}
		printk("[CONS] seq=%u t=%u\n", s.seq, k_uptime_get_32());
		task_wdt_feed(wdt_id); /* only after real progress */
	}
}

static void health_fn(void *p1, void *p2, void *p3)
{
	while (1) {
		uint32_t used = k_msgq_num_used_get(&data_q);

		printk("[HEALTH] %soccupancy=%u/%u t=%u\n", used * 100 >= WARN_PCT * Q_LEN ? "WARN " : "",
		       used, Q_LEN, k_uptime_get_32());
		k_msleep(100);
	}
}

K_THREAD_DEFINE(prod, 1024, producer_fn, NULL, NULL, NULL, 5, 0, 0);
K_THREAD_DEFINE(cons, 1024, consumer_fn, NULL, NULL, NULL, 6, 0, 0);
K_THREAD_DEFINE(health, 1024, health_fn, NULL, NULL, NULL, 4, 0, 0);
