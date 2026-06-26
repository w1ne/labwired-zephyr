#!/usr/bin/env python3
"""Derive a LabWired ``system.yaml`` from a Zephyr merged devicetree.

The per-board manual tax in LabWired is the ``board_io`` block — which GPIO pins
are the user LEDs and buttons. Zephyr already describes exactly that, per board, in
its devicetree (``gpio-leds`` / ``gpio-keys`` nodes), so we derive it instead of
hand-authoring it. This is the breadth multiplier: every Zephyr board's DTS becomes
a LabWired system manifest for free.

We parse with Zephyr's own devicetree library (``python-devicetree``'s ``dtlib``) —
the canonical parser — rather than re-implementing DTS. Input is the fully-merged
devicetree (``build/zephyr/zephyr.dts``); the SoC is passed in with ``--chip`` (it
is known when you pick the board), and the board IO is read from the tree.

    dts_to_system.py build/zephyr/zephyr.dts --chip nrf52840 --name nrf52840dk

Emits ``system.yaml`` text on stdout.
"""
import argparse
import os
import struct
import sys
from pathlib import Path

try:
    from devicetree import dtlib
except ModuleNotFoundError:  # pragma: no cover - environment fallback
    # Zephyr ships python-devicetree in-tree but does not always pip-install it
    # into the west venv. Ride the bundled copy via $ZEPHYR_BASE so derivation
    # works in any west environment with no extra install.
    _zb = os.environ.get("ZEPHYR_BASE")
    _bundled = Path(_zb) / "scripts" / "dts" / "python-devicetree" / "src" if _zb else None
    if _bundled and (_bundled / "devicetree" / "dtlib.py").exists():
        sys.path.insert(0, str(_bundled))
    from devicetree import dtlib

GPIO_ACTIVE_LOW = 1 << 0  # Zephyr GPIO flag bit 0


def _has_compatible(node, compat: str) -> bool:
    prop = node.props.get("compatible")
    return prop is not None and compat in prop.to_strings()


def _peripheral_name(node) -> str:
    """The LabWired peripheral id for a controller node: its first DTS label
    (e.g. ``gpio0``), falling back to the node name without its unit address."""
    if node.labels:
        return node.labels[0]
    return node.name.split("@", 1)[0]


def _io_from_group(dt, group, kind: str, signal: str):
    """Yield board_io dicts for each child of a gpio-leds / gpio-keys group."""
    for child in group.nodes.values():
        gpios = child.props.get("gpios")
        if gpios is None:
            continue
        # gpios is a phandle-array <&controller pin flags ...>; dtlib resolves the
        # &label to the controller's phandle in the raw value, so unpack big-endian
        # u32s directly (to_nums() rejects phandle-bearing properties).
        raw = gpios.value
        if len(raw) < 8:
            continue
        words = struct.unpack(f">{len(raw) // 4}I", raw)
        controller = dt.phandle2node.get(words[0])
        if controller is None:
            continue
        flags = words[2] if len(words) >= 3 else 0
        ident = child.labels[0] if child.labels else child.name.split("@", 1)[0]
        yield {
            "id": ident,
            "kind": kind,
            "peripheral": _peripheral_name(controller),
            "pin": words[1],
            "signal": signal,
            "active_high": (flags & GPIO_ACTIVE_LOW) == 0,
        }


def derive_board_io(dt: "dtlib.DT") -> list:
    """All user LED/button IO declared in the devicetree, sorted for stable output."""
    io = []
    for node in dt.node_iter():
        if _has_compatible(node, "gpio-leds"):
            io.extend(_io_from_group(dt, node, "led", "output"))
        elif _has_compatible(node, "gpio-keys"):
            io.extend(_io_from_group(dt, node, "button", "input"))
    io.sort(key=lambda e: (e["kind"], e["peripheral"], e["pin"]))
    return io


def _bus_kind(parent) -> str:
    """The bus a controller node sits on, by node name (i2c@.. / spi@..). '' if not a bus."""
    base = parent.name.split("@", 1)[0]
    if base.startswith("i2c"):
        return "i2c"
    if base.startswith("spi"):
        return "spi"
    return ""


