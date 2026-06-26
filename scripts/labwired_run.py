#!/usr/bin/env python3
"""``run_custom`` entry point: boot a built Zephyr image in LabWired.

This is the command the board's ``run_custom`` target (board.cmake) invokes, so
that stock twister's ``custom`` simulation handler — which runs ``ninja run`` and
scores the streamed stdout with its ztest/console harness — drives LabWired.

It is a thin CLI over :mod:`labwired_sim`: the board target is read from the
build's ``.config``, the system manifest is resolved from ``boards.map`` or
derived from the build's own devicetree, and the UART console streams to stdout
(LabWired's own logs go to stderr) for the harness to parse. Configuration that
varies by environment is taken from the environment so the CMake target stays
fixed:

  LABWIRED_BIN          the labwired binary (else ``labwired`` on PATH)
  LABWIRED_SYSTEMS_DIR  configs/systems for the boards.map lookup
  LABWIRED_CHIP         SoC id, to derive the system from the devicetree
  LABWIRED_CHIPS_DIR    configs/chips, with LABWIRED_CHIP, to derive
  LABWIRED_MAX_STEPS    step budget (else labwired_sim.DEFAULT_MAX_STEPS)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labwired_sim  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run a built Zephyr image in LabWired (twister run_custom).")
    ap.add_argument("--build-dir", default="build", help="Zephyr application build directory")
    ap.add_argument("--board-map", required=True, help="path to boards.map")
    ap.add_argument("--max-steps", type=int, default=None, help="override the step budget")
    args = ap.parse_args(argv)

    # The twister console/ztest harness scores LabWired's stdout line by line, so
    # stdout must be the firmware UART alone. LabWired's own tracing is INFO and
    # can interleave mid-line; default it to warn so only the firmware console is
    # emitted (the caller can still override RUST_LOG for debugging).
    os.environ.setdefault("RUST_LOG", "warn")

    max_steps = args.max_steps
    if max_steps is None:
        env_steps = os.environ.get("LABWIRED_MAX_STEPS")
        max_steps = int(env_steps) if env_steps else labwired_sim.DEFAULT_MAX_STEPS

    try:
        rc, _ = labwired_sim.simulate(
            build_dir=args.build_dir,
            board_map_path=args.board_map,
            max_steps=max_steps,
            chip=os.environ.get("LABWIRED_CHIP"),
            chips_dir=os.environ.get("LABWIRED_CHIPS_DIR"),
        )
    except labwired_sim.LabwiredError as exc:
        print(f"labwired run error: {exc}", file=sys.stderr)
        return 2
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
