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

## Supported boards

Boards are listed in [`boards.map`](boards.map). Add one line — the qualified
Zephyr board target and the LabWired system manifest it runs against — to add a
board.

| Zephyr board | LabWired system |
| --- | --- |
| `nrf52840dk/nrf52840` | `nrf52840-dk.yaml` |

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
