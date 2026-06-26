"""Unit tests for the shared core: board-map parsing, system resolution, argv
assembly, and board-target detection. No Zephyr, west, or labwired binary
needed."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import labwired_sim  # noqa: E402
import validate_matrix  # noqa: E402

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


def test_validate_matrix_expected_hello_world_line():
    assert (
        validate_matrix.expected_hello("nrf52840dk/nrf52840")
        == "Hello World! nrf52840dk/nrf52840"
    )


def test_validate_matrix_classifies_run_pass_from_uart_output():
    result = validate_matrix.classify_run_result(
        board="nrf52840dk/nrf52840",
        returncode=0,
        output="boot log\nHello World! nrf52840dk/nrf52840\r\n",
    )
    assert result.status == "run_pass"
    assert "Hello World!" in result.detail


def test_validate_matrix_classifies_wrong_or_missing_uart_output():
    result = validate_matrix.classify_run_result(
        board="nrf52840dk/nrf52840",
        returncode=0,
        output="boot log\nsome other UART\n",
    )
    assert result.status == "run_fail"
    assert "missing expected UART" in result.detail
    assert "some other UART" in result.detail


def test_validate_matrix_summary_counts_statuses():
    rows = [
        validate_matrix.Result("a", "sys.yaml", "run_pass", "ok", None),
        validate_matrix.Result("b", "sys.yaml", "build_fail", "no", None),
        validate_matrix.Result("c", "sys.yaml", "run_pass", "ok", None),
    ]
    assert validate_matrix.summarize(rows) == {"build_fail": 1, "run_pass": 2}


def test_validate_matrix_parse_jobs_default_and_override():
    default_args = validate_matrix.parse_args(["--systems-dir", "/sys"])
    assert default_args.jobs == 1
    override_args = validate_matrix.parse_args(["--systems-dir", "/sys", "--jobs", "4"])
    assert override_args.jobs == 4
# ── DTS-derived system manifest (the breadth path) ──────────────────────────

FIXTURE_DTS = REPO / "tests" / "fixtures" / "nrf52840dk_merged.dts"

# python-devicetree is only needed for the derivation path, not the runner core.
devicetree = pytest.importorskip("devicetree")


def _build_with_dts(tmp_path):
    """A fake finished build dir whose zephyr.dts is the nrf52840dk fixture."""
    z = tmp_path / "build" / "zephyr"
    z.mkdir(parents=True)
    (z / "zephyr.dts").write_text(FIXTURE_DTS.read_text())
    return tmp_path / "build"


def _chips_dir(tmp_path, *chips):
    d = tmp_path / "chips"
    d.mkdir()
    for chip in chips:
        (d / f"{chip}.yaml").write_text(f'name: "{chip}"\n')
    return d


def test_derive_system_yaml_writes_runnable_manifest(tmp_path):
    import yaml

    build = _build_with_dts(tmp_path)
    chips = _chips_dir(tmp_path, "nrf52840")
    out = labwired_sim.derive_system_yaml(
        build, "nrf52840", chips, build / "labwired" / "system.yaml", name="nrf52840dk/nrf52840"
    )
    parsed = yaml.safe_load(out.read_text())
    # board wiring came from the devicetree
    assert {e["id"] for e in parsed["board_io"]} == {"led0", "led1", "button0"}
    assert {e["id"] for e in parsed["external_devices"]} == {"bme280", "sdhc0"}
    # chip ref is absolute so the manifest runs from anywhere, and points at the real file
    assert parsed["chip"] == str((chips / "nrf52840.yaml").resolve())
    assert Path(parsed["chip"]).exists()


def test_derive_system_yaml_missing_dts_is_clear(tmp_path):
    chips = _chips_dir(tmp_path, "nrf52840")
    (tmp_path / "build" / "zephyr").mkdir(parents=True)
    with pytest.raises(labwired_sim.LabwiredError) as exc:
        labwired_sim.derive_system_yaml(
            tmp_path / "build", "nrf52840", chips, tmp_path / "out.yaml"
        )
    assert "merged devicetree" in str(exc.value)


def test_derive_system_yaml_missing_chip_is_clear(tmp_path):
    build = _build_with_dts(tmp_path)
    chips = _chips_dir(tmp_path)  # empty — no chip descriptor
    with pytest.raises(labwired_sim.LabwiredError) as exc:
        labwired_sim.derive_system_yaml(build, "nrf52840", chips, build / "out.yaml")
    assert "must be modelled first" in str(exc.value)


def test_simulate_requires_chip_and_chips_dir_to_derive(tmp_path):
    build = _build_with_dts(tmp_path)
    (build / "zephyr" / "zephyr.elf").write_text("")  # presence only
    with pytest.raises(labwired_sim.LabwiredError) as exc:
        labwired_sim.simulate(
            build_dir=build,
            board="some_unmapped/board",
            board_map_path=BOARD_MAP,
            derive=True,
        )
    assert "pass --chip and" in str(exc.value)
