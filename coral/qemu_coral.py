#!/usr/bin/env python3
"""Prepare Coral-specific *host-only* QEMU simulation of pinned ios-flame.

The original upstream emulator assumes Pixel 4 (flame) framebuffer dimensions,
1080x2280, while Coral's measured viewport is 1440x3040. Its boot-args and
framebuffer extraction must agree with the CORAL ADT/early-console geometry.
Run this only after 'python3 coral/stage05.py prepare source'.
Never interacts with phone or UFS.
"""
from pathlib import Path
import argparse


def one(path: Path, old: str, new: str) -> None:
    body=path.read_text()
    count=body.count(old)
    if count != 1:
        raise RuntimeError(f"QEMU source guard failed in {path}: {count} occurrences of {old!r}")
    path.write_text(body.replace(old,new))


def main(root: Path) -> None:
    flame=root / "flame"
    sim=flame / "qemu.py"
    original="qemu.FB_BASE, qemu.FB_H = 0x9c400000, 2280"
    adapted="qemu.FB_BASE, qemu.FB_W, qemu.FB_H = 0x9c400000, 1440, 3040\nqemu.FB_STRIDE = 5760"
    one(sim,original,adapted)
    one(sim, "This substitutes QEMU GIC/timer metadata and treats splash RAM as ordinary",
            "CORAL: QEMU GIC/timer metadata; 1440x3040 splash ordinary RAM.")
    # The last substitution intentionally only affects documentation; runtime
    # dimensions above must also match the CORAL ADT and boot_args geometry.
    profile=(flame/"coral-profile.json").read_text()
    assert '"width": 1440' in profile
    assert '"height": 3040' in profile
    assert '"assumed_stride": 5760' in profile
    assert "qemu.FB_STRIDE = 5760" in sim.read_text()
    print("PASS: QEMU framebuffer / boot-args 1440x3040 @ 5760-byte stride")
    print("SIMULATION ONLY: no physical Pixel/FDT/peripherals or storage access")


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("source",type=Path)
    main(parser.parse_args().source.resolve())
