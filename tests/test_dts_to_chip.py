"""DTS -> LabWired chip.yaml scaffold derivation (the SoC memory-map multiplier).

Requires Zephyr's python-devicetree (present in any Zephyr/west environment).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import dts_to_chip as c  # noqa: E402

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "nrf52840dk_merged.dts"


def _dt():
    return c.dtlib.DT(str(FIXTURE))


def _periphs():
    return c.derive_soc_peripherals(_dt(), "nrf52840")


def test_peripherals_sorted_by_base_address():
    bases = [p["base_address"] for p in _periphs()]
    assert bases == sorted(bases)


def test_uart_maps_to_faithful_model_with_irq():
    uart = next(p for p in _periphs() if p["id"] == "uart0")
    assert uart["type"] == "nrf52840_uart"
    assert uart["base_address"] == 0x40002000
    assert uart["size"] == 0x1000
    assert uart["irq"] == 2
    assert uart["modeled"] is True


def test_timer_compatible_templated_with_chip():
    timer = next(p for p in _periphs() if p["id"] == "timer0")
    assert timer["type"] == "nrf52840_timer"
    assert timer["irq"] == 8


def test_unmapped_compatible_is_unmodeled():
    # the flash controller has no faithful model -> honestly flagged
    fc = next(p for p in _periphs() if p["id"] == "flash_controller")
    assert fc["type"] == c.UNMODELED
    assert fc["modeled"] is False
    assert fc["compatible"] == "nordic,nrf52-flash-controller"


def test_bus_children_are_not_soc_peripherals():
    # bme280 sits under i2c0, not /soc — it's an external device, not a peripheral
    assert all(p["id"] != "bme280" for p in _periphs())


def test_cpu_arch_and_core_inferred():
    arch, core = c._cpu_arch_core(_dt())
    assert arch == "arm"
    assert core == "cortex-m4"  # trailing 'f' of cortex-m4f stripped


def test_flash_and_ram_regions_resolved_from_chosen():
    dt = _dt()
    assert c._region(dt, "zephyr,flash") == (0x0, 0x100000)
    assert c._region(dt, "zephyr,sram") == (0x20000000, 0x40000)


def test_emits_parseable_chip_yaml():
    import yaml

    dt = _dt()
    text = c.to_chip_yaml(
        "nrf52840",
        "arm",
        "cortex-m4",
        c._region(dt, "zephyr,flash"),
        c._region(dt, "zephyr,sram"),
        _periphs(),
    )
    parsed = yaml.safe_load(text)
    assert parsed["name"] == "nrf52840"
    assert parsed["arch"] == "arm"
    assert parsed["flash"]["size"] == "1024KB"
    assert parsed["ram"]["size"] == "256KB"
    ids = {p["id"] for p in parsed["peripherals"]}
    assert {"uart0", "timer0", "i2c0", "spi0", "gpio0"} <= ids
    uart = next(p for p in parsed["peripherals"] if p["id"] == "uart0")
    assert uart["type"] == "nrf52840_uart" and uart["irq"] == 2
