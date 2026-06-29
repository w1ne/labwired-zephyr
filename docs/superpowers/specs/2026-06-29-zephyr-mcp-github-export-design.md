# Zephyr-MCP-Export: build a full working Zephyr project via MCP and export a self-verifying GitHub repo

Date: 2026-06-29
Status: Approved (design); pending implementation plan

## Goal

A Codex-driven LabWired MCP flow that produces a **full, working Zephyr west
project**, boots it in the **LabWired simulator**, and **exports it to GitHub**
with tests and a CI workflow that re-runs the whole build+sim loop on
github-hosted runners — so anyone who clones the repo gets a green,
self-verifying build with zero setup.

This closes the "author" side of the Zephyr-honesty problem (devicetree /
Kconfig / BSP grounded in real bindings) on top of the already-shipped
`labwired-zephyr-dts` "run + grounding" layer (`west simulate`,
twister-on-LabWired, DTS → manifest derivation).

**North star:** make it possible to build *fully validated devices — Zephyr and
bare-metal — entirely via MCP*. LabWired already runs bare-metal firmware
(`labwired_compile_firmware` / `build_and_run` over the example ELFs); this
work adds the Zephyr authoring+export path. The MVP below is the first
end-to-end proof (Zephyr + BME280). Where it is cheap, the tool surface
(scaffold → build+validate → export self-verifying repo) should generalize so a
bare-metal track can reuse the same `build_and_sim` + `export` spine later;
where generalizing is not cheap, stay Zephyr-specific and defer.

## MVP slice

- **Board:** `nrf52840dk/nrf52840` — Phase-0 proven, and the committed DTS
  fixture already wires a `bosch,bme280` on `i2c0@0x76`.
- **App:** read the BME280 over I2C and expose the value; a **ztest that
  asserts a plausible reading** (not just a console print).
- **Verified support:** LabWired core ships a real `bme280.rs` model
  (`core/crates/core/src/peripherals/components/bme280.rs`), so the real Zephyr
  `bosch,bme280` driver reads live values in sim.
- **Definition of done:** Codex calls the tools → a real nrf52840dk Zephyr
  project that reads BME280 with an asserting ztest, builds, boots green in the
  LabWired sim, lands as a GitHub repo, and **that repo's hosted CI passes with
  zero manual setup.**

## Decisions (resolved during brainstorming)

| Fork | Decision |
|------|----------|
| Entry point | New `labwired_zephyr_*` MCP tools, Codex-driven (not proto.cat UI, not a bare CLI) |
| Authoring spine | Start from a **real buildable Zephyr sample** for the board, then layer **binding-grounded edits** (overlay / prj.conf / main.c / ztest) — buildable by construction |
| Exported CI depth | **Full loop on github-hosted runners** — build with `action-zephyr-setup`, boot the ELF by downloading the prebuilt `labwired` linux binary release asset; no self-hosted runner, no 15GB SDK for the sim step |
| MVP scope | Single board + single asserting sensor-read ztest (nrf52840dk + BME280) |

Rejected: free-form template generation (non-building risk); device-graph
derivation (couples to proto.cat graph, loses grounding); self-hosted-runner CI
(breaks "anyone can re-run it").

## Verified assumptions

- `labwired-core` v0.17.3 publishes `labwired-v0.17.3-linux-x86_64.tar.gz` as a
  release asset — CI can download it for the sim step.
- The DTS converter (`scripts/dts_to_system.py`, `scripts/dts_to_chip.py`) is
  green: **72 passed, 2 skipped** in a venv with `python-devicetree`; the 2
  skips are the real-binary integration tests (need `LABWIRED_BIN` +
  `LABWIRED_SYSTEMS_DIR`).
- LabWired models the BME280 (and bmp280, adxl345, aht20, ssd1306).
- The sim boot needs only the `labwired` binary + `system.yaml` + the ELF — not
  the Zephyr SDK. The SDK is only needed to *build* the ELF, and Zephyr's own
  `action-zephyr-setup` builds on hosted ubuntu.

