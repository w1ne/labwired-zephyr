"""Real west discovery + real prebuilt firmware, without a Zephyr SDK build.

CI supplies ZEPHYR_BASE, LABWIRED_BIN and LABWIRED_SYSTEMS_DIR and sets
LABWIRED_REQUIRE_INTEGRATION=1 so a missing input fails instead of skipping.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
HELLO = "Hello World! nrf52840dk/nrf52840"


def run(argv, cwd, env):
    return subprocess.run(argv, cwd=cwd, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          timeout=30)


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    required = {key: os.environ.get(key) for key in
                ("ZEPHYR_BASE", "LABWIRED_BIN", "LABWIRED_SYSTEMS_DIR")}
    missing = [key for key, value in required.items() if not value or not Path(value).exists()]
    if missing:
        message = "integration inputs missing: " + ", ".join(missing)
        if os.environ.get("LABWIRED_REQUIRE_INTEGRATION") == "1":
            pytest.fail(message)
        pytest.skip(message)
    zephyr = Path(required["ZEPHYR_BASE"]).resolve()
    w = tmp_path_factory.mktemp("west-workspace")
    (w / "manifest").mkdir()
    (w / "zephyr").symlink_to(zephyr, target_is_directory=True)
    (w / "labwired-zephyr").symlink_to(REPO, target_is_directory=True)
    (w / "manifest" / "west.yml").write_text(yaml.safe_dump({"manifest": {
        "projects": [
            {"name": "zephyr", "url": "https://github.com/zephyrproject-rtos/zephyr",
             "west-commands": "scripts/west-commands.yml"},
            {"name": "labwired-zephyr", "url": "https://github.com/w1ne/labwired-zephyr",
             "west-commands": "west-commands.yml"},
        ], "self": {"path": "manifest"},
    }}))
    env = dict(os.environ, RUST_LOG="warn", ZEPHYR_BASE=str(zephyr))
    # The tests must not discover unrelated modules in the developer's shell.
    env.pop("ZEPHYR_EXTRA_MODULES", None)
    env.pop("EXTRA_ZEPHYR_MODULES", None)
    west = [sys.executable, "-m", "west"]
    initialized = run(west + ["init", "-l", "manifest"], w, env)
    assert initialized.returncode == 0, initialized.stdout
    build = w / "build"
    (build / "zephyr").mkdir(parents=True)
    (build / "zephyr" / ".config").write_text(
        'CONFIG_BOARD="nrf52840dk"\nCONFIG_BOARD_TARGET="nrf52840dk/nrf52840"\n')
    shutil.copy2(REPO / "tests/fixtures/nrf52840dk_hello_world.elf", build / "zephyr/zephyr.elf")
    (build / "CMakeCache.txt").write_text(f"ZEPHYR_BASE:PATH={zephyr}\n")
    return w, zephyr, west, env


def test_extension_coexists_with_stock_zephyr_and_runs_firmware(workspace):
    w, _, west, env = workspace
    result = run(west + ["labwired-simulate", "--max-steps", "3000000"], w, env)
    assert result.returncode == 0, result.stdout
    assert HELLO in result.stdout
    assert "ignoring project" not in result.stdout


def test_missing_cli_fails_instead_of_reporting_a_successful_simulation(workspace):
    w, _, west, env = workspace
    result = run(west + ["labwired-simulate", "--labwired-bin", str(w / "missing")], w, env)
    assert result.returncode != 0
    assert "missing" in result.stdout


def test_base_module_metadata_still_validates_on_the_selected_zephyr(workspace):
    w, zephyr, _, env = workspace
    code = ("import sys; sys.path.insert(0, sys.argv[1]); import zephyr_module; "
            "assert zephyr_module.process_module(sys.argv[2]) is not None")
    result = run([sys.executable, "-c", code, str(zephyr / "scripts"), str(REPO)], w, env)
    assert result.returncode == 0, result.stdout


@pytest.fixture(scope="module")
def native_workspace(workspace):
    w, zephyr, west, env = workspace
    version_text = (zephyr / "VERSION").read_text()
    version = tuple(int(re.search(rf"VERSION_{part}\s*=\s*(\d+)", version_text)[1])
                    for part in ("MAJOR", "MINOR"))
    if version < (4, 5):
        if os.environ.get("LABWIRED_REQUIRE_NATIVE") == "1":
            pytest.fail("native runner tests require Zephyr 4.5")
        pytest.skip("native runner extra-module discovery requires Zephyr 4.5")
    cmake = shutil.which("cmake")
    assert cmake, "cmake is required to test the actual runner registration"
    script = w / "register-runner.cmake"
    script.write_text('''cmake_minimum_required(VERSION 3.20)
list(APPEND CMAKE_MODULE_PATH "${ZEPHYR_BASE}/cmake/modules")
include(extensions)
set(BOARD_FLASH_RUNNER jlink)
set(BOARD_SIM_RUNNER qemu)
board_finalize_runner_args(jlink)
board_finalize_runner_args(qemu)
include("${LABWIRED_ROOT}/native-runner/CMakeLists.txt")
get_property(runners GLOBAL PROPERTY ZEPHYR_RUNNERS)
file(WRITE "${OUT}" "${runners}\\n${BOARD_FLASH_RUNNER}\\n${BOARD_SIM_RUNNER}\\n")
''')
    registered = w / "registered.txt"
    result = run([cmake, f"-DZEPHYR_BASE={zephyr}", f"-DLABWIRED_ROOT={REPO}",
                  f"-DOUT={registered}", f"-DUSER_CACHE_DIR={w / 'cache'}",
                  f"-DPYTHON_EXECUTABLE={sys.executable}", "-P", str(script)], w, env)
    assert result.returncode == 0, result.stdout
    runner_line, flash_default, sim_default = registered.read_text().splitlines()
    runners = runner_line.split(";")
    assert "labwired" in runners and "jlink" in runners
    assert flash_default == "jlink", "registration must preserve the hardware flash default"
    assert sim_default == "qemu", "registration must preserve an existing simulator default"
    # This is the generated-runner contract, not a newly compiled application.
    (w / "build/zephyr/runners.yaml").write_text(yaml.safe_dump({
        "runners": runners, "flash-runner": flash_default, "sim-runner": sim_default,
        "config": {"board_dir": str(REPO / "boards/labwired/lwnrf52840dk"),
                   "elf_file": "zephyr.elf"},
        "args": {runner: [] for runner in runners},
    }))
    return w, west, dict(env, ZEPHYR_EXTRA_MODULES=str(REPO / "native-runner"))


@pytest.mark.parametrize("command", ["flash", "simulate"])
def test_native_runner_loads_and_runs_real_firmware(native_workspace, command):
    w, west, env = native_workspace
    result = run(west + [command, "--no-rebuild", "-r", "labwired",
                        "--max-steps", "3000000"], w, env)
    assert result.returncode == 0, result.stdout
    assert HELLO in result.stdout
    assert "using runner labwired" in result.stdout


def test_native_runner_propagates_bad_system_failure(native_workspace):
    w, west, env = native_workspace
    result = run(west + ["flash", "--no-rebuild", "-r", "labwired",
                        "--system", str(w / "missing-system.yaml")], w, env)
    assert result.returncode != 0
    assert "manifest not found" in result.stdout
