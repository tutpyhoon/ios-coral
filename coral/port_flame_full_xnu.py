#!/usr/bin/env python3
"""Patch a fully applied, PINNED iOS-flame XNU 0124 tree for Pixel 4 XL.

This is a *kernel compilation overlay*, not proof of a working Coral DPU.
Never flash the output. The upstream's 1080x2280 panel register programming
must be independently validated before GPU presentation can be enabled.
Do not use Flame's read/write UFS root to overwrite Coral userdata.
"""
import argparse
from pathlib import Path
import re

FB_W, FB_H, FB_STRIDE = 1440, 3040, 5760
FB_PA, FB_RESERVED = 0x9c400000, 0x2400000
GPU_MAPPED = 0x1200000  # align 17,510,400 up to 18 MiB for 2 MiB GTT blocks


def replace_exact(root, rel, before, after, *, dry_run=False):
    path=root/rel
    s=path.read_text()
    if s.count(before) != 1:
        raise ValueError(f"STOP {rel}: expected exactly one {before!r}, got {s.count(before)}")
    if not dry_run:
        path.write_text(s.replace(before,after))
    return rel


def port(root, *, dry_run=False):
    root=root.resolve(strict=True)
    assert FB_W*FB_H*4 == 17510400
    assert FB_STRIDE%64 == 0
    assert GPU_MAPPED >= FB_STRIDE*FB_H and GPU_MAPPED%0x200000 == 0
    assert GPU_MAPPED<=FB_RESERVED
    changes=[]
    substitutions=(
        ("pexpert/pexpert/arm64/SWEET.h",
         "#define SWEET_EARLY_FB_WIDTH      1080",
         "#define SWEET_EARLY_FB_WIDTH      1440"),
        ("pexpert/pexpert/arm64/SWEET.h",
         "#define SWEET_EARLY_FB_HEIGHT     2280",
         "#define SWEET_EARLY_FB_HEIGHT     3040"),
        ("pexpert/pexpert/arm64/SWEET.h",
         "#define SWEET_EARLY_FB_STRIDE     4320",
         "#define SWEET_EARLY_FB_STRIDE     5760"),
        ("bsd/dev/sweet_a6xx.h",
         "#define A6_FB_SIZE\t\t0xa00000ull",
         "#define A6_FB_SIZE\t\t0x1200000ull"),
        ("bsd/dev/sweet_gpu.c",
         "#define PANEL_W         1080",
         "#define PANEL_W         1440"),
        ("bsd/dev/sweet_gpu.c",
         "#define PANEL_H         2280",
         "#define PANEL_H         3040"),
        ("iokit/Kernel/arm/SweetFramebuffer.cpp",
         "#define SWEET_FB_GPU_ROWBYTES           4352",
         "#define SWEET_FB_GPU_ROWBYTES           5760"),
        ("iokit/Kernel/arm/hid/SweetHID.cpp",
         "#define SWEET_PANEL_W 1080",
         "#define SWEET_PANEL_W 1440"),
        ("iokit/Kernel/arm/hid/SweetHID.cpp",
         "#define SWEET_PANEL_H 2280",
         "#define SWEET_PANEL_H 3040"),
    )
    # Every mutation is guarded against source drift; a failed guard aborts.
    for rel,before,after in substitutions:
        changes.append(replace_exact(root,rel,before,after,dry_run=dry_run))

    # Full Flame contains WRITE(10) storage paths. Our first Coral kernel
    # must deny all media writes, even if someone supplies ufsrw=1.
    # Three independent barriers: low-level CDB submission, write helper,
    # and writable state. These are compile-level guards, not a boot permit.
    ufs_rel = "bsd/dev/sweet_ufs.c"
    changes.append(replace_exact(
        root, ufs_rel,
        "ufs_scsi(const uint8_t *cdb, unsigned cdb_len, uint32_t len, bool write)\n{",
        "ufs_scsi(const uint8_t *cdb, unsigned cdb_len, uint32_t len, bool write)\n"
        "{\n"
        "    /* CORAL_MEDIA_WRITE_FENCE: never submit device write or erase. */\n"
        "    if (write || (cdb_len && (cdb[0] == 0x2a || cdb[0] == 0xaa ||\n"
        "                              cdb[0] == 0x35 || cdb[0] == 0x42)))\n"
        "        return EROFS;",
        dry_run=dry_run))
    changes.append(replace_exact(
        root, ufs_rel, "su.writable = (rw != 0);",
        "su.writable = false; /* CORAL_MEDIA_WRITE_FENCE: ignore ufsrw */",
        dry_run=dry_run))
    changes.append(replace_exact(
        root, ufs_rel,
        "ufs_write_blocks(uint64_t lba, uint32_t count)\n{",
        "ufs_write_blocks(uint64_t lba, uint32_t count)\n"
        "{\n"
        "    /* CORAL_MEDIA_WRITE_FENCE: block direct WRITE(10) helper use. */\n"
        "    return EROFS;",
        dry_run=dry_run))

    # Disable optional Flame RAM log mirror completely. The upstream
    # mirror writes to fixed PA 0x1fe000000, which is not mapped in
    # the 4 GiB QEMU guest and has not been proven safe on Coral.
    # This was the confirmed first QEMU panic at _sweet_log_mirror_start.
    # The ring stays in normal mapped kernel memory (sweet_log_ring).
    changes.append(replace_exact(
        root, ufs_rel,
        "sweet_log_mirror_start(void)\n{\n",
        "sweet_log_mirror_start(void)\n{\n"
        "    /* CORAL_MIRROR_FENCE: unverified high-memory mirror disabled. */\n"
        "    return;\n",
        dry_run=dry_run))

    # The generic QEMU 'virt' machine has no Qualcomm PMIC/SPMI MMIO at
    # 0x0c440000. A post-mirror emulated boot panicked in
    # _sweet_spmi_init+156 on an unmapped read at this physical address.
    # A special opt-in boot argument disables this one hardware probe in
    # QEMU ONLY. The real Coral phone never sets 'coralqemu=1'.
    spmi_rel = "bsd/dev/sweet_spmi.c"
    changes.append(replace_exact(
        root, spmi_rel,
        "#include <IOKit/IOLocks.h>\n",
        "#include <IOKit/IOLocks.h>\n"
        "#include <pexpert/pexpert.h>\n",
        dry_run=dry_run))
    changes.append(replace_exact(
        root, spmi_rel,
        "sweet_spmi_init(void)\n{\n",
        "sweet_spmi_init(void)\n{\n"
        "    int coral_qemu_no_spmi = 0;\n"
        "    (void)PE_parse_boot_argn(\"coralqemu\", &coral_qemu_no_spmi,\n"
        "                            sizeof(coral_qemu_no_spmi));\n"
        "    if (coral_qemu_no_spmi == 1) {\n"
        "        /* CORAL_QEMU_SPMI_FENCE: generic virt has no Qualcomm PMIC. */\n"
        "        printf(\"CORAL QEMU: Qualcomm SPMI MMIO disabled\\n\");\n"
        "        return -1;\n"
        "    }\n",
        dry_run=dry_run))

    # These are bounds checks, *not* an endorsement of the Flame panel
    # register writes. There are panel timing and mixer geometry differences.
    s=(root/"bsd/dev/sweet_gpu.c").read_text()
    for token in ("sweet_gpu_present(", "sweet_display_fit", "PANEL_W", "PANEL_H"):
        if token not in s:
            raise ValueError(f"STOP: missing GPU contract {token!r}")
    s=(root/"bsd/dev/sweet_ufs.c").read_text()
    for token in ("ufs_read_blocks(", "ufs_write_blocks("):
        if token not in s:
            raise ValueError("STOP: full upstream XNU UFS driver not present")
    if not dry_run:
        for marker in ("CORAL_MEDIA_WRITE_FENCE", "su.writable = false;", "CORAL_MIRROR_FENCE"):
            if marker not in s:
                raise ValueError("STOP: failed to fence UFS writes: " + marker)
    s=(root/"iokit/Kernel/arm/SweetFramebuffer.cpp").read_text()
    if "sweet_gpu_panel_stride(" not in s:
        raise ValueError("STOP: full upstream GPU display path absent")

    print("PASS: CORAL XNU 0124 geometry source overlay", len(changes),
          " guarded replacements; device media writes FENCED; GPU/panel "
          "still NOT validated on Coral. NO BOOT IMAGE.")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("xnu_source",type=Path)
    p.add_argument("--check-only",action="store_true")
    args=p.parse_args()
    port(args.xnu_source,dry_run=args.check_only)
