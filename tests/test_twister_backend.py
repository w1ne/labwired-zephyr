"""The stock-twister `custom` simulation backend: board-root wiring + run shim.

These assert the contract that lets unmodified twister drive LabWired (no Zephyr
or twister fork): a board declaring `simulation: custom`, a `run_custom` target
over the run shim, and the module board_root that makes the board discoverable.
The end-to-end proof (twister builds + runs + scores ztest/console) needs the
toolchain + labwired binary and lives in the README recipe.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import labwired_run  # noqa: E402
import labwired_sim  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BOARD = REPO / "boards" / "labwired" / "lwnrf52840dk"


def test_board_declares_custom_simulation():
    text = (BOARD / "lwnrf52840dk_nrf52840.yaml").read_text()
    assert "simulation: custom" in text
    # simulation_exec must be set so twister marks the run handler ready
    assert "simulation_exec: labwired" in text
    assert "identifier: lwnrf52840dk/nrf52840" in text


def test_board_cmake_wires_run_custom():
    text = (BOARD / "board.cmake").read_text()
    assert "set(SUPPORTED_EMU_PLATFORMS custom)" in text
    assert "add_custom_target(run_custom" in text
    assert "labwired_run.py" in text
    # ZEPHYR_BASE is forwarded so the system-derivation path finds bundled dtlib
    assert "ZEPHYR_BASE=${ZEPHYR_BASE}" in text


def test_module_declares_board_root():
    text = (REPO / "zephyr" / "module.yml").read_text()
    assert "board_root:" in text


def test_run_shim_silences_logs_and_delegates(monkeypatch, tmp_path):
    """labwired_run defaults RUST_LOG=warn (clean UART for the harness) and
    forwards the build dir, board map, and derive env to simulate()."""
    monkeypatch.delenv("RUST_LOG", raising=False)
    monkeypatch.setenv("LABWIRED_CHIP", "nrf52840")
    monkeypatch.setenv("LABWIRED_CHIPS_DIR", str(tmp_path / "chips"))

    captured = {}

    def fake_simulate(**kwargs):
        captured.update(kwargs)
        import os
        captured["RUST_LOG"] = os.environ.get("RUST_LOG")
        return 0, None

    monkeypatch.setattr(labwired_sim, "simulate", fake_simulate)
    rc = labwired_run.main(["--build-dir", str(tmp_path / "build"), "--board-map", str(REPO / "boards.map")])

    assert rc == 0
    assert captured["RUST_LOG"] == "warn"
    assert captured["chip"] == "nrf52840"
    assert captured["chips_dir"] == str(tmp_path / "chips")
    assert Path(captured["build_dir"]) == tmp_path / "build"


def test_run_shim_honours_explicit_rust_log(monkeypatch, tmp_path):
    monkeypatch.setenv("RUST_LOG", "debug")
    monkeypatch.setattr(labwired_sim, "simulate", lambda **k: (0, None))
    # setdefault must not clobber an explicit RUST_LOG
    labwired_run.main(["--build-dir", str(tmp_path), "--board-map", str(REPO / "boards.map")])
    import os
    assert os.environ["RUST_LOG"] == "debug"
