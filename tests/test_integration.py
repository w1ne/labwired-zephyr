"""Integration test: drive a pinned nRF52840 DK ``hello_world`` ELF through the
runner core against the real LabWired CLI, asserting the console output and a
clean exit.

Needs a real LabWired install, so it is skipped unless BOTH are available:
  - a LabWired binary: ``$LABWIRED_BIN`` or ``labwired`` on PATH;
  - its systems directory: ``$LABWIRED_SYSTEMS_DIR`` (e.g. <labwired>/configs/systems),
    which must contain the mapped manifest and the chip descriptors it references.
The unit suite (test_core.py) runs everywhere regardless.
"""

import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import labwired_sim  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"
ELF = FIXTURES / "nrf52840dk_hello_world.elf"


def _labwired_bin():
    return os.environ.get("LABWIRED_BIN") or shutil.which("labwired")


def _systems_dir():
    """Real LabWired systems dir from env, else a sibling labwired-core checkout."""
    env = os.environ.get("LABWIRED_SYSTEMS_DIR")
    if env and Path(env, "nrf52840-dk.yaml").exists():
        return env
    for sibling in ("labwired-core-zephyr", "labwired-core", "labwired"):
        guess = REPO.parent / sibling / "configs" / "systems"
        if (guess / "nrf52840-dk.yaml").exists():
            return str(guess)
    return None


_BIN = _labwired_bin()
_SYS = _systems_dir()
pytestmark = pytest.mark.skipif(
    _BIN is None or _SYS is None,
    reason="needs LABWIRED_BIN and a LabWired configs/systems dir (LABWIRED_SYSTEMS_DIR)",
)


def test_hello_world_boots_and_prints():
    rc, out = labwired_sim.simulate(
        board="nrf52840dk/nrf52840",
        elf=ELF,
        labwired_bin=_BIN,
        board_map_path=REPO / "boards.map",
        systems_dir=_SYS,
        max_steps=3_000_000,
        capture=True,
    )
    assert rc == 0, f"non-zero exit; output:\n{out}"
    assert "Hello World! nrf52840dk" in out, f"console output missing; output:\n{out}"


def test_unmapped_board_fails_clearly():
    with pytest.raises(labwired_sim.LabwiredError) as exc:
        labwired_sim.simulate(
            board="stm32/nope",
            elf=ELF,
            labwired_bin=_BIN,
            board_map_path=REPO / "boards.map",
            systems_dir=_SYS,
        )
    assert "no LabWired system mapped" in str(exc.value)
