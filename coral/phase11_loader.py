#!/usr/bin/env python3
"""CORAL Phase11: separate temporary-boot loader display for RAM-only child test.

Compile a Phase11-specific probe using the pinned loader only after the
QEMU test passes. No UFS driver, persistent partition write or flash.
"""
from pathlib import Path
import argparse

def once(path, old, new):
    body=path.read_text()
    n=body.count(old)
    if n!=1:
        raise RuntimeError(f"{path}: expected 1, got {n}: {old!r}")
    path.write_text(body.replace(old,new))

def main(root):
    f=root/"flame"
    p=f/"probe.c"
    once(p, 'line("PIXEL 4 XL / CORAL - XNU TEST 05");',
         'line("PIXEL 4 XL / CORAL - CHILD EXEC 11");')
    once(p,'line("JUMPING TO XNU - CAPTURE SCREEN");\n            wait_seconds(2);',
         'line("RAM HFS+ - FORK/EXEC/WAIT4");\n'
         '            line("NO UFS OR ANDROID WRITES");\n'
         '            line("XNU ENTRY IN 10 SECONDS");\n'
         '            wait_seconds(10);\n'
         '            line("JUMPING TO XNU - CAPTURE SCREEN");\n'
         '            wait_seconds(2);')
    b=f/"build.sh"
    once(b, '05) test -f "${2:-}" ;;', '05|11) test -f "${2:-}" ;;')
    once(b, '[01|02|03|04|05 PAYLOAD|06]', '[01|02|03|04|05 PAYLOAD|06|11 PAYLOAD]')
    once(b, 'if [[ "$mode" == 05 ]]; then flags+=(-DPROBE_KERNEL); fi',
         'if [[ "$mode" == 05 || "$mode" == 11 ]]; then flags+=(-DPROBE_KERNEL); fi')
    once(b, 'if [[ "$mode" == 05 ]]; then python3 embed.py "$2"; fi',
         'if [[ "$mode" == 05 || "$mode" == 11 ]]; then python3 embed.py "$2"; fi')
    c=f/"check.py"
    once(c, 'choices=["01", "02", "03", "04", "05", "06"]',
         'choices=["01", "02", "03", "04", "05", "06", "11"]')
    once(c, 'if mode == "05":', 'if mode in ("05", "11"):')
    print("PASS: Phase 11 loader instrumentation prepared; experimental XNU boot")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("source",type=Path)
    main(p.parse_args().source.resolve())
