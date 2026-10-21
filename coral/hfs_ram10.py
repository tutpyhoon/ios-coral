#!/usr/bin/env python3
"""CORAL phase 10: screen-marked HFS+ root entirely in kernel-managed RAM.

Use only with the exact pinned ios-flame source after coral/stage05.py prepare.
This does not modify persistent storage. Like Phase 09 it executes XNU, can
freeze, and has no automatic restart once the kernel takes control.
"""
from pathlib import Path
import argparse


def replace_one(file: Path, old: str, new: str) -> None:
    s = file.read_text()
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f"{file}: expected 1 occurrence, got {count}: {old!r}")
    file.write_text(s.replace(old, new))


def prepare(root: Path) -> None:
    f = root / "flame"
    probe = f / "probe.c"
    replace_one(probe, 'line("PIXEL 4 XL / CORAL - XNU TEST 05");',
                'line("PIXEL 4 XL / CORAL - HFS ROOT 10");')
    replace_one(probe, 'line("JUMPING TO XNU - CAPTURE SCREEN");\n            wait_seconds(2);',
                'line("16 MIB HFS+ ROOT IN RAM ONLY");\n'
                '            line("NO UFS OR PHONE STORAGE");\n'
                '            line("XNU ENTRY IN 10 SECONDS");\n'
                '            wait_seconds(10);\n'
                '            line("JUMPING TO XNU - CAPTURE SCREEN");\n'
                '            wait_seconds(2);')
    builder = f / "build.sh"
    replace_one(builder, '05) test -f "${2:-}" ;;', '05|10) test -f "${2:-}" ;;')
    replace_one(builder, '[01|02|03|04|05 PAYLOAD|06]',
                '[01|02|03|04|05 PAYLOAD|06|10 PAYLOAD]')
    replace_one(builder, 'if [[ "$mode" == 05 ]]; then flags+=(-DPROBE_KERNEL); fi',
                'if [[ "$mode" == 05 || "$mode" == 10 ]]; then flags+=(-DPROBE_KERNEL); fi')
    replace_one(builder, 'if [[ "$mode" == 05 ]]; then python3 embed.py "$2"; fi',
                'if [[ "$mode" == 05 || "$mode" == 10 ]]; then python3 embed.py "$2"; fi')
    checker = f / "check.py"
    replace_one(checker, 'choices=["01", "02", "03", "04", "05", "06"]',
                'choices=["01", "02", "03", "04", "05", "06", "10"]')
    replace_one(checker, 'if mode == "05":', 'if mode in ("05", "10"):')
    print("PASS: CORAL Phase 10 HFS+ RAM-root source instrumentation staged")
    print("NOTE: the 1 GiB RAM window remains incompletely characterized")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    prepare(parser.parse_args().source.resolve())
