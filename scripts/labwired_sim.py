"""Core logic shared by the LabWired ``west simulate`` command and the
``labwired`` ZephyrBinaryRunner.

Deliberately pure Python with no Zephyr or west imports, so it is unit-testable
on its own and has a single implementation of board resolution and CLI
assembly. The two front ends (the west extension command and the runner) are
thin shims over the functions here.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Zephyr's boot + a little app output needs far more than the CLI's 20000-step
# default; a few million steps reaches main() and the first console writes with
# room to spare while still terminating a hung run.
DEFAULT_MAX_STEPS = 5_000_000

_BOARD_TARGET_ALIASES = {
    "nrf52840dk_nrf52840": "nrf52840dk/nrf52840",
    "nrf52dk_nrf52832": "nrf52dk/nrf52832",
    "xiao_ble_nrf52840": "xiao_ble/nrf52840",
    "xiao_ble_nrf52840_sense": "xiao_ble/nrf52840/sense",
    "rpi_pico_rp2040": "rpi_pico/rp2040",
    "rpi_pico_rp2040_w": "rpi_pico/rp2040/w",
    "esp32_devkitc_wroom_esp32_procpu": "esp32_devkitc_wroom/esp32/procpu",
}


class LabwiredError(Exception):
    """A user-facing error (bad board, missing file) — message is shown as-is."""


def normalize_board_target(board: str) -> str:
    """Normalize known Zephyr board-target spellings across releases."""
    return _BOARD_TARGET_ALIASES.get(board, board)


def load_board_map(path: os.PathLike | str) -> dict[str, str]:
    """Parse ``boards.map`` into ``{board_target: system_filename}``.

    The format is intentionally a tiny ``key: value`` subset (no YAML
    dependency): blank lines and ``#`` comments are ignored, everything else is
    split on the first colon.
    """
    mapping: dict[str, str] = {}
    text = Path(path).read_text(encoding="utf-8")
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise LabwiredError(f"{path}:{lineno}: expected 'board: system.yaml', got {raw!r}")
        board, system = line.split(":", 1)
        board, system = normalize_board_target(board.strip()), system.strip()
        if not board or not system:
            raise LabwiredError(f"{path}:{lineno}: empty board or system in {raw!r}")
        mapping[board] = system
    return mapping


def read_board_target(build_dir: os.PathLike | str) -> str:
    """Read the qualified board target (e.g. ``nrf52840dk/nrf52840``) from a
    finished build's ``zephyr/.config``. Falls back to ``CONFIG_BOARD``."""
    config = Path(build_dir) / "zephyr" / ".config"
    if not config.exists():
        raise LabwiredError(
            f"no Zephyr .config in {build_dir} — build first "
            f"(west build -b <board>) before running the simulator"
        )
    board = board_target = None
    for line in config.read_text(encoding="utf-8").splitlines():
        if line.startswith("CONFIG_BOARD_TARGET="):
            board_target = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("CONFIG_BOARD="):
            board = line.split("=", 1)[1].strip().strip('"')
    result = board_target or board
    if not result:
        raise LabwiredError(f"could not determine the board from {config}")
    return normalize_board_target(result)


def resolve_system(
    board: str,
    board_map: dict[str, str],
    systems_dir: os.PathLike | str | None,
    override: os.PathLike | str | None = None,
) -> Path:
    """Resolve a board target to a LabWired system manifest path.

    ``override`` (a full path) wins; otherwise the board is looked up in the map
    and the filename is joined onto ``systems_dir``.
    """
    if override:
        return Path(override)
    board = normalize_board_target(board)
    system_name = board_map.get(board)
    if not system_name:
        known = ", ".join(sorted(board_map)) or "(empty map)"
        raise LabwiredError(
            f"no LabWired system mapped for board '{board}'. "
            f"Add it to boards.map or pass --system <path>. Known boards: {known}"
        )
    if systems_dir is None:
        raise LabwiredError(
            f"board '{board}' maps to '{system_name}' but no systems directory is set. "
            f"Pass --systems-dir or set LABWIRED_SYSTEMS_DIR to <labwired>/configs/systems, "
            f"or pass --system with a full path."
        )
    return Path(systems_dir) / system_name


def build_argv(
    labwired_bin: os.PathLike | str,
    elf: os.PathLike | str,
    system: os.PathLike | str,
    max_steps: int = DEFAULT_MAX_STEPS,
    extra_args: list[str] | None = None,
) -> list[str]:
    """Assemble the LabWired CLI argv. Pure; this is the contract with the CLI's
    existing ``--firmware``/``--system`` interface."""
    argv = [
        str(labwired_bin),
        "--firmware",
        str(elf),
        "--system",
        str(system),
        "--max-steps",
        str(max_steps),
    ]
    if extra_args:
        argv += list(extra_args)
    return argv


def default_systems_dir() -> str | None:
    """Best-effort systems directory: ``$LABWIRED_SYSTEMS_DIR`` if set."""
    return os.environ.get("LABWIRED_SYSTEMS_DIR")


def default_labwired_bin() -> str:
    """The LabWired binary: ``$LABWIRED_BIN`` if set, else ``labwired`` on PATH."""
    return os.environ.get("LABWIRED_BIN", "labwired")


def simulate(
    *,
    build_dir: os.PathLike | str = "build",
    board_map_path: os.PathLike | str,
    labwired_bin: os.PathLike | str | None = None,
    systems_dir: os.PathLike | str | None = None,
    system_override: os.PathLike | str | None = None,
    elf: os.PathLike | str | None = None,
    board: str | None = None,
    max_steps: int = DEFAULT_MAX_STEPS,
    timeout: float | None = None,
    extra_args: list[str] | None = None,
    capture: bool = False,
) -> tuple[int, str | None]:
    """Resolve everything and run one firmware ELF in LabWired.

    Returns ``(returncode, captured_output_or_None)``. With ``capture=False`` the
    child's stdout/stderr stream straight through (live UART console); with
    ``capture=True`` they are captured and returned (used by the integration
    test). A ``timeout`` that fires is reported as a non-zero return code.
    """
    labwired_bin = labwired_bin or default_labwired_bin()
    systems_dir = systems_dir if systems_dir is not None else default_systems_dir()
    board = board or read_board_target(build_dir)
    elf_path = Path(elf) if elf else Path(build_dir) / "zephyr" / "zephyr.elf"
    if not elf_path.exists():
        raise LabwiredError(f"firmware ELF not found: {elf_path}")
    board_map = load_board_map(board_map_path)
    system = resolve_system(board, board_map, systems_dir, system_override)
    if not Path(system).exists():
        raise LabwiredError(f"LabWired system manifest not found: {system}")

    argv = build_argv(labwired_bin, elf_path, system, max_steps, extra_args)
    try:
        if capture:
            proc = subprocess.run(
                argv, timeout=timeout, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            return proc.returncode, proc.stdout
        proc = subprocess.run(argv, timeout=timeout)
        return proc.returncode, None
    except FileNotFoundError as exc:
        raise LabwiredError(
            f"could not execute LabWired binary '{labwired_bin}': {exc}. "
            f"Pass --labwired-bin or set LABWIRED_BIN."
        ) from exc
    except subprocess.TimeoutExpired:
        return 124, None
