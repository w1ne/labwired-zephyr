"""``west simulate`` — run a freshly built Zephyr application in the LabWired
deterministic simulator.

This is the out-of-tree front end that works on stock Zephyr: register it from
your west manifest with ``west-commands: west-commands.yml`` on the
labwired-zephyr project entry, then::

    west build -b nrf52840dk/nrf52840 samples/hello_world
    west simulate

It is a thin shim over :mod:`labwired_sim`; the runner (``west flash -r
labwired``) shares the same core.
"""

from __future__ import annotations

import sys
from pathlib import Path

from west.commands import WestCommand

# labwired_sim lives one level up (scripts/); make it importable without a
# package install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import labwired_sim  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_BOARD_MAP = _REPO_ROOT / "boards.map"


class Simulate(WestCommand):
    def __init__(self):
        super().__init__(
            "simulate",
            "run a built Zephyr application in the LabWired simulator",
            "Boot the build's zephyr.elf in LabWired against the system manifest "
            "mapped from the board, streaming the UART console and propagating the "
            "exit code.",
        )

    def do_add_parser(self, parser_adder):
        parser = parser_adder.add_parser(
            self.name, help=self.help, description=self.description
        )
        parser.add_argument(
            "-d", "--build-dir", default="build",
            help="application build directory (default: build)",
        )
        parser.add_argument(
            "--labwired-bin", default=None,
            help="path to the labwired binary (default: $LABWIRED_BIN or 'labwired')",
        )
        parser.add_argument(
            "--system", default=None,
            help="LabWired system manifest path, overriding the board map",
        )
        parser.add_argument(
            "--systems-dir", default=None,
            help="directory holding system manifests "
                 "(default: $LABWIRED_SYSTEMS_DIR; e.g. <labwired>/configs/systems)",
        )
        parser.add_argument(
            "--board-map", default=str(_DEFAULT_BOARD_MAP),
            help="board → system manifest map (default: the repo's boards.map)",
        )
        parser.add_argument(
            "--max-steps", type=int, default=labwired_sim.DEFAULT_MAX_STEPS,
            help=f"max simulation steps (default: {labwired_sim.DEFAULT_MAX_STEPS})",
        )
        parser.add_argument(
            "--timeout", type=float, default=None,
            help="wall-clock timeout in seconds (non-zero exit if it fires)",
        )
        parser.add_argument(
            "labwired_args", nargs="*", metavar="-- ARG",
            help="extra args passed through to labwired (e.g. --trace)",
        )
        return parser

    def do_run(self, args, unknown_args):
        try:
            rc, _ = labwired_sim.simulate(
                build_dir=args.build_dir,
                board_map_path=args.board_map,
                labwired_bin=args.labwired_bin,
                systems_dir=args.systems_dir,
                system_override=args.system,
                max_steps=args.max_steps,
                timeout=args.timeout,
                extra_args=list(args.labwired_args) + list(unknown_args),
            )
        except labwired_sim.LabwiredError as exc:
            self.die(str(exc))
        sys.exit(rc)
