#include <zephyr/ztest.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>

ZTEST_SUITE(bme280_read, NULL, NULL, NULL, NULL, NULL);

/* Prove the DTS overlay was applied: the bosch,bme280 node must exist in the
   final devicetree, regardless of whether the simulator models the device.
   This assertion fails if the overlay is missing or the build configuration is
   wrong — making the test load-bearing for the full DTS -> build pipeline. */
ZTEST(bme280_read, test_device_node_in_dts)
{
    const struct device *dev = DEVICE_DT_GET_ANY(bosch_bme280);
    zassert_not_null(dev, "no bosch,bme280 node in devicetree: DTS overlay not applied");
    TC_PRINT("BME280 DTS node found; device_is_ready: %d\n", device_is_ready(dev));
}

/* Read temperature from the live BME280 model.  With i2c0 modeled as
   nrf52840_serial the Nrf52SerialInstance mux is instantiated and the BME280
   is attached, so device_is_ready() MUST return true.  A silent skip here
   would mask the very regression this test was introduced to catch. */
ZTEST(bme280_read, test_fetch_temperature_in_range)
{
    const struct device *dev = DEVICE_DT_GET_ANY(bosch_bme280);
    zassert_not_null(dev, "BME280 device node not found in DTS");
    zassert_true(device_is_ready(dev),
                 "BME280 must be ready now that i2c0 is modeled as nrf52840_serial");
    zassert_ok(sensor_sample_fetch(dev), "sensor_sample_fetch failed");

    struct sensor_value temp;
    zassert_ok(sensor_channel_get(dev, SENSOR_CHAN_AMBIENT_TEMP, &temp),
               "sensor_channel_get(TEMP) failed");
    /* A live BME280 read is never exactly zero across both fields; reject a
       dead/zero model that reports fetch success but returns no data. */
    zassert_false(temp.val1 == 0 && temp.val2 == 0, "dead/zero temperature read");
    /* BME280 operating range is -40..85 C; assert a plausible non-extreme read
       so a dead/zero model would fail rather than pass. */
    zassert_true(temp.val1 > -40 && temp.val1 < 85,
                 "temperature %d C out of plausible range", temp.val1);
}
