# Self-Verifying Zephyr + BME280 Repo Template — Implementation Plan (Slice A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a self-contained Zephyr application repo (nrf52840dk + BME280, asserting ztest) whose GitHub-hosted CI builds it, boots the real ELF in the LabWired simulator, and scores the ztest green — with zero manual setup by whoever clones it.

**Architecture:** Add an exported-repo *template* under `export/template/zephyr-bme280/` in the `labwired-zephyr-dts` module. The template vendors the single self-contained LabWired chip descriptor (`nrf52840.yaml`) so the sim needs no `labwired-core` checkout, and its CI reuses the module's already-proven `scripts/twister_smoke.sh` (stock Zephyr twister → custom backend → `labwired` binary → ztest scoring). The `labwired` binary is downloaded from a `labwired-core` GitHub release asset at CI time. This slice produces a working, pushable repo by hand; Slice B (separate plan) adds the `labwired_zephyr_*` MCP tools that *generate* such repos.

**Tech Stack:** Zephyr RTOS v3.7, west, Zephyr `bosch,bme280` sensor driver, `zephyrproject-rtos/action-zephyr-setup@v1`, the `labwired` binary (Rust sim), Python 3.12 + `python-devicetree` (converter tests), GitHub Actions, `pytest` (template-validation tests run in the module repo).

## Global Constraints