## Components

### 1. `labwired_zephyr_scaffold` (new MCP tool)
Location: `labwired/packages/api/src/mcp/tools.ts` (registered alongside the
existing `labwired_*` tools).

- **Input:** board target (e.g. `nrf52840dk/nrf52840`) + app intent (free text).
- **Action:** copy a real Zephyr sample for the board into a fresh workspace;
  parse the board's merged DTS (reuse the converter's `dtlib` path) and return
  the **real bindings / node labels / peripherals available on that board**.
- **Output:** the file tree + the grounded binding catalog, so the agent edits
  against what actually exists rather than inventing node names.

### 2. `labwired_zephyr_build_and_sim` (new MCP tool)
- **Action:** `west build` (via the hosted `labwired-builder` SDK path) → boot
  the ELF in LabWired using the `boards.map` → `system.yaml` mapping.
- **Output:** build log + console + exit code + **classified failure** (Kconfig
  symbol unknown / DTS binding mismatch / link error / sim assertion failed).
- This is the **build-doctor loop**: on failure the agent gets the classified
  error and makes a targeted next edit. Bounded retries.

### 3. `labwired_zephyr_export` (new MCP tool)
- **Precondition:** refuse unless the last `build_and_sim` for this workspace
  was green (no broken repos shipped — mirrors proto.cat's publish gate).
- **Action:** assemble the exported repo (below) and push to GitHub, reusing the
  auth/push pattern from proto.cat's `src/lib/export/github.ts`.

### 4. Exported-repo template
```
app/                  CMakeLists.txt, prj.conf, app.overlay (DTS), src/main.c
tests/                ztest suite (asserts BME280 reads)
west.yml              pins Zephyr v3.7 + the labwired-zephyr-dts module
boards.map            board -> system.yaml (from the module)
.github/workflows/
  ci.yml              hosted: action-zephyr-setup -> west build ->
                      download labwired linux binary -> west simulate ->
                      score ztest/console + the pure-Python DTS-converter tests
README.md             "verifiably runs" badge + how-to
```

## Data flow (happy path)

```
agent -> scaffold(board, intent)        -> real sample tree + grounded bindings
agent edits overlay/prj.conf/main.c/ztest
agent -> build_and_sim()                -> green build + BME280 reads asserted in sim
agent -> export(repo)                   -> GitHub repo pushed
GitHub hosted CI re-runs build+sim      -> green "verifiably runs" badge
```

## Error handling

- **build-doctor loop:** classified failures drive targeted edits, bounded retries.
- **Grounding gate:** scaffold returns the board's real DTS bindings/labels;
  edits referencing a non-existent node/prop are caught before build.
- **Export precondition:** export refuses unless the last build+sim was green.

## How we test the tool itself

- **Unit:** scaffold copies a known sample; export emits the exact file set;
  CI-YAML lint.
- **Integration (the proof):** run the full MCP loop for nrf52840dk+BME280,
  push to a throwaway repo, and assert *that repo's* `ci.yml` goes green. The
  heavy `twister-e2e` self-hosted job stays as the manual deep-fidelity check.

## Top risk (de-risk first in the plan)

The exported repo's hosted `ci.yml` building Zephyr with `action-zephyr-setup`
is the heaviest unproven link (SDK fetch/cache time, west module pin
resolution). Everything else (binary asset, BME280 model, DTS converter, sim
boot) is verified. The plan's first slice proves a hand-written exported-repo
`ci.yml` goes green on hosted runners before any MCP-tool code is written.

## Out of scope (YAGNI for MVP)

- Multi-board generation (boards.map already lists many; add after single-board
  path is proven).
- `west flash -r labwired` runner path in the exported repo (sim via
  `west simulate` only for MVP).
- kconfig-tuner / build-doctor as standalone reusable skills (the loop is
  internal to `build_and_sim` for now).
- proto.cat UI integration (Codex-driven only for MVP).
