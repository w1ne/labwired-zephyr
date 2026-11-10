# labwired-zephyr

Run Zephyr applications in the [LabWired](https://github.com/w1ne/labwired-core)
deterministic simulator straight from your west workflow — build for a real
board, then boot the firmware in the sim and watch the UART console, no hardware
attached.

```
west build -b nrf52840dk/nrf52840 samples/hello_world
west labwired-simulate
```

```
*** Booting Zephyr OS ...
Hello World! nrf52840dk/nrf52840
```

LabWired runs the **unmodified** ELF (the same binary you would flash), so the
kernel, drivers, and your code execute against modeled peripheral
models. Exit code and console output make it usable as a CI smoke test.

## How it works

`west labwired-simulate` resolves the build's board target to a LabWired *system
manifest* via [`boards.map`](boards.map), then runs:

```
labwired --firmware build/zephyr/zephyr.elf --system <mapped>.yaml --max-steps N
```

streaming the console and propagating the exit code. The same core also backs a
`ZephyrBinaryRunner` for native `west flash` and `west simulate` on Zephyr 4.5
with the optional module below. `west labwired-simulate` works with both Zephyr
3.7 and 4.5 once this west extension and the simulator paths are configured.

The command uses a distinct name because stock Zephyr already registers
`west simulate`. Registering a second command with that name causes west to
ignore one of the extensions.

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

Boards are listed in [`boards.map`](boards.map), which is the authoritative
snapshot. It currently maps 156 Zephyr target identifiers whose `board.yml`
declares a LabWired-modeled SoC family: nRF52832, nRF52840, RP2040, ESP32,
ESP32-C3, ESP32-S3, STM32F103, STM32F401, STM32F407, STM32G474, STM32H563,
STM32L073, STM32L476, STM32WB55, and STM32WBA52.

Each line maps a qualified Zephyr board target to the LabWired system manifest
it should run against. Prefer exact board manifests when they exist; otherwise
map same-SoC boards to the closest model-backed system manifest. Do not add
core-only mappings across different SoC families: a Cortex-M4 STM32 image and a
Cortex-M4 nRF52 image touch different memory-mapped peripherals during boot.

Representative examples:

| Zephyr target | LabWired system |
| --- | --- |
| `nrf52840dk/nrf52840` | `nrf52840-dk.yaml` |
| `nucleo_h563zi` | `nucleo-h563zi-demo.yaml` |
| `esp32s3_luatos_core/esp32s3/procpu` | `esp32s3-zero.yaml` |
| `blackpill_f401ce` | `stm32f401cdu6-blackpill.yaml` |
| `xiao_rp2040` | `rp2040-pico.yaml` |

## Using the runner instead

On **Zephyr 4.5**, enable the optional native runner module in the shell used
for both building and running:

```bash
# From the west workspace root; keep any existing extra modules.
export ZEPHYR_EXTRA_MODULES="${ZEPHYR_EXTRA_MODULES:+${ZEPHYR_EXTRA_MODULES};}$(west list labwired-zephyr -f '{abspath}')/native-runner"
export LABWIRED_BIN=/path/to/labwired
export LABWIRED_SYSTEMS_DIR=/path/to/labwired-core/configs/systems
west build -p always -b nrf52840dk/nrf52840 zephyr/samples/hello_world
west simulate -r labwired
west flash -r labwired
```

The optional module uses Zephyr's [external runner metadata](https://docs.zephyrproject.org/latest/develop/modules.html#external-runners)
and CMake runner registration. Both commands execute the simulator. It adds
LabWired alongside the board's existing runners and keeps the hardware flash
default. Keep `ZEPHYR_EXTRA_MODULES` exported when running west; a CMake-only
`-DZEPHYR_EXTRA_MODULES=...` setting does not register the Python runner for
the later west process. Reconfigure an existing build after enabling it.

Zephyr **3.7** does not support this native module metadata. Leave the optional
module disabled and use `west labwired-simulate`. The root module remains valid
for 3.7. Adding `scripts/runners` to `PYTHONPATH` alone does not register a runner.
Neither path changes an installed Zephyr checkout.

The native runner accepts `--labwired-bin`, `--system`, `--systems-dir`,
`--board-map`, `--max-steps`, and `--timeout`.

## Development

```
python3 -m pytest tests/
```

The unit tests (board resolution, CLI assembly, board-target detection) run
anywhere. The integration test boots a pinned `nrf52840dk` `hello_world.elf`
through the real CLI and is skipped unless `LABWIRED_BIN` and a LabWired
`configs/systems` directory (`LABWIRED_SYSTEMS_DIR`) are available.

`tests/test_west_integration.py` also requires `west`, `cmake`, and
`ZEPHYR_BASE`. It registers the real stock Zephyr commands beside this module,
uses Zephyr's CMake functions to register the native runner, and runs the
committed firmware through both native commands. It checks failure propagation
and verifies that the hardware flash default is preserved. Set
`LABWIRED_REQUIRE_INTEGRATION=1` to fail on missing inputs. Native cases require
4.5; `LABWIRED_REQUIRE_NATIVE=1` makes an older version a failure.

The self-hosted `west-integration` workflow tests 3.7 and 4.5 with the released
Core v0.25.0 binary. These checks use a prebuilt ELF; they do not replace a fresh
Zephyr SDK build, a Twister run, or a test of every board in `boards.map`.

## License

Apache-2.0.
