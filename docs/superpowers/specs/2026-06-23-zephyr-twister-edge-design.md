# Zephyr twister on LabWired — design (SP1 + SP4)

Date: 2026-06-23
Status: approved, pre-implementation
Repo home: `w1ne/labwired-zephyr` (out-of-tree Zephyr module + board root)
Related: `w1ne/labwired-core` (the simulator + silicon-fidelity gate), labwired-core PR #340
(nRF52 UARTE EasyDMA TX), app PR #376 (hosted Zephyr west compile, merged).

## The thesis: not another Renode — something better

Renode proved the model: a functional simulator wired into Zephyr's `twister`
test runner, so Zephyr's own corpus runs against it. We adopt the *integration
shape* and then beat it on the axes that actually matter. We are explicitly **not**
trying to become a second Renode (we will not win on raw board count — that is a
decade of community work). We win where Renode is structurally weak:

1. **Silicon-validated fidelity.** Renode is functionally accurate but not
   register/behaviour-validated against real silicon. LabWired has a drift gate
   backed by live SWD captures (the same gate that just blocked PR #340). When a
   Zephyr test passes on LabWired, it passes because the model matches *measured
   silicon*, not because it is "close enough." Twister gives us thousands of
   tests; the drift gate makes every green result mean more than Renode's.
2. **Agent-first by construction.** Renode's surface is a human `.resc`/`.repl`
   monitor and robot scripts. LabWired is built to be driven by an AI agent — MCP
   tools, hosted compile, and a closed write→build→run→inspect loop. Twister
   integration is what lets an agent run a real firmware test suite and read the
   result, end to end, with no human in the loop.
3. **Zero-install, hosted.** Renode needs a local install and a .NET/Mono
   runtime. LabWired already compiles and runs Zephyr in the cloud
   (builder.labwired.com, app PR #376). The twister loop can run hosted.
4. **Multi-node co-sim *with* fidelity.** LabWired already has the multi-node
   substrate (see "Existing assets") — and pairs it with the silicon-fidelity
   gate, which Renode's functional multi-node does not.

Twister is therefore a **means, not the identity**: the vehicle that turns
Zephyr's corpus into proof of our fidelity + agent-first edge. Every success
criterion below is written to surface that edge, not to match a checklist.

This spec covers two sub-projects of the larger program:

- **SP1 — twister run loop** (the foundation): build + run Zephyr ztest/sample
  suites on LabWired through stock twister, pass/fail reported, **each pass
  backed by the drift gate**.
- **SP4 — breadth + upstreaming**: a repeatable recipe to add boards, and the
  path from out-of-tree to a first-class upstream `simulation: labwired`.

Out of scope, each deferred to its own spec:

- **SP2 — scripted/interactive tests** (keyword assertions, GPIO poking, reset
  sequencing). LabWired's `--script` is the bridge.
- **SP3 — multi-node net/BT twister suites.** The multi-node *substrate* already
  exists; SP3 is per-protocol driver-fidelity work, not framework work.

## Goal & success criteria

1. On stock, pinned Zephyr **v3.7 LTS** with **no fork of Zephyr or twister**,
   `twister` builds and runs Zephyr's ztest and sample suites for board target
   `nrf52840dk/nrf52840` on LabWired and reports per-test pass/fail.
2. **The edge is visible, not implied:** every twister run executes against a
   silicon-validated model, and the CI smoke asserts both that the suite passes
   *and* that the board is drift-gate clean — a green test on a stale model
   fails. The whole loop is runnable headless/agent-driven (no monitor, no human).
3. A documented, repeatable recipe adds the next board with no per-board glue
   code — validated by bringing up a second board (an STM32 LabWired already
   models) end-to-end.
4. A defined upstreaming track: the out-of-tree artifacts are exactly what gets
   contributed upstream later, not throwaway.

Non-goals: SP2 and SP3 (above); changing the LabWired CLI's `--firmware`/
`--system` contract; matching Renode's raw board *count* (we compete on depth and
agent-readiness, not breadth).

## How twister runs a simulator (verified, Zephyr 3.7)

Confirmed by reading `scripts/pylib/twister/twisterlib/handlers.py` and
`testinstance.py` in the pinned workspace:

- `SUPPORTED_SIMS = ["mdb-nsim", "nsim", "renode", "qemu", "tsim", "armfvp",
  "xt-sim", "native", "custom"]` — there is a generic **`custom`** sim type.
- `SimulationHandler(BinaryHandler)` handles non-QEMU sims. For a non-`native`,
  non-`renode` type it keeps `call_make_run = True`, so `_create_command`
  returns `[generator_cmd, "run"]` — i.e. it invokes the board's **`ninja run`**
  target and streams that process's stdout line-by-line into the harness.
- The stock `console`/`ztest` harness parses those lines for the ztest banner and
  per-test `PASS`/`FAIL`, scoring the run. No twister code change needed for this
  path.

This is the zero-patch hook: declare a board with `simulation: custom` and a
`run` target that launches `labwired`, and stock twister drives it.

## Architecture

Five pieces; four already exist.

1. **Board root** (NEW) — a `BOARD_ROOT`-discoverable tree in this repo providing
   board entries that (a) declare `simulation: custom` in their twister metadata
   and (b) supply a `board.cmake` `run` target invoking `labwired`. `BOARD_ROOT`
   is a first-class Zephyr extension point, so this needs no Zephyr patch. Board
   entries reuse the real SoC devicetree (the silicon is real; only the run/sim
   wiring is added).
2. **Run shim** (EXISTS) — `scripts/labwired_sim.py::simulate()` already resolves
   board → LabWired system via `boards.map`, assembles the CLI argv, streams UART
   to stdout, and terminates via `--max-steps`. The `run` target calls into it.
3. **Harness** (EXISTS, stock twister) — `console`/`ztest`. No new code.
4. **Board→system map** (EXISTS) — `boards.map` + `configs/systems/*.yaml`,
   already shared with the hosted compiler.
5. **Handler** (EXISTS, stock twister) — `SimulationHandler` via `ninja run`.

Data flow: `twister` → build (west/CMake) → `ninja run` → `board.cmake` run
target → `labwired_sim.py` → `labwired --firmware … --system … --max-steps` →
UART to stdout → twister `console`/`ztest` harness → pass/fail.

The drift gate runs in `labwired-core` CI; the twister smoke (below) pins the
board it runs against to a drift-clean state, so the edge is enforced, not just
asserted in prose.

## The one real risk: the `run`-target mechanism

The single technical unknown is whether `ninja run` cleanly maps to `labwired`
for a `custom`-sim board on 3.7 (Zephyr's `run` target is normally created by an
emulator `board.cmake` include such as `qemu.board.cmake`). The spec mandates a
**spike before the rest of the plan is detailed**:

- Wire exactly one board's `run` target to `labwired`.
- Confirm `twister -p <board>` builds it, drives the run target, and the `ztest`
  harness scores a known-passing ztest suite (e.g. `tests/kernel/common`).

Fallback if a raw `add_custom_target(run …)` conflicts with Zephyr's own `run`
handling: register `labwired` as a ZephyrBinaryRunner with the **`run`**
capability (we already have `scripts/runners/labwired.py`) so the standard runner
machinery creates the `run` target. Either way the run shim underneath is the
same `labwired_sim.py`.

A second known consideration, settled in advance: ztest suites must terminate for
the harness to finalize. LabWired's `--max-steps` guarantees termination, and the
`ztest` harness detects the end-of-suite banner before that; `DEFAULT_MAX_STEPS`
(5M) already reaches boot + console with margin and is tunable per board.

## Board-breadth model (SP4, part 1)

Adding a board is three declarative edits, no code:

1. one board-root entry (reusing the upstream SoC devicetree + the shared sim
   `board.cmake` fragment),
2. one `boards.map` line (`<board target>: <system>.yaml`),
3. one LabWired system manifest under `configs/systems/`.

The only gate is that LabWired already models the SoC — and models it to silicon
fidelity, which is the differentiator we are scaling, not raw count. Today that
covers nRF52, STM32F1/F4/H5, RP2040, and the RISC-V CI fixtures. The recipe is
validated by bringing up a second board (an STM32) end-to-end.

## Upstreaming track (SP4, part 2)

Approach B is the endgame, sequenced *after* SP1 proves out, and explicitly not
throwaway: the board root and `boards.map` produced here are the upstream
contribution. The upstream delta is a thin `LabwiredHandler` mirroring the
existing renode handler plus adding `labwired` to `SUPPORTED_SIMS`, enabling
first-class `simulation: labwired` on boards. Gating condition: LabWired must be
installable in Zephyr CI; `labwired-core` is open, which makes this viable.
Upstreaming is tracked but not on SP1's critical path — the zero-patch `custom`
route delivers full ztest runs without it. Strategically, landing `simulation:
labwired` upstream puts the silicon-fidelity + agent-first simulator in front of
the entire Zephyr community as a distinct option, not a Renode substitute.

## Existing assets — the edge is already partly built

These are already in `labwired-core` and are the foundation of the
differentiation (they also de-risk SP3):

- `crates/core/src/world.rs` `World` — holds multiple `Machine` nodes.
- `crates/core/src/network/` — `Interconnect` trait, `CanBus`, `WirelessBus`,
  `virtual_uart_wire`, `mqtt`, `sim`.
- Multi-node coverage — `crates/cli/src/bin/demo_multi_node.rs`,
  `crates/core/tests/multi_node_iot.rs` (CAN controller → CAN+wireless bridge →
  wireless monitor), `world_multichip.rs`.
- CAN — `bxcan.rs`, `can.rs`, `fdcan.rs` (+ `tests/fdcan.rs`).
- BLE/radio — `nrf52/radio.rs`, `radio.rs`, paired `firmware-nrf52840-ble-collector`
  / `firmware-nrf52840-ble-rx`.
- Silicon-fidelity drift gate — `validation/manifest.yaml` +
  `scripts/generate_validation_status.py`, live SWD captures per board.

Implication: the multi-node interconnect framework that took Renode years already
exists *and* is paired with a fidelity gate Renode lacks. The edge is not
aspirational — it is shipped substrate that twister will expose and prove.

## Testing

- The spike's known-passing ztest suite becomes a CI smoke that asserts **both**
  the suite passes through twister **and** the board is drift-gate clean (the edge
  is gated, not narrated).
- Extend the existing `boards.map` parity test to cover new entries.
- The breadth recipe is validated by a second board brought up end-to-end.
- All existing labwired-zephyr pytest (14, incl. the real-CLI hello_world boot)
  must stay green.

## Risks & mitigations

- **`ninja run` wiring** — primary risk; gated behind the mandatory spike with a
  runner-capability fallback (above).
- **ztest suites needing peripherals LabWired doesn't model** — expected; scope
  the SP1 smoke to kernel/common suites that need only CPU + systick + UART, and
  let breadth/fidelity expand the runnable set incrementally. Document which
  suites are in-scope rather than implying full-corpus green on day one. Honesty
  here *is* the edge — we report a silicon-validated runnable set, not a green
  wall.
- **Pinned-version drift** — keep everything on Zephyr v3.7 LTS to match the
  hosted compiler and the proven Phase 0 workspace; revisit on the next LTS.

## Deliverables

1. Board root (nRF52840 + one STM32) with `simulation: custom` + shared sim
   `board.cmake`.
2. `run`-target wiring over `labwired_sim.py` (or runner-capability fallback).
3. CI ztest smoke that gates on suite-pass **and** drift-clean.
4. Extended `boards.map` parity test.
5. README/recipe: "add a board" and "run Zephyr tests on LabWired via twister,"
   leading with the fidelity + agent-first edge over a functional simulator.
6. An upstreaming note capturing the `LabwiredHandler` delta for the SP4 PR.
