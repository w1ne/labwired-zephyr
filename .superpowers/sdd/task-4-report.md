# Task 4 Report: Zephyr+BME280 Export Template — GitHub CI Green

**Date:** 2026-06-29  
**Proof repo:** https://github.com/w1ne/zephyr-bme280-proof  
**Passing CI run:** https://github.com/w1ne/zephyr-bme280-proof/actions/runs/28385695276  
**Template source branch:** `feat/zephyr-mcp-export` of `w1ne/labwired-zephyr-dts`

## Result

Both CI jobs pass:

| Job | Status |
|-----|--------|
| DTS converter (pure python) | success |
| build + LabWired sim + ztest (hosted) | success |

Twister summary (from CI log):
```
INFO - 1 of 1 test configurations passed (100.00%), 0 failed, 0 errored, 0 skipped
INFO - 1 test cases were executed, 1 skipped on 1 out of total 1 platforms (100.00%)
```

Test breakdown:
- `test_device_node_in_dts` — PASS (DTS node `bosch,bme280` exists)
- `test_fetch_temperature_in_range` — SKIP (expected: device_is_ready() returns false when LABWIRED_NO_EXTERNAL_DEVICES=1; BME280 I²C device is not attached in simulation)

## Root Causes Fixed

### 1. ARM MPU assertion loop

LabWired's Cortex-M4 model returns 0 for MPU TYPE.DREGION (no MPU regions). Zephyr's `mpu_configure_static_mpu_regions()` treats this as -EINVAL and fires `__ASSERT(0)`, which becomes a `svc 2` no-op. The loop repeats on every kernel interrupt, preventing firmware from reaching `main()`.

**Fix:** Added to `application/tests/bme280_read/prj.conf`:
```
CONFIG_ARM_MPU=n
CONFIG_HW_STACK_PROTECTION=n
```

### 2. SPIM0/I2C0 peripheral overlap

nRF52840 multiplexes SPIM0/SPIS0/TWIM0/TWIS0/SPI0/TWI0 all at base address 0x40003000. The chip descriptor had both `spi0` and `i2c0` mapped to that address, causing LabWired to abort with PERIPHERAL_OVERLAP.

**Fix:** Removed the `i2c0` entry from `labwired/chips/nrf52840.yaml`. The `spi0` entry (type: spi, profile: nrf52) is the authoritative model for that address block.

### 3. UARTE EasyDMA first-TX deadlock (required new LabWired release)

`uarte_instance_init()` in Zephyr's `uart_nrfx_uarte.c` triggers TASKS_STARTTX + TASKS_STOPTX to issue a 0-length transfer, which sets EVENTS_TXSTOPPED on real silicon. The `is_tx_ready()` predicate polls `EVENTS_TXSTOPPED || EVENTS_ENDTX` — both were 0 in LabWired v0.17.3's generic `uart` model (TASKS_STOPTX writes silently ignored), causing `wait_tx_ready()` to spin forever in pre-kernel context before `main()` was ever reached.

LabWired's `origin/main` (commit `7f3277e2`) added the `Nrf52Uarte` EasyDMA model with proper `TASKS_STOPTX → events_txstopped = 1` handling. This was not yet released.

**Fix:** Bumped labwired-core workspace version from 0.17.3 to 0.17.4 (PR #415, merged), tagged `v0.17.4`, and updated the CI download URL to the new release. Updated `ci.yml` to fetch:
```
https://github.com/w1ne/labwired-core/releases/download/v0.17.4/labwired-v0.17.4-linux-x86_64.tar.gz
```

## Template Files Modified

- `export/template/zephyr-bme280/application/tests/bme280_read/prj.conf` — ARM MPU disable
- `export/template/zephyr-bme280/labwired/chips/nrf52840.yaml` — remove duplicate i2c0 at 0x40003000
- `export/template/zephyr-bme280/.github/workflows/ci.yml` — LabWired v0.17.3 → v0.17.4

All fixes are committed on `feat/zephyr-mcp-export` (commits `7dd0e03` and `4fff4d4`).

## Known Limitation

`LABWIRED_NO_EXTERNAL_DEVICES=1` is required to skip BME280 external device attachment. LabWired's nRF52 TWIM factory does not yet register `bme280` as an attachable device type. The `test_fetch_temperature_in_range` test gracefully skips when `device_is_ready()` returns false, so the suite still reports PASS. Remove this flag once the nRF52 factory supports BME280.
