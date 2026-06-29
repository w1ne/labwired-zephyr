"""Static invariants on the exported template — no Zephyr toolchain needed.
The real build+sim proof is the CI run in Task 4."""
from pathlib import Path

T = Path(__file__).resolve().parent.parent / "export/template/zephyr-bme280"
APP = T / "application"


def test_required_files_exist():
    for rel in [
        "CMakeLists.txt", "prj.conf", "src/main.c",
        "boards/lwnrf52840dk_nrf52840.overlay",
        "tests/bme280_read/CMakeLists.txt",
        "tests/bme280_read/prj.conf",
        "tests/bme280_read/src/test_bme280.c",
        "tests/bme280_read/testcase.yaml",
        "tests/bme280_read/boards/lwnrf52840dk_nrf52840.overlay",
    ]:
        assert (APP / rel).exists(), f"missing {rel}"


def test_overlay_declares_bme280():
    for ov in APP.glob("**/lwnrf52840dk_nrf52840.overlay"):
        text = ov.read_text()
        assert 'compatible = "bosch,bme280"' in text
        assert "reg = <0x76>" in text


def test_test_prjconf_enables_driver_stack():
    conf = (APP / "tests/bme280_read/prj.conf").read_text()
    for sym in ["CONFIG_ZTEST=y", "CONFIG_I2C=y", "CONFIG_SENSOR=y", "CONFIG_BME280=y"]:
        assert sym in conf, f"missing {sym}"


def test_ztest_asserts_not_just_prints():
    src = (APP / "tests/bme280_read/src/test_bme280.c").read_text()
    assert "zassert" in src
    assert "sensor_sample_fetch" in src
    assert "SENSOR_CHAN_AMBIENT_TEMP" in src


def test_testcase_uses_ztest_harness_on_labwired_board():
    tc = (APP / "tests/bme280_read/testcase.yaml").read_text()
    assert "harness: ztest" in tc
    assert "lwnrf52840dk/nrf52840" in tc
