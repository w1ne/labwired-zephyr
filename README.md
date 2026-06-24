# labwired-zephyr

Run Zephyr applications in the [LabWired](https://github.com/w1ne/labwired)
deterministic simulator straight from your west workflow — build for a real
board, then boot the firmware in the sim and watch the UART console, no hardware
attached.

```
west build -b nrf52840dk/nrf52840 samples/hello_world
west simulate
```

```
*** Booting Zephyr OS ...
Hello World! nrf52840dk/nrf52840
```

LabWired runs the **unmodified** ELF (the same binary you would flash), so the
kernel, drivers, and your code execute against silicon-accurate peripheral
models. Exit code and console output make it usable as a CI smoke test.

## How it works

`west simulate` resolves the build's board target to a LabWired *system
manifest* via [`boards.map`](boards.map), then runs:

```
labwired --firmware build/zephyr/zephyr.elf --system <mapped>.yaml --max-steps N
```

streaming the console and propagating the exit code. The same core also backs a
`ZephyrBinaryRunner` (`west flash -r labwired`) for setups that register
out-of-tree runners; `west simulate` is the zero-configuration path and is
recommended.

## Setup

Add this module to your west manifest and register its command:

```yaml
# west.yml
manifest:
  projects:
    - name: labwired-zephyr
      url: https://github.com/w1ne/labwired-zephyr
      revision: main
      west-commands: west-commands.yml
```

`west update`, then point the command at your LabWired install:

- `--labwired-bin` / `$LABWIRED_BIN` — the `labwired` binary (default: on `PATH`).
- `--systems-dir` / `$LABWIRED_SYSTEMS_DIR` — the system manifests
  (`<labwired>/configs/systems`). Or pass `--system <path>` directly.

### Options

| Flag | Meaning |
| --- | --- |
| `-d, --build-dir` | application build directory (default `build`) |
| `--labwired-bin` | path to the `labwired` binary |
| `--systems-dir` | directory of system manifests |
| `--system` | a system manifest path, overriding the board map |
| `--board-map` | board → system map (default: this repo's `boards.map`) |
| `--max-steps` | step budget before the run is stopped (default 5,000,000) |
| `--timeout` | wall-clock timeout in seconds |
| `-- ARG…` | extra args passed through to `labwired` (e.g. `--trace`) |

## Supported Zephyr targets

Boards are listed in [`boards.map`](boards.map). Add one line — the qualified
Zephyr board target and the LabWired system manifest it runs against — to add a
board. The map is intentionally board-specific, not just CPU-core-specific: a
Zephyr image still touches SoC-specific memory-mapped peripherals during boot,
so a Cortex-M4 binary built for STM32 cannot safely run on an nRF52 manifest just
because both use a Cortex-M4 core.

| Zephyr board | LabWired system |
| --- | --- |
| `black_f407ve` | `nucleo-f407.yaml` |
| `black_f407zg_pro` | `nucleo-f407.yaml` |
| `blackpill_f401cc` | `stm32f401cdu6-blackpill.yaml` |
| `blackpill_f401ce` | `stm32f401cdu6-blackpill.yaml` |
| `esp32_devkitc_wroom/esp32/procpu` | `esp32-wroom-32.yaml` |
| `esp32c3_devkitm` | `esp32c3-devkit.yaml` |
| `esp32s3_devkitc/esp32s3/procpu` | `esp32s3-zero.yaml` |
| `esp32s3_devkitm/esp32s3/procpu` | `esp32s3-zero.yaml` |
| `esp32s3_touch_lcd_1_28/esp32s3/procpu` | `esp32s3-zero.yaml` |
| `nrf52dk/nrf52832` | `nrf52-dk.yaml` |
| `nrf52840dk/nrf52840` | `nrf52840-dk.yaml` |
| `nucleo_f103rb` | `nucleo-f103rb-epaper.yaml` |
| `nucleo_f401re` | `nucleo-f401re.yaml` |
| `nucleo_g474re` | `nucleo_g474re.yaml` |
| `nucleo_h563zi` | `nucleo-h563zi-demo.yaml` |
| `nucleo_l073rz` | `nucleo-l073rz.yaml` |
| `nucleo_l476rg` | `nucleo-l476rg.yaml` |
| `nucleo_wb55rg` | `mb1355c.yaml` |
| `nucleo_wba52cg` | `nucleo_wba52cg.yaml` |
| `rpi_pico` | `rp2040-pico.yaml` |
| `rpi_pico/rp2040/w` | `rp2040-pico.yaml` |
| `segger_trb_stm32f407` | `nucleo-f407.yaml` |
| `stm32f401_mini` | `stm32f401cdu6.yaml` |
| `xiao_ble` | `seeed-xiao-nrf52840-sense.yaml` |
| `xiao_ble/nrf52840/sense` | `seeed-xiao-nrf52840-sense.yaml` |
| `xiao_esp32s3/esp32s3/procpu` | `esp32s3-zero.yaml` |

This covers the Zephyr targets that currently have matching LabWired system
manifests or a model-backed board manifest for the same SoC family. Secondary
ESP32 app-core targets are not listed because `west simulate` boots one ELF
through the primary-core LabWired runner path.

## Using the runner instead

Stock Zephyr discovers runners from a fixed list, so `west flash -r labwired`
requires the `labwired` runner to be importable on the `runners` package path
(e.g. a `PYTHONPATH` entry pointing at `scripts/runners`, or vendoring the file).
The runner accepts the same `--labwired-bin` / `--system` / `--systems-dir` /
`--max-steps` / `--timeout` options. `west simulate` needs none of this.

## Development

```
python3 -m pytest tests/
```

The unit tests (board resolution, CLI assembly, board-target detection) run
anywhere. The integration test boots a pinned `nrf52840dk` `hello_world.elf`
through the real CLI and is skipped unless `LABWIRED_BIN` and a LabWired
`configs/systems` directory (`LABWIRED_SYSTEMS_DIR`) are available.

## License

Apache-2.0.