- Zephyr version floor: **v3.7.0** (the version the module's boot work is proven against). Pin it in `west.yml`.
- LabWired binary: **`labwired-v0.17.3-linux-x86_64.tar.gz`** from `w1ne/labwired-core` releases; the tarball contains only the `labwired` binary. Pin this version in CI; bump deliberately.
- Board target: **`lwnrf52840dk/nrf52840`** (the LabWired board variant shipped in the module's `boards/labwired/` board-root; its `run_custom` target routes `ninja run` → `labwired`).
- SoC id for derivation: **`nrf52840`**; the sim system manifest is **derived from the build's own merged devicetree** (so the app's BME280 overlay node becomes a LabWired external device) using the vendored chip descriptor — never a hand-authored per-board system.
- Console hygiene: set **`RUST_LOG=warn`** for the sim step so only the firmware UART reaches stdout (LabWired INFO logs interleave and mis-score the harness otherwise) — already defaulted by `scripts/labwired_run.py`, but set it explicitly in CI.
- Commits: **no Claude / AI / assistant references** in commit messages.
- TDD: every task writes a failing check first where a local check exists; the SDK-bound build+sim is proven by the CI run in Task 4 (it cannot be compiled in this dev environment).
- Work happens on branch `feat/zephyr-mcp-export` in `~/projects/labwired-zephyr-dts`.

---

### Task 1: Vendor the LabWired chip descriptor and prove the derive path emits BME280

**Files:**
- Create: `export/template/zephyr-bme280/labwired/chips/nrf52840.yaml` (copied verbatim from `labwired-core` `core/configs/chips/nrf52840.yaml`, 266 lines, self-contained)
- Test: `tests/test_export_derive.py`

**Interfaces:**
- Consumes: `scripts/dts_to_system.py` (`dtlib`, `derive_external_devices`, `to_system_yaml`) — existing, unchanged.
- Produces: the vendored chip path `export/template/zephyr-bme280/labwired/chips/nrf52840.yaml` that Task 3's CI points `LABWIRED_CHIPS_DIR` at.

- [ ] **Step 1: Copy the chip descriptor into the template**

```bash
mkdir -p export/template/zephyr-bme280/labwired/chips
cp ~/projects/labwired/core/configs/chips/nrf52840.yaml \
   export/template/zephyr-bme280/labwired/chips/nrf52840.yaml
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_export_derive.py
"""The vendored chip descriptor + the DTS-derive path must yield a LabWired
system that includes the app's BME280 — this is what makes the sim see the
sensor without any labwired-core checkout."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import dts_to_system  # noqa: E402

CHIP = REPO / "export/template/zephyr-bme280/labwired/chips/nrf52840.yaml"
FIXTURE = REPO / "tests/fixtures/nrf52840dk_merged.dts"  # already contains bme280@76


def test_vendored_chip_is_self_contained():
    text = CHIP.read_text(encoding="utf-8")
    assert CHIP.exists()
    assert 'name: "nrf52840"' in text
    # no external file references — vendoring one file must be enough
    assert "$ref" not in text
    assert "../" not in text


def test_derive_emits_bme280_external_device():
    dt = dts_to_system.dtlib.DT(str(FIXTURE))
    externals = dts_to_system.derive_external_devices(dt)
    kinds = " ".join(str(e).lower() for e in externals)
    assert "bme280" in kinds, f"expected bme280 in derived externals, got {externals!r}"
    yaml_text = dts_to_system.to_system_yaml(
        "nrf52840dk", "nrf52840",
        dts_to_system.derive_board_io(dt),
        externals,
        chip_ref=str(CHIP.resolve()),
    )
    assert "bme280" in yaml_text.lower()
    assert str(CHIP.resolve()) in yaml_text
```

- [ ] **Step 3: Run the test to verify it fails before the copy / passes after**

Run: `/tmp/.../zdts-venv/bin/python -m pytest tests/test_export_derive.py -v`
(venv with `python-devicetree`; create with `python3 -m venv venv && venv/bin/pip install pytest devicetree` if not present.)
Expected before Step 1: FAIL (`CHIP.exists()` / FileNotFound). After Step 1: PASS. If `test_derive_emits_bme280_external_device` fails, inspect `derive_external_devices` output against the fixture and fix the assertion to match the real derived shape (do NOT loosen it to always-pass).

- [ ] **Step 4: Commit**

```bash
git add export/template/zephyr-bme280/labwired/chips/nrf52840.yaml tests/test_export_derive.py
git commit -m "vendor nrf52840 chip descriptor + assert derive emits BME280"
```

---

### Task 2: Author the Zephyr app and the asserting BME280 ztest in the template

**Files:**
- Create: `export/template/zephyr-bme280/application/CMakeLists.txt`
- Create: `export/template/zephyr-bme280/application/prj.conf`
- Create: `export/template/zephyr-bme280/application/src/main.c`
- Create: `export/template/zephyr-bme280/application/boards/lwnrf52840dk_nrf52840.overlay`
- Create: `export/template/zephyr-bme280/application/tests/bme280_read/CMakeLists.txt`
- Create: `export/template/zephyr-bme280/application/tests/bme280_read/prj.conf`
- Create: `export/template/zephyr-bme280/application/tests/bme280_read/src/test_bme280.c`
- Create: `export/template/zephyr-bme280/application/tests/bme280_read/testcase.yaml`
- Create: `export/template/zephyr-bme280/application/tests/bme280_read/boards/lwnrf52840dk_nrf52840.overlay`
- Test: `tests/test_export_template.py`

**Interfaces:**
- Consumes: the `lwnrf52840dk/nrf52840` board (module board-root), the `bosch,bme280` Zephyr driver.
- Produces: `application/tests/bme280_read` (twister scenario `app.bme280_read`) that Task 3's CI runs.

- [ ] **Step 1: Write the demo app overlay (enables I2C0 + the BME280 node)**

```dts
/* application/boards/lwnrf52840dk_nrf52840.overlay */
&i2c0 {
    status = "okay";
    bme280@76 {
        compatible = "bosch,bme280";
        reg = <0x76>;
    };
};
```

- [ ] **Step 2: Write the demo app main.c (console read — human-facing demo)**

```c
/* application/src/main.c */
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>

int main(void)
{
    const struct device *dev = DEVICE_DT_GET_ANY(bosch_bme280);

    if (!dev || !device_is_ready(dev)) {
        printk("BME280 not ready\n");
        return 0;
    }
    if (sensor_sample_fetch(dev) != 0) {
        printk("BME280 fetch failed\n");
        return 0;
    }
    struct sensor_value temp;
    sensor_channel_get(dev, SENSOR_CHAN_AMBIENT_TEMP, &temp);
    printk("BME280 temp: %d.%06d C\n", temp.val1, temp.val2);
    return 0;
}
```

- [ ] **Step 3: Write the demo app prj.conf + CMakeLists.txt**

```conf
# application/prj.conf
CONFIG_I2C=y
CONFIG_SENSOR=y
CONFIG_BME280=y
CONFIG_CBPRINTF_FP_SUPPORT=y
```

```cmake
# application/CMakeLists.txt
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(bme280_app)
target_sources(app PRIVATE src/main.c)
```

- [ ] **Step 4: Write the asserting ztest, its overlay, prj.conf, CMakeLists, testcase.yaml**

```c
/* application/tests/bme280_read/src/test_bme280.c */
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
```

```dts
/* application/tests/bme280_read/boards/lwnrf52840dk_nrf52840.overlay */
&i2c0 {
    status = "okay";
    bme280@76 {
        compatible = "bosch,bme280";
        reg = <0x76>;
    };
};
```

```conf
# application/tests/bme280_read/prj.conf
CONFIG_ZTEST=y
CONFIG_I2C=y
CONFIG_SENSOR=y
CONFIG_BME280=y
```

```cmake
# application/tests/bme280_read/CMakeLists.txt
cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(bme280_read)
target_sources(app PRIVATE src/test_bme280.c)
```

```yaml
# application/tests/bme280_read/testcase.yaml
common:
  harness: ztest
  tags:
    - sensor
    - bme280
tests:
  app.bme280_read:
    platform_allow:
      - lwnrf52840dk/nrf52840
```

- [ ] **Step 5: Write the template-validation test (static, runs now)**

```python
# tests/test_export_template.py
"""Static invariants on the exported template — no Zephyr toolchain needed.
The real build+sim proof is the CI run in Task 4."""
from pathlib import Path

T = Path(__file__).resolve().parent.parent / "export/template/zephyr-bme280"
APP = T / "application"


def test_required_files_exist():
    for rel in [
        "CMakeLists.txt", "prj.conf", "src/main.c",
        "boards/lwnrf52840dk_nrf52840.overlay",
        "tests/bme280_read/CMakeLists.txt",
        "tests/bme280_read/prj.conf",
        "tests/bme280_read/src/test_bme280.c",
        "tests/bme280_read/testcase.yaml",
        "tests/bme280_read/boards/lwnrf52840dk_nrf52840.overlay",
    ]:
        assert (APP / rel).exists(), f"missing {rel}"


def test_overlay_declares_bme280():
    for ov in APP.glob("**/lwnrf52840dk_nrf52840.overlay"):
        text = ov.read_text()
        assert 'compatible = "bosch,bme280"' in text
        assert "reg = <0x76>" in text


def test_test_prjconf_enables_driver_stack():
    conf = (APP / "tests/bme280_read/prj.conf").read_text()
    for sym in ["CONFIG_ZTEST=y", "CONFIG_I2C=y", "CONFIG_SENSOR=y", "CONFIG_BME280=y"]:
        assert sym in conf, f"missing {sym}"


def test_ztest_asserts_not_just_prints():
    src = (APP / "tests/bme280_read/src/test_bme280.c").read_text()
    assert "zassert" in src
    assert "sensor_sample_fetch" in src
    assert "SENSOR_CHAN_AMBIENT_TEMP" in src


def test_testcase_uses_ztest_harness_on_labwired_board():
    tc = (APP / "tests/bme280_read/testcase.yaml").read_text()
    assert "harness: ztest" in tc
    assert "lwnrf52840dk/nrf52840" in tc
```

- [ ] **Step 6: Run the validation test**

Run: `venv/bin/python -m pytest tests/test_export_template.py -v`
Expected: PASS (all 5).

- [ ] **Step 7: Commit**

```bash
git add export/template/zephyr-bme280/application tests/test_export_template.py
git commit -m "add nrf52840dk BME280 Zephyr app + asserting ztest template"
```

---

### Task 3: Author the exported repo's west manifest and hosted CI workflow

**Files:**
- Create: `export/template/zephyr-bme280/west.yml`
- Create: `export/template/zephyr-bme280/.github/workflows/ci.yml`
- Create: `export/template/zephyr-bme280/README.md`
- Test: `tests/test_export_ci.py`

**Interfaces:**
- Consumes: `scripts/twister_smoke.sh` (module, unchanged — invoked with the app's test path), the vendored chip dir (Task 1), the test scenario `app.bme280_read` (Task 2).
- Produces: a complete pushable repo tree under `export/template/zephyr-bme280/`.

- [ ] **Step 1: Write the west manifest**

```yaml
# west.yml — the exported repo is the manifest repo (self)
manifest:
  remotes:
    - name: zephyrproject-rtos
      url-base: https://github.com/zephyrproject-rtos
    - name: w1ne
      url-base: https://github.com/w1ne
  projects:
    - name: zephyr
      remote: zephyrproject-rtos
      revision: v3.7.0
      import: true
    - name: labwired-zephyr-dts
      remote: w1ne
      revision: main
      path: modules/labwired-zephyr-dts
      west-commands: west-commands.yml
  self:
    path: application
```

- [ ] **Step 2: Write the CI workflow**

```yaml
# .github/workflows/ci.yml
name: ci
on:
  push:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  converter-tests:
    name: DTS converter (pure python)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install pytest devicetree
      - run: git clone --depth 1 https://github.com/w1ne/labwired-zephyr-dts module
      - run: cd module && python -m pytest -q tests/test_dts_to_system.py tests/test_dts_to_chip.py

  build-and-sim:
    name: build + LabWired sim + ztest (hosted)
    runs-on: ubuntu-latest
    steps:
      - name: Checkout application
        uses: actions/checkout@v4
        with:
          path: application

      - name: Zephyr setup (SDK + west workspace)
        uses: zephyrproject-rtos/action-zephyr-setup@v1
        with:
          app-path: application
          toolchains: arm-zephyr-eabi

      - name: Download LabWired binary
        run: |
          set -euo pipefail
          curl -fsSL -o lw.tgz \
            https://github.com/w1ne/labwired-core/releases/download/v0.17.3/labwired-v0.17.3-linux-x86_64.tar.gz
          mkdir -p "$HOME/lwbin"
          tar xzf lw.tgz -C "$HOME/lwbin"
          chmod +x "$HOME/lwbin/labwired"
          "$HOME/lwbin/labwired" --version || true

      - name: Twister — build, boot in LabWired, score ztest
        env:
          ZEPHYR_BASE: ${{ github.workspace }}/zephyr
          LABWIRED_BIN_DIR: ${{ env.HOME }}/lwbin
          LABWIRED_CHIP: nrf52840
          LABWIRED_CHIPS_DIR: ${{ github.workspace }}/application/labwired/chips
          RUST_LOG: warn
        run: |
          set -euo pipefail
          MOD="${{ github.workspace }}/modules/labwired-zephyr-dts"
          export LABWIRED_BIN_DIR="$HOME/lwbin"
          "$MOD/scripts/twister_smoke.sh" \
            -T "${{ github.workspace }}/application/tests/bme280_read" \
            -s app.bme280_read

      - name: Upload twister output
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: twister-out
          path: modules/labwired-zephyr-dts/twister-out/
          if-no-files-found: ignore
```

Note: `twister_smoke.sh` sets `BOARD=lwnrf52840dk/nrf52840`, `--board-root "$MOD/boards"`, and `ZEPHYR_EXTRA_MODULES="$MOD"`, and `cd "$ZEPHYR_BASE"` before running `west twister`. Passing `-T <path> -s app.bme280_read` replaces its default hello_world targets. The exact `LABWIRED_BIN_DIR`/`ZEPHYR_BASE` paths produced by `action-zephyr-setup` are reconciled in Task 4 against the first real run.

- [ ] **Step 3: Write the README**

```markdown
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
```

- [ ] **Step 4: Write the CI-structure test (static, runs now)**

```python
# tests/test_export_ci.py
"""The exported CI must actually wire the full loop, not a stub."""
from pathlib import Path
import yaml

T = Path(__file__).resolve().parent.parent / "export/template/zephyr-bme280"


def test_west_pins_zephyr_v37_and_module():
    m = yaml.safe_load((T / "west.yml").read_text())["manifest"]
    projects = {p["name"]: p for p in m["projects"]}
    assert projects["zephyr"]["revision"] == "v3.7.0"
    assert "labwired-zephyr-dts" in projects


def test_ci_runs_full_loop():
    ci = yaml.safe_load((T / ".github/workflows/ci.yml").read_text())
    jobs = ci["jobs"]
    assert "build-and-sim" in jobs and "converter-tests" in jobs
    steps = jobs["build-and-sim"]["steps"]
    blob = yaml.safe_dump(steps)
    assert "zephyrproject-rtos/action-zephyr-setup" in blob
    assert "labwired-core/releases/download" in blob          # downloads the binary
    assert "twister_smoke.sh" in blob                          # build+sim+score
    assert "app/labwired/chips" in blob or "application/labwired/chips" in blob


def test_ci_pins_labwired_binary_version():
    ci = (T / ".github/workflows/ci.yml").read_text()
    assert "labwired-v0.17.3-linux-x86_64.tar.gz" in ci
```

- [ ] **Step 5: Run the CI-structure test**

Run: `venv/bin/python -m pytest tests/test_export_ci.py -v`
Expected: PASS (3).

- [ ] **Step 6: Commit**

```bash
git add export/template/zephyr-bme280/west.yml \
        export/template/zephyr-bme280/.github \
        export/template/zephyr-bme280/README.md \
        tests/test_export_ci.py
git commit -m "add exported repo west manifest, hosted CI, and README"
```

---

### Task 4: Prove the exported repo goes green on GitHub-hosted runners

This is the de-risk gate for the whole feature: the only unverified link is the SDK build via `action-zephyr-setup` and the BME280 ztest actually passing against the LabWired model. No local unit test can stand in for a real Actions run.

**Files:**
- Create: `scripts/prove_export.sh`

**Interfaces:**
- Consumes: the full template under `export/template/zephyr-bme280/`.
- Produces: a pushed proof repo + a green CI run (evidence), and any fixes folded back into Tasks 1–3.

- [ ] **Step 1: Write the proof script**

```bash
#!/usr/bin/env bash
# Materialize the template into a throwaway GitHub repo and watch its CI.
set -euo pipefail
REPO_NAME="${1:-zephyr-bme280-proof}"
OWNER="${OWNER:-w1ne}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/export/template/zephyr-bme280"
WORK="$(mktemp -d)"
cp -r "$SRC/." "$WORK/"
cd "$WORK"
git init -q && git add -A && git commit -q -m "init zephyr-bme280 verifiable build"
gh repo create "$OWNER/$REPO_NAME" --private --source=. --push
echo "watching CI for $OWNER/$REPO_NAME ..."
sleep 10
gh run watch -R "$OWNER/$REPO_NAME" --exit-status
```

- [ ] **Step 2: Run the proof**

Run: `bash scripts/prove_export.sh`
Expected: `gh run watch --exit-status` returns 0 (both jobs green). The `build-and-sim` job log shows the BME280 ztest `PASS`.

- [ ] **Step 3: If it fails, fix at the source and re-run**

Likely failure points and fixes (apply to Tasks 1–3 template files, not the proof repo):
- `action-zephyr-setup` can't find the manifest → adjust `west.yml` `self.path` / `app-path`.
- `ZEPHYR_BASE`/`LABWIRED_BIN_DIR` path mismatch → correct the `env:` block in `ci.yml` to the paths the action actually produces (read them from the failed run's log).
- BME280 `device_is_ready` false → the app/test overlay node isn't reaching the merged DTS the derive path reads; confirm i2c0 is enabled on `lwnrf52840dk` and the overlay is in `boards/` so twister applies it.
- `sensor_channel_get` returns an unmodeled channel → switch the asserted channel to one the `bme280.rs` model supports (try `SENSOR_CHAN_PRESS` / `SENSOR_CHAN_HUMIDITY`); keep an asserting (non-trivial) check.
Re-run Step 2 until green.

- [ ] **Step 4: Record the evidence and commit the script**

```bash
git add scripts/prove_export.sh
git commit -m "add export proof script; record green hosted CI run"
```
In the commit body, paste the green `gh run watch` summary line and the run URL as the evidence that Slice A is proven.

- [ ] **Step 5: Delete the throwaway proof repo (optional cleanup)**

```bash
gh repo delete w1ne/zephyr-bme280-proof --yes
```

---

## Self-Review

**Spec coverage:**
- Exported repo with tests + LabWired sim CI on hosted runners → Tasks 2–4. ✅
- Full loop on hosted runners (build → boot ELF via downloaded binary → score) → Task 3 `ci.yml` + Task 4 proof. ✅
- Buildable-by-construction / grounded → Task 2 uses the real `bosch,bme280` driver + real board; Task 1 proves the sim sees the sensor. ✅
- Verified assumptions (binary asset, BME280 model, self-contained chip) → encoded in Global Constraints + Task 1. ✅
- MVP = nrf52840dk + BME280 asserting ztest → Task 2. ✅
- **Deferred to Slice B (separate plan), intentionally out of this plan:** the `labwired_zephyr_{scaffold,build_and_sim,export}` MCP tools, the build-doctor classified-error loop, the export precondition gate. This plan hand-builds the artifact those tools will later generate; that is the spec's "prove the CI green before writing tool code" ordering.

**Placeholder scan:** No TBD/TODO; every code step shows complete file content. The one genuinely run-dependent item (exact `action-zephyr-setup` paths) is explicitly a Task 4 reconciliation step with the method to resolve it, not a hidden placeholder.

**Type consistency:** Board target `lwnrf52840dk/nrf52840`, scenario `app.bme280_read`, chip id `nrf52840`, binary `labwired-v0.17.3-linux-x86_64.tar.gz`, and chip path `application/labwired/chips/nrf52840.yaml` are used identically across Tasks 1–4 and the CI test assertions.
