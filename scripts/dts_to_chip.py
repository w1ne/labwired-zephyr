#!/usr/bin/env python3
"""Derive a LabWired ``chip.yaml`` scaffold from a Zephyr merged devicetree.

A chip config's tedious, error-prone part is the peripheral memory map: every
peripheral's base address, register-window size, and interrupt number. Zephyr's
devicetree already carries exactly that, vendor-authoritative, in the ``/soc``
node (``reg`` + ``interrupts``). We extract it so a new SoC's config starts from
the silicon's own description instead of hand transcription from a datasheet.

What we DON'T fabricate is fidelity. The ``type`` field names a LabWired model
implementation; a DTS ``compatible`` only tells us what the peripheral *is*. We
map the compatibles we have faithful models for to their model type, and emit
everything else as ``type: "unmodeled"`` with its ``compatible`` preserved — so
the gap between "declared in the devicetree" and "actually simulated" is visible,
never silently claimed. That modeled/unmodeled frontier is the coverage signal.

The output is a reviewable SCAFFOLD, not a drop-in config: addresses/IRQs are
ready, model types and reset values still want a human (and the validated-models
report) before it earns a verdict.

    dts_to_chip.py build/zephyr/zephyr.dts --chip nrf52840

Emits ``chip.yaml`` text on stdout.
"""
import argparse
import sys

from devicetree import dtlib

# DTS compatible -> LabWired model type. "{chip}" is filled with --chip, so a
# family shares one entry; a bare string is a chip-independent generic model.
# Only list compatibles backed by a faithful LabWired model — anything absent is
# emitted as "unmodeled" on purpose. Extend as models land.
_COMPATIBLE_TYPE = {
    "nordic,nrf-uarte": "{chip}_uart",
    "nordic,nrf-uart": "{chip}_uart",
    "nordic,nrf-twim": "{chip}_i2c",
    "nordic,nrf-twi": "{chip}_i2c",
    "nordic,nrf-twis": "{chip}_i2c",
    "nordic,nrf-spim": "{chip}_spi",
    "nordic,nrf-spi": "{chip}_spi",
    "nordic,nrf-spis": "{chip}_spi",
    "nordic,nrf-timer": "{chip}_timer",
    "nordic,nrf-rtc": "{chip}_rtc",
    "nordic,nrf-wdt": "{chip}_watchdog",
    "nordic,nrf-rng": "{chip}_rng",
    "nordic,nrf-temp": "{chip}_temp",
    "nordic,nrf-saadc": "{chip}_saadc",
    "nordic,nrf-gpiote": "{chip}_gpiotasksevents",
    "nordic,nrf-gpio": "gpio",
    "nordic,nrf-clock": "nrf_clock",
}

UNMODELED = "unmodeled"


def _enabled(node) -> bool:
    status = node.props.get("status")
    return status is None or status.to_string() == "okay"


def _model_type(compatibles, chip: str):
    """(type, modeled) for a node's compatible list — first faithful match wins."""
    for compat in compatibles:
        tmpl = _COMPATIBLE_TYPE.get(compat)
        if tmpl is not None:
            return tmpl.format(chip=chip), True
    return UNMODELED, False


def _fmt_size(nbytes: int) -> str:
    """Match the existing config style: whole-KB windows render as "<n>KB"."""
    if nbytes and nbytes % 1024 == 0:
        return f"{nbytes // 1024}KB"
    return hex(nbytes)


def _ident(node) -> str:
    return node.labels[0] if node.labels else node.name.split("@", 1)[0]


def derive_soc_peripherals(dt: "dtlib.DT", chip: str) -> list:
    """Direct children of /soc with a reg window and a compatible, as peripherals.

    Bus *controllers* (i2c0/spi0) are peripherals and are kept; their bus children
    (sensors etc.) are off-chip and handled separately by dts_to_system. Memory
    nodes are skipped. Sorted by base address for stable output.
    """
    soc = dt.root.nodes.get("soc")
    if soc is None:
        return []
    periphs = []
    for node in soc.nodes.values():
        if not _enabled(node):
            continue
        compat = node.props.get("compatible")
        reg = node.props.get("reg")
        if compat is None or reg is None:
            continue
        dt_compat = compat.to_strings()
        nums = reg.to_nums()
        if len(nums) < 2:
            continue
        base, size = nums[0], nums[1]
        model_type, modeled = _model_type(dt_compat, chip)
        entry = {
            "id": _ident(node),
            "type": model_type,
            "base_address": base,
            "size": size,
            "modeled": modeled,
            "compatible": dt_compat[0],
        }
        irq = node.props.get("interrupts")
        if irq is not None:
            irq_nums = irq.to_nums()
            if irq_nums:
                entry["irq"] = irq_nums[0]
        periphs.append(entry)
    periphs.sort(key=lambda p: p["base_address"])
    return periphs


