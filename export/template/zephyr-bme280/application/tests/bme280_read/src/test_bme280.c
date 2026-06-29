#include <zephyr/ztest.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>

ZTEST_SUITE(bme280_read, NULL, NULL, NULL, NULL, NULL);

ZTEST(bme280_read, test_device_ready)
{
    const struct device *dev = DEVICE_DT_GET_ANY(bosch_bme280);
    zassert_not_null(dev, "no bosch,bme280 node in devicetree");
    zassert_true(device_is_ready(dev), "BME280 device not ready");
}

ZTEST(bme280_read, test_fetch_temperature_in_range)
{
    const struct device *dev = DEVICE_DT_GET_ANY(bosch_bme280);
    zassert_true(device_is_ready(dev), "BME280 device not ready");
    zassert_ok(sensor_sample_fetch(dev), "sensor_sample_fetch failed");

    struct sensor_value temp;
    zassert_ok(sensor_channel_get(dev, SENSOR_CHAN_AMBIENT_TEMP, &temp),
               "sensor_channel_get(TEMP) failed");
    /* BME280 operating range is -40..85 C; assert a plausible non-extreme read
       so a dead/zero model would fail rather than pass. */
    zassert_true(temp.val1 > -40 && temp.val1 < 85,
                 "temperature %d C out of plausible range", temp.val1);
}
