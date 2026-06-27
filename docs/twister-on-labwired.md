# Running Zephyr tests on LabWired through twister

Stock Zephyr `twister` runs its own ztest and sample suites against LabWired —
**no fork of Zephyr or twister**. Each green result is backed by LabWired's
silicon-validated models, and the whole loop is headless (no monitor, no human),
which is the edge over a functional simulator: a passing test passes because the
model matches measured silicon, and an agent can run the suite and read the
result end to end.

## How it works

Zephyr's twister has a generic `custom` simulation type. A board that declares
`simulation: custom` and implements a `run_custom` CMake target gets driven by
stock twister: the `SimulationHandler` invokes the board's `ninja run` target and
scores the streamed stdout with the normal `console`/`ztest` harness.

```
twister → west/CMake build → ninja run → board.cmake run_custom
        → scripts/labwired_run.py → labwired --firmware … --system …
        → UART on stdout → twister console/ztest harness → pass/fail
```

Five pieces, only the board root is new here:

| Piece | Where | Role |
|---|---|---|
| Board root | `boards/labwired/lwnrf52840dk/` | declares `simulation: custom`, defines `run_custom` |
| Run shim | `scripts/labwired_run.py` → `labwired_sim.py` | resolve/derive system, run labwired, stream UART |
| Module board_root | `zephyr/module.yml` | makes the board discoverable with zero `-DBOARD_ROOT` plumbing |
| Harness | stock twister `console`/`ztest` | unchanged |
| Handler | stock twister `SimulationHandler` | unchanged |

The run shim resolves the system manifest from `boards.map`, or — for any board
not mapped — **derives it from the build's own devicetree** (`build/zephyr/zephyr.dts`),
so the board's real LEDs/buttons/devices come from the tree rather than a
hand-authored file.

## Run it

A binary built from labwired-core `main` is required (it routes its own logs to
stderr so stdout is clean UART for the harness; older binaries interleave logs
and the harness mis-scores).

```sh
export ZEPHYR_BASE=~/zephyrproject/zephyr
export ZEPHYR_TOOLCHAIN_VARIANT=gnuarmemb GNUARMEMB_TOOLCHAIN_PATH=/usr
export ZEPHYR_VENV_BIN=~/zephyrproject/.venv/bin           # so CMake's python sees twister deps
export LABWIRED_BIN_DIR=<labwired-core>/target/release     # holds the `labwired` binary
export LABWIRED_CHIPS_DIR=<labwired-core>/configs/chips    # to derive the system from DTS

scripts/twister_smoke.sh        # hello_world (console) + ztest base, both PASSED (custom)
```

Or invoke twister directly for any suite:

```sh
west twister -p lwnrf52840dk/nrf52840 \
  --board-root <repo>/boards -x ZEPHYR_EXTRA_MODULES=<repo> \
  -T tests/ztest/base
```

When this repo is a real module in the west manifest, the `board_root` in
`zephyr/module.yml` makes both halves automatic — no `--board-root` or
`ZEPHYR_EXTRA_MODULES` needed.

## Two vendors, one mechanism

The bridge is proven on two silicon vendors with the *same* SoC-agnostic run
shim and *zero* converter changes:

| Board | SoC | Vendor | Derivation | Result |
|---|---|---|---|---|
| `lwnrf52840dk` | nRF52840 | Nordic | board_io from Nordic DTS nodes | console + ztest |
| `lwnucleo_l476rg` | STM32L476 | ST | board_io from ST DTS nodes (`gpioa`/`gpioc`) | console + ztest |

The L476 board's system manifest is derived from ST's own devicetree — different
`compatible` strings, different bus-node shapes — and the `dts_to_system` /
`dts_to_chip` derivation generalised with no code edits, which is the point: this
rides Zephyr's whole board ecosystem, not one vendor.

Bringing up the second vendor also surfaced (and fixed) a real silicon-model
fidelity gap, exactly the kind running unmodified ztest is meant to catch: the
STM32 USARTv2 model dropped the baud-rate register (BRR) read-back, so every
`CONFIG_ASSERT=y` image (the ztest kernel suites) tripped
`uart_stm32_set_baudrate`'s `__ASSERT(BRR >= 16)` and hung silently at PRE_KERNEL
boot, while the console sample ran (the byte path ignores BRR). Fixed in
labwired-core (USARTv2 BRR read-back); the L476 ztest suites then run to
`PROJECT EXECUTION SUCCESSFUL`.

## Add a board

The only gate is that LabWired already models the SoC (to silicon fidelity — the
differentiator being scaled, not raw count). Then it is declarative, no code:

1. A board root entry under `boards/labwired/<board>/` reusing the upstream SoC
   devicetree, declaring `simulation: custom` + `simulation_exec: labwired`, with
   a `board.cmake` that sets `SUPPORTED_EMU_PLATFORMS custom` and defines
   `run_custom` over `scripts/labwired_run.py` (copy `lwnrf52840dk`'s or
   `lwnucleo_l476rg`'s).
2. Either add a `boards.map` line (`<board target>: <system>.yaml`) pointing at a
   LabWired system manifest, or rely on the DTS-derivation fallback by exporting
   `LABWIRED_CHIP`/`LABWIRED_CHIPS_DIR`.

## Honest scope

The runnable set is what LabWired exercises today on a given SoC: CPU + SysTick +
UART (+ GPIO) cover the kernel and console suites. Networking/Bluetooth/sensor
suites that need unmodeled peripherals are out, and the board's twister metadata
says so (`ignore_tags`). This is a silicon-validated runnable set, reported
honestly — not a green wall.

## Upstreaming

The zero-fork `custom` route delivers full ztest runs today. The endgame is a thin
`LabwiredHandler` upstream (mirroring the renode handler, adding `labwired` to
`SUPPORTED_SIMS`) for first-class `simulation: labwired` — the board root and
`boards.map` here are exactly that contribution, not throwaway.
