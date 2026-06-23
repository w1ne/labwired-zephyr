"""Unit tests for the shared core: board-map parsing, system resolution, argv
assembly, and board-target detection. No Zephyr, west, or labwired binary
needed."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import labwired_sim  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BOARD_MAP = REPO / "boards.map"


def test_load_board_map_parses_and_ignores_comments(tmp_path):
    f = tmp_path / "boards.map"
    f.write_text(
        "# a comment\n"
        "\n"
        "nrf52840dk/nrf52840: nrf52840-dk.yaml\n"
        "  some/board : other.yaml  \n"
    )
    m = labwired_sim.load_board_map(f)
    assert m == {"nrf52840dk/nrf52840": "nrf52840-dk.yaml", "some/board": "other.yaml"}


def test_repo_board_map_has_nrf52840():
    m = labwired_sim.load_board_map(BOARD_MAP)
    assert m["nrf52840dk/nrf52840"] == "nrf52840-dk.yaml"


def test_load_board_map_rejects_malformed(tmp_path):
    f = tmp_path / "boards.map"
    f.write_text("this-line-has-no-colon\n")
    with pytest.raises(labwired_sim.LabwiredError):
        labwired_sim.load_board_map(f)


def test_resolve_system_joins_systems_dir():
    m = {"nrf52840dk/nrf52840": "nrf52840-dk.yaml"}
    p = labwired_sim.resolve_system("nrf52840dk/nrf52840", m, "/sys")
    assert p == Path("/sys/nrf52840-dk.yaml")


def test_resolve_system_override_wins():
    m = {"nrf52840dk/nrf52840": "nrf52840-dk.yaml"}
    p = labwired_sim.resolve_system("anything", m, "/sys", override="/abs/custom.yaml")
    assert p == Path("/abs/custom.yaml")


def test_resolve_system_unknown_board_lists_known():
    m = {"nrf52840dk/nrf52840": "nrf52840-dk.yaml"}
    with pytest.raises(labwired_sim.LabwiredError) as exc:
        labwired_sim.resolve_system("stm32/foo", m, "/sys")
    assert "nrf52840dk/nrf52840" in str(exc.value)


def test_resolve_system_no_systems_dir_is_clear():
    m = {"nrf52840dk/nrf52840": "nrf52840-dk.yaml"}
    with pytest.raises(labwired_sim.LabwiredError) as exc:
        labwired_sim.resolve_system("nrf52840dk/nrf52840", m, None)
    assert "systems" in str(exc.value).lower()


def test_build_argv_order_and_contents():
    argv = labwired_sim.build_argv("labwired", "fw.elf", "sys.yaml", max_steps=42)
    assert argv == [
        "labwired", "--firmware", "fw.elf", "--system", "sys.yaml", "--max-steps", "42",
    ]


def test_build_argv_appends_extra():
    argv = labwired_sim.build_argv("labwired", "fw.elf", "sys.yaml", 42, ["--trace"])
    assert argv[-1] == "--trace"


def test_read_board_target_prefers_qualified(tmp_path):
    z = tmp_path / "zephyr"
    z.mkdir()
    (z / ".config").write_text(
        'CONFIG_BOARD="nrf52840dk"\nCONFIG_BOARD_TARGET="nrf52840dk/nrf52840"\n'
    )
    assert labwired_sim.read_board_target(tmp_path) == "nrf52840dk/nrf52840"


def test_read_board_target_falls_back_to_board(tmp_path):
    z = tmp_path / "zephyr"
    z.mkdir()
    (z / ".config").write_text('CONFIG_BOARD="nrf52840dk"\n')
    assert labwired_sim.read_board_target(tmp_path) == "nrf52840dk"


def test_read_board_target_missing_config_is_clear(tmp_path):
    with pytest.raises(labwired_sim.LabwiredError) as exc:
        labwired_sim.read_board_target(tmp_path)
    assert "build first" in str(exc.value)
