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
import struct
import sys

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


def to_system_yaml(name: str, chip: str, board_io: list) -> str:
    lines = [
        f"# LabWired system manifest — derived from Zephyr devicetree for {name}",
        f'name: "{name}"',
        f'chip: "../../configs/chips/{chip}.yaml"',
        "external_devices: []",
    ]
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
    args = ap.parse_args(argv)

    dt = dtlib.DT(args.dts)
    board_io = derive_board_io(dt)
    sys.stdout.write(to_system_yaml(args.name or args.chip, args.chip, board_io))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
