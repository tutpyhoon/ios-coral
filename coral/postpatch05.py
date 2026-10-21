#!/usr/bin/env python3
"""Post-0099 CORAL viewport corrections, before any XNU compilation.

Run only after the pinned upstream Flame 0099 patch has applied. The original
Flame hunks must remain unchanged where later patches depend on their context.
Fail closed if the expected source shape changes.
"""
from pathlib import Path
import sys


def once(path: Path, old: str, new: str):
    s = path.read_text()
    if s.count(old) != 1:
        raise SystemExit(f"STOP: {path} expected unique post-0099 token {old!r}, got {s.count(old)}")
    path.write_text(s.replace(old, new))


def main(root: Path):
    start = root / "osfmk/arm64/start.s"
    early = root / "osfmk/arm64/sweet_early.c"
    # All other viewport constants are changed in 0099's added lines.
    once(start, "\tmov\t\tx4, #4320", "\tmov\t\tx4, #5760")
    once(early, "#define EARLY_WIDTH 1080u", "#define EARLY_WIDTH 1440u")
    once(early, "#define EARLY_STRIDE (4320u / 4)",
         "#define EARLY_STRIDE (5760u / 4)")
    expected = {
        start: ["0x9c400000 + 3008 * 5760", "1440 * 3040 * 4", "x4, #5760"],
        early: ["#define EARLY_WIDTH 1440u", "#define EARLY_HEIGHT 3040u",
                "#define EARLY_STRIDE (5760u / 4)"],
        root / "osfmk/arm64/arm_vm_init.c": ["1440 * 3040 * 4", "flame_fb_l3"],
        root / "iokit/KernelConfigTables.cpp": ["'google,coral'"],
    }
    for file, values in expected.items():
        data = file.read_text()
        for token in values:
            if token not in data:
                raise SystemExit(f"STOP: {file} expected Coral output token {token!r}")
    if (root / "bsd/dev/sweet_ufs.c").exists():
        raise SystemExit("STOP: unexpected SWEET UFS source included")
    print("PASS: post-0099 CORAL bootstrap stride, early console and identity verified")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: postpatch05.py PATH_TO_PATCHED_XNU")
    main(Path(sys.argv[1]).resolve())
