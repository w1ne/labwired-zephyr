"""DTS -> LabWired system.yaml derivation (the breadth multiplier).

Requires Zephyr's python-devicetree (present in any Zephyr/west environment).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import dts_to_system as d  # noqa: E402

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "nrf52840dk_merged.dts"


def _io():
    return d.derive_board_io(d.dtlib.DT(str(FIXTURE)))


def test_derives_leds_and_buttons_sorted():
    io = _io()
    assert [e["id"] for e in io] == ["button0", "led0", "led1"]


def test_led_active_low_decoded_from_gpio_flags():
    led0 = next(e for e in _io() if e["id"] == "led0")
    assert led0 == {
        "id": "led0",
        "kind": "led",
        "peripheral": "gpio0",
        "pin": 13,
        "signal": "output",
        "active_high": False,  # GPIO_ACTIVE_LOW set
    }


def test_active_high_when_flag_clear():
    led1 = next(e for e in _io() if e["id"] == "led1")
    assert led1["active_high"] is True


def test_button_is_input():
    btn = next(e for e in _io() if e["id"] == "button0")
    assert btn["kind"] == "button" and btn["signal"] == "input"


def test_emits_parseable_system_yaml():
    import yaml

    text = d.to_system_yaml("nrf52840dk", "nrf52840", _io())
    parsed = yaml.safe_load(text)
    assert parsed["name"] == "nrf52840dk"
    assert parsed["chip"] == "../../configs/chips/nrf52840.yaml"
    assert len(parsed["board_io"]) == 3
    assert {e["peripheral"] for e in parsed["board_io"]} == {"gpio0"}
