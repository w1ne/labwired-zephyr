# zephyr-bme280 — verifiably runs

A Zephyr application for `nrf52840dk` that reads a BME280 over I2C, with a ztest
that asserts a plausible reading. CI builds it, boots the **real ELF** in the
[LabWired](https://github.com/w1ne/labwired) simulator on a github-hosted
runner, and scores the ztest — no hardware, no local setup.

![ci](https://github.com/<owner>/zephyr-bme280/actions/workflows/ci.yml/badge.svg)

- `application/` — the Zephyr app + the `app.bme280_read` ztest
- `application/labwired/chips/nrf52840.yaml` — vendored LabWired SoC model
- `.github/workflows/ci.yml` — build (`action-zephyr-setup`) → download the
  `labwired` binary → twister custom backend → LabWired → ztest score
