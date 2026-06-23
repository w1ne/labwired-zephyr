"""``labwired`` ZephyrBinaryRunner — boots the built ELF in the LabWired
simulator via ``west flash -r labwired``.

This implements the spec's runner interface contract: ``flash`` resolves the
board to a LabWired system manifest and shells out to the LabWired CLI using its
existing ``--firmware``/``--system`` contract, streaming the UART console and
propagating the exit code. The board-resolution and argv-assembly logic is
shared with ``west simulate`` (see :mod:`labwired_sim`).

Discovery note: stock Zephyr imports runners from a fixed list, so to use this
as ``west flash -r labwired`` the module must be on the ``runners`` package path
(see README). ``west simulate`` is the zero-configuration front end and needs no
such registration.
"""

from __future__ import annotations

import sys
from pathlib import Path

from runners.core import RunnerCaps, ZephyrBinaryRunner

# Share the one implementation of board resolution + CLI assembly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import labwired_sim  # noqa: E402

_DEFAULT_BOARD_MAP = Path(__file__).resolve().parent.parent.parent / "boards.map"


class LabwiredBinaryRunner(ZephyrBinaryRunner):
    def __init__(self, cfg, labwired_bin=None, system=None, systems_dir=None,
                 board_map=None, max_steps=labwired_sim.DEFAULT_MAX_STEPS, timeout=None):
        super().__init__(cfg)
        self.labwired_bin = labwired_bin
        self.system = system
        self.systems_dir = systems_dir
        self.board_map = board_map or str(_DEFAULT_BOARD_MAP)
        self.max_steps = max_steps
        self.timeout = timeout

    @classmethod
    def name(cls):
        return "labwired"

    @classmethod
    def capabilities(cls):
        # 'flash' is the natural verb for "load and run on the target"; here the
        # target is the simulator.
        return RunnerCaps(commands={"flash"})

    @classmethod
    def do_add_parser(cls, parser):
        parser.add_argument("--labwired-bin", default=None,
                            help="path to the labwired binary "
                                 "(default: $LABWIRED_BIN or 'labwired')")
        parser.add_argument("--system", default=None,
                            help="LabWired system manifest path, overriding the board map")
        parser.add_argument("--systems-dir", default=None,
                            help="directory holding system manifests "
                                 "(default: $LABWIRED_SYSTEMS_DIR)")
        parser.add_argument("--board-map", default=str(_DEFAULT_BOARD_MAP),
                            help="board → system manifest map")
        parser.add_argument("--max-steps", type=int,
                            default=labwired_sim.DEFAULT_MAX_STEPS,
                            help="max simulation steps")
        parser.add_argument("--timeout", type=float, default=None,
                            help="wall-clock timeout in seconds")

    @classmethod
    def do_create(cls, cfg, args):
        return cls(cfg,
                   labwired_bin=args.labwired_bin,
                   system=args.system,
                   systems_dir=args.systems_dir,
                   board_map=args.board_map,
                   max_steps=args.max_steps,
                   timeout=args.timeout)

    def do_run(self, command, **kwargs):
        if command != "flash":
            raise ValueError(f"unsupported command: {command}")
        try:
            rc, _ = labwired_sim.simulate(
                build_dir=self.cfg.build_dir,
                board_map_path=self.board_map,
                labwired_bin=self.labwired_bin,
                systems_dir=self.systems_dir,
                system_override=self.system,
                elf=self.cfg.elf_file,
                max_steps=self.max_steps,
                timeout=self.timeout,
            )
        except labwired_sim.LabwiredError as exc:
            raise RuntimeError(str(exc)) from exc
        if rc != 0:
            raise RuntimeError(f"LabWired exited with status {rc}")