def _resolve_node(prop):
    """A chosen phandle/path property -> its node. Merged zephyr.dts writes the
    bare ``= &flash0`` form (a PATH); overlays may use ``= < &flash0 >`` (PHANDLE)."""
    if prop.type == dtlib.Type.PATH:
        return prop.to_path()
    if prop.type == dtlib.Type.PHANDLE:
        return prop.to_node()
    return None


def _region(dt: "dtlib.DT", chosen_key: str):
    """(base, size) of a chosen memory region (zephyr,flash / zephyr,sram)."""
    chosen = dt.root.nodes.get("chosen")
    if chosen is None or chosen_key not in chosen.props:
        return None
    node = _resolve_node(chosen.props[chosen_key])
    if node is None:
        return None
    reg = node.props.get("reg")
    if reg is None:
        return None
    nums = reg.to_nums()
    if len(nums) < 2:
        return None
    return nums[0], nums[1]


def _cpu_arch_core(dt: "dtlib.DT"):
    """(arch, core) inferred from the first cpu's compatible, or (None, None)."""
    cpus = dt.root.nodes.get("cpus")
    if cpus is None:
        return None, None
    for node in cpus.nodes.values():
        compat = node.props.get("compatible")
        if compat is None:
            continue
        vendor, _, model = compat.to_strings()[0].partition(",")
        arch = "riscv" if "riscv" in model or "riscv" in vendor else vendor
        core = model.rstrip("f") if model.startswith("cortex-") else model
        return arch, core
    return None, None


def to_chip_yaml(chip: str, arch: str, core: str, flash, ram, peripherals: list) -> str:
    modeled = sum(1 for p in peripherals if p["modeled"])
    lines = [
        f"# LabWired chip scaffold — derived from a Zephyr devicetree for {chip}.",
        f"# {modeled}/{len(peripherals)} peripherals mapped to a faithful model; the rest",
        '# are "unmodeled" (declared by the devicetree, not yet simulated). Addresses and',
        "# IRQs are devicetree-authoritative; model types and reset values want review.",
        f'name: "{chip}"',
        f'arch: "{arch}"',
        f'core: "{core}"',
    ]
    if flash is not None:
        lines += ["flash:", f"  base: {hex(flash[0])}", f'  size: "{_fmt_size(flash[1])}"']
    if ram is not None:
        lines += ["ram:", f"  base: {hex(ram[0])}", f'  size: "{_fmt_size(ram[1])}"']
    lines.append("peripherals:")
    for p in peripherals:
        lines.append(f'  - id: "{p["id"]}"')
        lines.append(f'    type: "{p["type"]}"')
        lines.append(f"    base_address: {hex(p['base_address'])}")
        lines.append(f'    size: "{_fmt_size(p["size"])}"')
        if "irq" in p:
            lines.append(f"    irq: {p['irq']}")
        if not p["modeled"]:
            lines.append(f'    compatible: "{p["compatible"]}"  # UNMODELED — needs a LabWired model')
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Derive a LabWired chip.yaml scaffold from a Zephyr merged devicetree.")
    ap.add_argument("dts", help="path to the merged devicetree (build/zephyr/zephyr.dts)")
    ap.add_argument("--chip", required=True, help="LabWired SoC id (e.g. nrf52840)")
    ap.add_argument("--arch", help="override the arch (else inferred from /cpus)")
    ap.add_argument("--core", help="override the core (else inferred from /cpus)")
    args = ap.parse_args(argv)

    dt = dtlib.DT(args.dts)
    arch, core = _cpu_arch_core(dt)
    arch = args.arch or arch or "unknown"
    core = args.core or core or "unknown"
    flash = _region(dt, "zephyr,flash")
    ram = _region(dt, "zephyr,sram")
    peripherals = derive_soc_peripherals(dt, args.chip)
    sys.stdout.write(to_chip_yaml(args.chip, arch, core, flash, ram, peripherals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
