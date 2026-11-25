#ifndef SENSOR_MSG_H
#define SENSOR_MSG_H

#include <zephyr/zbus/zbus.h>

struct reading {
	uint32_t seq;
	int32_t temp_mc; /* milli-degrees C */
};

ZBUS_CHAN_DECLARE(temp_ch);

#endif
