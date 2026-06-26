#!/usr/bin/env bash
# Smoke: run Zephyr suites on LabWired through stock twister (the `custom` sim
# backend), proving the integration end to end. Builds the board, drives the
# board's `ninja run` -> labwired, and scores with twister's own console/ztest
# harness. No fork of Zephyr or twister.
#
# Requires, via environment:
#   ZEPHYR_BASE              a Zephyr v3.7 workspace (west + a toolchain)
#   LABWIRED_BIN_DIR         dir containing the `labwired` binary (added to PATH;
#                            the binary IS the board's simulation_exec)
#   LABWIRED_CHIPS_DIR       LabWired configs/chips (to derive the system from DTS)
# Optional:
#   ZEPHYR_VENV_BIN          west venv bin dir to prepend to PATH (so CMake's
#                            python resolves the twister deps); defaults unset
#   LABWIRED_MAX_STEPS       step budget (default 20000000)
#
# Usage: scripts/twister_smoke.sh [twister args...]   (default: hello_world + ztest base)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${ZEPHYR_BASE:?set ZEPHYR_BASE to a Zephyr v3.7 workspace}"
: "${LABWIRED_BIN_DIR:?set LABWIRED_BIN_DIR to the dir holding the labwired binary}"
: "${LABWIRED_CHIPS_DIR:?set LABWIRED_CHIPS_DIR to LabWired configs/chips}"

export PATH="${ZEPHYR_VENV_BIN:-}${ZEPHYR_VENV_BIN:+:}${LABWIRED_BIN_DIR}:${PATH}"
export LABWIRED_CHIP="${LABWIRED_CHIP:-nrf52840}"
export LABWIRED_MAX_STEPS="${LABWIRED_MAX_STEPS:-20000000}"

OUT="${OUT:-${REPO}/twister-out}"
BOARD="lwnrf52840dk/nrf52840"

# --board-root makes twister discover the board; ZEPHYR_EXTRA_MODULES applies the
# module's board_root to the build (real workspaces get this from the manifest).
ARGS=(-p "${BOARD}" --board-root "${REPO}/boards" -x ZEPHYR_EXTRA_MODULES="${REPO}" -O "${OUT}")
if [ "$#" -gt 0 ]; then
  ARGS+=("$@")
else
  # One console-harness sample + one ztest scenario, selected across both roots.
  ARGS+=(-T "${ZEPHYR_BASE}/samples/hello_world"
         -T "${ZEPHYR_BASE}/tests/ztest/base"
         -s sample.basic.helloworld
         -s tests/ztest/base/testing.ztest.base.verbose_0)
fi

cd "${ZEPHYR_BASE}"
exec west twister "${ARGS[@]}"