def _enabled(node) -> bool:
    status = node.props.get("status")
    return status is None or status.to_string() == "okay"


def derive_external_devices(dt: "dtlib.DT") -> list:
    """Off-chip, bus-connected devices (I2C/SPI sensors, displays, flash, …).

    These are the child nodes of an enabled i2c/spi controller — the parts that
    automatic DTS->sim converters like dts2repl SILENTLY DROP. Riding them is the
    differentiation: a device's verdict can cover its real sensors, not just the SoC.
    Emits `type` from the compatible's model, `connection` = the bus controller, and
    the I2C address / SPI chip-select from `reg`.
    """
    devices = []
    for node in dt.node_iter():
        parent = node.parent
        if parent is None:
            continue
        bus = _bus_kind(parent)
        if not bus or not _enabled(parent) or not _enabled(node):
            continue
        compat = node.props.get("compatible")
        reg = node.props.get("reg")
        if compat is None or reg is None:
            continue
        addr = reg.to_nums()[0]
        connection = parent.labels[0] if parent.labels else parent.name.split("@", 1)[0]
        ident = node.labels[0] if node.labels else node.name.split("@", 1)[0]
        dev_type = compat.to_strings()[0].split(",")[-1]  # "bosch,bme280" -> "bme280"
        config = {"i2c_addr": hex(addr)} if bus == "i2c" else {"cs": addr}
        devices.append(
            {"id": ident, "type": dev_type, "connection": connection, "config": config}
        )
    devices.sort(key=lambda d: (d["connection"], d["id"]))
    return devices


def to_system_yaml(
    name: str, chip: str, board_io: list, external_devices: list = None, chip_ref: str = None
) -> str:
    external_devices = external_devices or []
    # The emitted ``chip:`` is resolved relative to the system file's own
    # directory by LabWired. The default sibling path works when the system
    # lives in configs/systems; a derived system written elsewhere (e.g. a temp
    # dir at run time) needs an explicit, usually absolute, ``chip_ref``.
    chip_value = chip_ref if chip_ref else f"../../configs/chips/{chip}.yaml"
    lines = [
        f"# LabWired system manifest — derived from Zephyr devicetree for {name}",
        f'name: "{name}"',
        f'chip: "{chip_value}"',
    ]
    if not external_devices:
        lines.append("external_devices: []")
    else:
        lines.append("external_devices:")
        for dvc in external_devices:
            lines.append(f'  - id: "{dvc["id"]}"')
            lines.append(f'    type: "{dvc["type"]}"')
            lines.append(f'    connection: "{dvc["connection"]}"')
            cfg = dvc["config"]
            if cfg:
                lines.append("    config:")
                for k, v in cfg.items():
                    rendered = f'"{v}"' if isinstance(v, str) else v
                    lines.append(f"      {k}: {rendered}")
            else:
                lines.append("    config: {}")
    if not board_io:
        lines.append("board_io: []")
    else:
        lines.append("board_io:")
        for e in board_io:
            lines.append(f'  - id: "{e["id"]}"')
            lines.append(f'    kind: "{e["kind"]}"')
            lines.append(f'    peripheral: "{e["peripheral"]}"')
            lines.append(f'    pin: {e["pin"]}')
            lines.append(f'    signal: "{e["signal"]}"')
            lines.append(f'    active_high: {"true" if e["active_high"] else "false"}')
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Derive a LabWired system.yaml from a Zephyr merged devicetree.")
    ap.add_argument("dts", help="path to the merged devicetree (build/zephyr/zephyr.dts)")
    ap.add_argument("--chip", required=True, help="LabWired SoC id (e.g. nrf52840)")
    ap.add_argument("--name", help="system name (defaults to the chip id)")
    ap.add_argument(
        "--chip-ref",
        help="verbatim value for the system's chip: field (e.g. an absolute path "
        "to the chip.yaml); defaults to ../../configs/chips/<chip>.yaml",
    )
    args = ap.parse_args(argv)

    dt = dtlib.DT(args.dts)
    board_io = derive_board_io(dt)
    external_devices = derive_external_devices(dt)
    sys.stdout.write(
        to_system_yaml(
            args.name or args.chip, args.chip, board_io, external_devices, args.chip_ref
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
