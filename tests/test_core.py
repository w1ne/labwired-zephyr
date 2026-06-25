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


SUPPORTED_ZEPHYR_TARGETS = {
    # Nordic
    "nrf52840dk/nrf52840": "nrf52840-dk.yaml",
    "nrf52dk/nrf52832": "nrf52-dk.yaml",
    "xiao_ble": "seeed-xiao-nrf52840-sense.yaml",
    "xiao_ble/nrf52840/sense": "seeed-xiao-nrf52840-sense.yaml",
    # RP2040
    "rpi_pico": "rp2040-pico.yaml",
    "rpi_pico/rp2040/w": "rp2040-pico.yaml",
    # STM32 boards with exact LabWired system manifests.
    "nucleo_f103rb": "nucleo-f103rb-epaper.yaml",
    "nucleo_f401re": "nucleo-f401re.yaml",
    "blackpill_f401cc": "stm32f401cdu6-blackpill.yaml",
    "blackpill_f401ce": "stm32f401cdu6-blackpill.yaml",
    "stm32f401_mini": "stm32f401cdu6.yaml",
    "black_f407ve": "nucleo-f407.yaml",
    "black_f407zg_pro": "nucleo-f407.yaml",
    "segger_trb_stm32f407": "nucleo-f407.yaml",
    "nucleo_h563zi": "nucleo-h563zi-demo.yaml",
    "nucleo_l073rz": "nucleo-l073rz.yaml",
    "nucleo_l476rg": "nucleo-l476rg.yaml",
    "nucleo_g474re": "nucleo_g474re.yaml",
    "nucleo_wb55rg": "mb1355c.yaml",
    "nucleo_wba52cg": "nucleo_wba52cg.yaml",
    # Espressif boards with matching LabWired chip/board manifests.
    "esp32_devkitc_wroom/esp32/procpu": "esp32-wroom-32.yaml",
    "esp32c3_devkitm": "esp32c3-devkit.yaml",
    "esp32s3_devkitc/esp32s3/procpu": "esp32s3-zero.yaml",
    "esp32s3_devkitm/esp32s3/procpu": "esp32s3-zero.yaml",
    "esp32s3_touch_lcd_1_28/esp32s3/procpu": "esp32s3-zero.yaml",
    "xiao_esp32s3/esp32s3/procpu": "esp32s3-zero.yaml",
}


@pytest.mark.parametrize(("board", "system"), sorted(SUPPORTED_ZEPHYR_TARGETS.items()))
def test_repo_board_map_covers_supported_zephyr_targets(board, system):
    m = labwired_sim.load_board_map(BOARD_MAP)
    assert m[board] == system


def test_repo_board_map_covers_model_backed_zephyr_catalog_snapshot():
    m = labwired_sim.load_board_map(BOARD_MAP)
    assert len(m) == 156
    assert m["xiao_esp32c3"] == "esp32c3-devkit.yaml"
    assert m["esp32s3_luatos_core/esp32s3/procpu"] == "esp32s3-zero.yaml"
    assert m["stm32_min_dev@blue"] == "stm32f103-bare.yaml"
    assert "esp32s2_saola" not in m
    assert "esp32c6_devkitc" not in m


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


def test_read_board_target_normalizes_legacy_board_target_separator(tmp_path):
    z = tmp_path / "zephyr"
    z.mkdir()
    (z / ".config").write_text(
        'CONFIG_BOARD_TARGET="xiao_ble_nrf52840_sense"\n'
    )
    assert labwired_sim.read_board_target(tmp_path) == "xiao_ble/nrf52840/sense"


def test_read_board_target_missing_config_is_clear(tmp_path):
    with pytest.raises(labwired_sim.LabwiredError) as exc:
        labwired_sim.read_board_target(tmp_path)
    assert "build first" in str(exc.value)
