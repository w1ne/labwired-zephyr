#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>

int main(void)
{
    const struct device *dev = DEVICE_DT_GET_ANY(bosch_bme280);

    if (!dev || !device_is_ready(dev)) {
        printk("BME280 not ready\n");
        return 0;
    }
    if (sensor_sample_fetch(dev) != 0) {
        printk("BME280 fetch failed\n");
        return 0;
    }
    struct sensor_value temp;
    sensor_channel_get(dev, SENSOR_CHAN_AMBIENT_TEMP, &temp);
    printk("BME280 temp: %d.%06d C\n", temp.val1, temp.val2);
    return 0;
}
