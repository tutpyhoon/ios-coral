#!/usr/bin/env python3
"""Adapt the pinned Pixel emulator to CORAL Phase 11's fork/exec/wait result.
Fails closed if the upstream simulator text changes.
No kernel patch, storage access, or device access.
"""
import argparse
from pathlib import Path

def replace_once(file, needle, replacement):
    body=file.read_text()
    n=body.count(needle)
    if n!=1:
        raise ValueError(f"{file}: expected one source guard, found {n}: {needle!r}")
    file.write_text(body.replace(needle,replacement))

def main(root):
    sim=root/"flame/qemu.py"
    replace_once(sim,
                 "qemu.FB_BASE, qemu.FB_H = 0x9c400000, 2280",
                 "qemu.FB_BASE, qemu.FB_W, qemu.FB_H = 0x9c400000, 1440, 3040\nqemu.FB_STRIDE = 5760")
    replace_once(sim,
                 "        result.update(screen_milestones(screen))",
                 """        result.update(screen_milestones(screen))
        # Snapshot-only markers, separately counted to prevent false positives
        # from the old Phase 10 PID1/HFS+ success criteria.
        observed = ''.join(screen.splitlines())
        result['coral11_parent_active'] = 'CORAL11: PID1 HFS+ root active' in observed
        result['coral11_fork_done'] = 'CORAL11: fork succeeded, waiting for child' in observed
        result['coral11_child_exec'] = 'CORAL11: child exec succeeded' in observed
        result['coral11_child_exit0'] = 'CORAL11: child exited status 0' in observed
        result['coral11_parent_alive'] = 'CORAL11: PID1 still alive' in observed
        result['coral11_error'] = 'CORAL11 ERROR:' in observed""")
    replace_once(sim,
                 """        if args.hfs_root:
            expected_progress = (expected_progress and result['hfs_mounted'] and
                                 result['filesystem_read_verified'] and not result['filesystem_read_failed'])""",
                 """        if args.hfs_root:
            expected_progress = (result['hfs_mounted'] and result['coral11_parent_active'] and
                                 result['coral11_fork_done'] and result['coral11_child_exec'] and
                                 result['coral11_child_exit0'] and result['coral11_parent_alive'] and
                                 not result['coral11_error'])""")
    print("PASS: Phase11 QEMU criteria require HFS mount, child exec, exit=0, parent alive")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("source",type=Path)
    main(ap.parse_args().source.resolve())
