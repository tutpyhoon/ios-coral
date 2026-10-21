#!/usr/bin/env python3
"""Make a separately named, screen-marked first XNU-entry test for CORAL.

Apply only after stage05.py prepares the pinned ios-flame checkout.
Unlike Phase 05 preflight 07, mode 08 deliberately copies the source-built
kernel to the measured candidate RAM and jumps to its entry point. It may
freeze or reset the device; it is NOT an iOS boot or storage-ready kernel.
"""
from pathlib import Path
import argparse

def once(path: Path, old: str, new: str) -> None:
    s = path.read_text()
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{path}: expected one occurrence of {old!r}, found {n}")
    path.write_text(s.replace(old, new))

def prepare(root: Path) -> None:
    flame = root / "flame"
    probe = flame / "probe.c"
    once(probe, 'line("PIXEL 4 XL / CORAL - XNU TEST 05");',
         'line("PIXEL 4 XL / CORAL - FIRST XNU 08");')
    once(probe,
         'line("JUMPING TO XNU - CAPTURE SCREEN");\n            wait_seconds(2);',
         'line("XNU ENTRY START IN 15 SECONDS");\n'
         '            line("EXPERIMENTAL - MAY FREEZE");\n'
         '            wait_seconds(15);\n'
         '            line("JUMPING TO XNU - CAPTURE SCREEN");\n'
         '            wait_seconds(2);')
    build = flame / "build.sh"
    once(build, '05) test -f "${2:-}" ;;', '05|08) test -f "${2:-}" ;;')
    once(build, '[01|02|03|04|05 PAYLOAD|06]', '[01|02|03|04|05 PAYLOAD|06|08 PAYLOAD]')
    once(build, 'if [[ "$mode" == 05 ]]; then flags+=(-DPROBE_KERNEL); fi',
         'if [[ "$mode" == 05 || "$mode" == 08 ]]; then flags+=(-DPROBE_KERNEL); fi')
    once(build, 'if [[ "$mode" == 05 ]]; then python3 embed.py "$2"; fi',
         'if [[ "$mode" == 05 || "$mode" == 08 ]]; then python3 embed.py "$2"; fi')
    check = flame / "check.py"
    once(check, 'choices=["01", "02", "03", "04", "05", "06"]',
         'choices=["01", "02", "03", "04", "05", "06", "08"]')
    once(check, 'if mode == "05":', 'if mode in ("05", "08"):')
    print("PASS: Phase 08 guarded entry source variant staged")
    print("WARNING: this variant WILL attempt to copy and execute XNU on hardware")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    prepare(ap.parse_args().source.resolve())
