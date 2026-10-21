#!/usr/bin/env python3
"""Derive a *non-executing* Phase 05 runtime preflight from pinned Flame source.

Run only after coral/stage05.py prepare. Mode 07 checks the live boot
environment and payload structure but NEVER copies segments to candidate RAM,
calls the XNU entry point, accesses UFS, or writes any Android partition.
The normal Phase 05 experimental image remains unchanged.
"""
from pathlib import Path
import argparse


def replace_once(path: Path, old: str, new: str) -> None:
    content = path.read_text()
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one replacement, found {count}: {old!r}")
    path.write_text(content.replace(old, new))


def prepare(root: Path) -> None:
    flame = root / "flame"
    probe = flame / "probe.c"
    replace_once(probe,
                 'line("PIXEL 4 XL / CORAL - XNU TEST 05");',
                 'line("PIXEL 4 XL / CORAL - PREFLIGHT 07");')
    original = """            line("COPYING KERNEL AND DEVICE TREE");
            payload_materialize(payload, &plan, FLAME_RAM_BASE);
            line("JUMPING TO XNU - CAPTURE SCREEN");
            wait_seconds(2);
            __asm__ volatile("dsb sy; ic iallu; dsb sy; isb" ::: "memory");
            ((void (*)(uint64_t))(uintptr_t)(FLAME_RAM_BASE + plan.entry))(FLAME_RAM_BASE + plan.args);
            line("XNU RETURNED UNEXPECTEDLY");"""
    replacement = """#ifdef PROBE_PREFLIGHT_ONLY
            line("RUNTIME CHECKS AND PAYLOAD PASS");
            line("NO XNU COPY OR JUMP PERFORMED");
            line("NOT CLEARED FOR XNU EXECUTION");
#else
""" + original + """
#endif"""
    replace_once(probe, original, replacement)

    build = flame / "build.sh"
    replace_once(build, '05) test -f "${2:-}" ;;', '05|07) test -f "${2:-}" ;;')
    replace_once(build,
                 'if [[ "$mode" == 05 ]]; then flags+=(-DPROBE_KERNEL); fi',
                 'if [[ "$mode" == 05 || "$mode" == 07 ]]; then flags+=(-DPROBE_KERNEL); fi\n'
                 'if [[ "$mode" == 07 ]]; then flags+=(-DPROBE_PREFLIGHT_ONLY); fi')
    replace_once(build,
                 'if [[ "$mode" == 05 ]]; then python3 embed.py "$2"; fi',
                 'if [[ "$mode" == 05 || "$mode" == 07 ]]; then python3 embed.py "$2"; fi')
    replace_once(build,
                 '[01|02|03|04|05 PAYLOAD|06]',
                 '[01|02|03|04|05 PAYLOAD|06|07 PAYLOAD]')

    check = flame / "check.py"
    replace_once(check,
                 'choices=["01", "02", "03", "04", "05", "06"]',
                 'choices=["01", "02", "03", "04", "05", "06", "07"]')
    replace_once(check, 'if mode == "05":', 'if mode in ("05", "07"):')
    print("PASS: separate CORAL mode 07; payload preflight without copy or XNU execution")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    prepare(args.source.resolve())
