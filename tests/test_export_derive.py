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
