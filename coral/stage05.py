#!/usr/bin/env python3
"""Prepare a pinned storage-free XNU/boot-image bring-up profile for Pixel 4 XL.

Only transforms a *fresh* checkout of the pinned upstream ios-flame revision.
The development kernel still uses the upstream SWEET-derived bare-minimum
software profile; it is NOT the Phase 22 CORAL kernel and cannot run iOS apps.
The compatibility profile is temporary until a dedicated CORAL minimal
machine config is audited.

No phone or storage operations. Fail closed on unexpected upstream changes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

FLAME_COMMIT = "b91463ab1ef083f81f6c3393593385aa996ceaf0"
WIDTH, HEIGHT, STRIDE = 1440, 3040, 5760
FRAMEBUFFER = 0x9C400000
FB_RESERVE = 0x02400000
MEM_START, MEM_SIZE = 0x100000000, 0x40000000


def replace_once(path: Path, old: str, new: str, count: int = 1) -> None:
    original = path.read_text()
    found = original.count(old)
    if found != count:
        raise RuntimeError(f"{path}: wanted {count} occurrence(s) of {old!r}, saw {found}")
    path.write_text(original.replace(old, new))


def substitutions(root: Path) -> None:
    patch = root / "flame/patches/0099-flame-early-console.patch"
    # Adapt the actual XNU bootstrap and late framebuffer mappings, not only
    # the standalone console diagnostic. One 32 MiB L2 region is sufficient
    # for the observed 16.7 MiB contiguous viewport.
    # Modify only NEW lines in Flame's 0099 patch. Context lines must stay
    # byte-for-byte identical until after the patch has applied to XNU.
    # The three retained context values are corrected by postpatch05.py.
    changes = [
        ("0x9c400000 + 2248 * 4320", "0x9c400000 + 3008 * 5760", 1),
        ("1080 * 2280 * 4", "1440 * 3040 * 4", 2),
        ("#define EARLY_HEIGHT 2280u", "#define EARLY_HEIGHT 3040u", 1),
        ("'google,flame'", "'google,coral'", 1),
        ('strlcpy(name, "flame",', 'strlcpy(name, "coral",', 1),
        ('strlcpy(name, "Google Pixel 4",', 'strlcpy(name, "Google Pixel 4 XL",', 1),
    ]
    for old, new, count in changes:
        replace_once(patch, old, new, count)

    stage = root / "flame/stage_kernel.py"
    replace_once(stage, "'google,flame'", "'google,coral'")
    replace_once(stage, '"#define EARLY_HEIGHT 2280u"', '"#define EARLY_HEIGHT 3040u"')

    adt = root / "flame/mkadt.py"
    replace_once(adt, 'cstr("google,flame")', 'cstr("google,coral")')
    replace_once(adt, '"Google Pixel 4"', '"Google Pixel 4 XL"')
    replace_once(adt, '"flame-early-shim"', '"coral-early-shim"')
    for name, old, new in (("width", 1080, WIDTH), ("height", 2280, HEIGHT),
                           ("stride", 4320, STRIDE)):
        replace_once(adt, f'("{name}", u32({old}))', f'("{name}", u32({new}))')

    pack = root / "flame/pack_kernel.py"
    replace_once(pack, "b'Google Pixel 4\\0'", "b'Google Pixel 4 XL\\0'")
    replace_once(pack, "b'google,flame'", "b'google,coral'")

    probe = root / "flame/probe.c"
    replace_once(probe, "#define WIDTH 1080U", "#define WIDTH 1440U")
    replace_once(probe, "#define HEIGHT 2280U", "#define HEIGHT 3040U")
    lines = probe.read_text()
    if lines.count("PIXEL 4 / FLAME") < 5:
        raise RuntimeError("Changed upstream probe banners")
    probe.write_text(lines.replace("PIXEL 4 / FLAME", "PIXEL 4 XL / CORAL"))

    loader = root / "flame/loader.c"
    for old, new in (
        ("ba->video.stride = 4320;", "ba->video.stride = 5760;"),
        ("ba->video.width = 1080;", "ba->video.width = 1440;"),
        ("ba->video.height = 2280;", "ba->video.height = 3040;"),
    ):
        replace_once(loader, old, new)
    replace_once(root / "flame/check_loader.py",
                 "0x9c400000, 1, 4320, 1080, 2280, 32",
                 "0x9c400000, 1, 5760, 1440, 3040, 32")
    replace_once(root / "flame/check_mmu.py", "1080 * 2280 * 4", "1440 * 3040 * 4", 2)
    replace_once(root / "flame/mmu.c", "fb_size > 0x1000000", "fb_size > 0x1200000")
    builder = root / "flame/build.sh"
    replace_once(builder, "experimental/flame/flame", "experimental/coral/coral")
    replace_once(builder, "666c616d652d70726f62652d3031",
                 "636f72616c2d70726f62652d3031")

    # Geometry fits the live splash reservation and never crosses a 32MiB
    # framebuffer L2 block boundary. The actual runtime stride and FDT must
    # also be independently checked before a kernel image is booted.
    viewport = STRIDE * HEIGHT
    assert STRIDE >= WIDTH * 4 and viewport <= FB_RESERVE
    assert (FRAMEBUFFER & ~0x1ffffff) == ((FRAMEBUFFER + viewport - 1) & ~0x1ffffff)
    assert MEM_START == 0x100000000 and MEM_START + MEM_SIZE == 0x140000000
    (root / "flame/coral-profile.json").write_text(json.dumps({
        "source_commit": FLAME_COMMIT,
        "target": "Pixel 4 XL / coral",
        "kernel_config": "SWEET-derived minimal Pixel compatibility profile",
        "kernel_boot_executed": False,
        "ram": {"base": hex(MEM_START), "size": hex(MEM_SIZE)},
        "splash": {"base": hex(FRAMEBUFFER), "reserved_size": hex(FB_RESERVE),
                   "width": WIDTH, "height": HEIGHT,
                   "assumed_stride": STRIDE, "stride_independently_verified": False},
        "storage": "No UFS or persistent root filesystem included"
    }, indent=2) + "\n")
    print("Prepared pinned CORAL Phase 05 XNU compatibility profile")
    print("STOP: output is a source profile, not a hardware-cleared boot image")


def verify_kernel_source(root: Path, checkout: Path) -> None:
    expected = {
        "osfmk/arm64/start.s": [
            "Lsflame_map_fb_page:", "0x9c400000 + 3008 * 5760",
            "1440 * 3040 * 4"
        ],
        "osfmk/arm64/sweet_early.c": [
            "#define EARLY_WIDTH 1440u", "#define EARLY_HEIGHT 3040u",
            "#define EARLY_STRIDE (5760u / 4)", "FLAME FINAL FB TRANSLATION FAILED"
        ],
        "osfmk/arm64/arm_vm_init.c": [
            "flame_fb_l3", "1440 * 3040 * 4", "kvtophys((vm_offset_t)flame_fb_l3)"
        ],
        "iokit/KernelConfigTables.cpp": ["'google,coral'"],
        "iokit/Kernel/arm/SweetPlatformExpert.cpp": ['strlcpy(name, "coral",'],
    }
    for name, needles in expected.items():
        source = (root / name).read_text()
        for needle in needles:
            if needle not in source:
                raise RuntimeError(f"{name}: missing CORAL source guard {needle}")
    if (root / "bsd/dev/sweet_ufs.c").exists():
        raise RuntimeError("UFS source detected in supposedly storage-free source profile")
    # The underlying Flame verifier guards providers, mockfs and framebuffer
    # table placement. Import it from the modified pinned upstream checkout.
    import sys
    sys.path.insert(0, str(checkout / "flame"))
    from stage_kernel import verify
    verify(root)
    print("PASS: CORAL geometry/identity, early console and no UFS source")


def install_hook(checkout: Path) -> None:
    """Run the strict three-token postpatch only AFTER 0099 applies."""
    path = checkout / "dxb/build.sh"
    script = path.read_text()
    anchor = '        done\n        cd "${WORK_DIR}"\n    fi'
    if script.count(anchor) != 1:
        raise RuntimeError("Cannot locate pinned build patch-loop tail")
    injected = ('        done\n'
                '        python3 "${GITHUB_WORKSPACE}/coral/postpatch05.py" "${WORK_DIR}/xnu"\n'
                '        cd "${WORK_DIR}"\n    fi')
    path.write_text(script.replace(anchor, injected))
    print("PASS: XNU build will apply CORAL postpatch after validated 0099")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("prepare", "verify-source", "hook"))
    p.add_argument("upstream_checkout", type=Path)
    args = p.parse_args()
    root = args.upstream_checkout.resolve()
    if args.command == "prepare":
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        if sha != FLAME_COMMIT:
            raise RuntimeError(f"Refusing unpinned upstream source: {sha}")
        substitutions(root)
    elif args.command == "hook":
        install_hook(root)
    else:
        verify_kernel_source(root / "dxb/xnu" if (root / "dxb/xnu").exists() else root, root)


if __name__ == "__main__":
    main()
