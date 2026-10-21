#!/usr/bin/env python3
"""CORAL 09: instrument a first RAM-only PID 1 bring-up image.

Transform an already CORAL-prepared pinned ios-flame checkout. The source-built
mockfs binary is embedded in RAM, never read from or written to internal UFS.
This mode is separate from XNU entry 08 and never changes its generated image.
"""
from pathlib import Path
import argparse


def replace_once(path: Path, old: str, new: str):
    s = path.read_text()
    found = s.count(old)
    if found != 1:
        raise RuntimeError(f"{path}: expected exactly 1 occurrence, found {found}: {old!r}")
    path.write_text(s.replace(old, new))


def prepare(root: Path):
    flame = root / "flame"
    p = flame / "probe.c"
    replace_once(p, 'line("PIXEL 4 XL / CORAL - XNU TEST 05");',
                 'line("PIXEL 4 XL / CORAL - RAM PID1 09");')
    replace_once(p, 'line("JUMPING TO XNU - CAPTURE SCREEN");\n            wait_seconds(2);',
                 'line("RAM ROOT: STATIC INIT, NO UFS");\n'
                 '            line("XNU ENTRY IN 10 SECONDS");\n'
                 '            wait_seconds(10);\n'
                 '            line("JUMPING TO XNU - CAPTURE SCREEN");\n'
                 '            wait_seconds(2);')
    b = flame / "build.sh"
    replace_once(b, '05) test -f "${2:-}" ;;', '05|09) test -f "${2:-}" ;;')
    replace_once(b, '[01|02|03|04|05 PAYLOAD|06]',
                 '[01|02|03|04|05 PAYLOAD|06|09 PAYLOAD]')
    replace_once(b, 'if [[ "$mode" == 05 ]]; then flags+=(-DPROBE_KERNEL); fi',
                 'if [[ "$mode" == 05 || "$mode" == 09 ]]; then flags+=(-DPROBE_KERNEL); fi')
    replace_once(b, 'if [[ "$mode" == 05 ]]; then python3 embed.py "$2"; fi',
                 'if [[ "$mode" == 05 || "$mode" == 09 ]]; then python3 embed.py "$2"; fi')
    c = flame / "check.py"
    replace_once(c, 'choices=["01", "02", "03", "04", "05", "06"]',
                 'choices=["01", "02", "03", "04", "05", "06", "09"]')
    replace_once(c, 'if mode == "05":', 'if mode in ("05", "09"):')
    print("PASS: RAM-only 09 probe instrumentation prepared")
    print("REMINDER: host checks cannot prove actual XNU/userland execution or device safety")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    prepare(ap.parse_args().source.resolve())
