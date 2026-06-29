"""The exported CI must actually wire the full loop, not a stub."""
from pathlib import Path
import yaml

T = Path(__file__).resolve().parent.parent / "export/template/zephyr-bme280"


def test_west_pins_zephyr_v37_and_module():
    m = yaml.safe_load((T / "west.yml").read_text())["manifest"]
    projects = {p["name"]: p for p in m["projects"]}
    assert projects["zephyr"]["revision"] == "v3.7.0"
    assert "labwired-zephyr-dts" in projects


def test_ci_runs_full_loop():
    ci = yaml.safe_load((T / ".github/workflows/ci.yml").read_text())
    jobs = ci["jobs"]
    assert "build-and-sim" in jobs and "converter-tests" in jobs
    steps = jobs["build-and-sim"]["steps"]
    blob = yaml.safe_dump(steps)
    assert "zephyrproject-rtos/action-zephyr-setup" in blob
    assert "labwired-core/releases/download" in blob          # downloads the binary
    assert "twister_smoke.sh" in blob                          # build+sim+score
    assert "app/labwired/chips" in blob or "application/labwired/chips" in blob


def test_ci_pins_labwired_binary_version():
    ci = (T / ".github/workflows/ci.yml").read_text()
    assert "labwired-v0.17.3-linux-x86_64.tar.gz" in ci
