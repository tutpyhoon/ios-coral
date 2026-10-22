#!/usr/bin/env python3
"""Build a TEMPORARY Coral Phase12 UFS register-only probe (no media I/O).

Reuses pinned FLAME mode 06 (Google Pixel 4 same SM8150 family), adapted to
Coral's known 1440x3040 framebuffer. NO XNU, NO SCSI, NO DMA, NO UFS writes,
NO boot/flash actions. This does not mean Coral UFS blocks are readable.
The bootloader-supplied live device tree and EL1/MMU-off state must pass
before any MMIO register accesses take place.

Always keep the proven Phase11 image and Android backup as fallback.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys

import build_probes as base

def main():
    base.build()  # pinned source and proven geometric adaptation, modes 01-04
    source = base.WORK / "flame"
    ufs = (source / "ufs.c").read_text()
    probe = (source / "probe.c").read_text()
    platform = (source / "platform.c").read_text()
    expected_reads = [
        "FLAME_UFS_BASE + 0x00","FLAME_UFS_BASE + 0x08",
        "FLAME_UFS_BASE + 0x34","FLAME_UFS_BASE + 0x30",
        "FLAME_UFS_BASE + 0x50","FLAME_UFS_BASE + 0x54",
        "FLAME_UFS_BASE + 0x60","FLAME_UFS_BASE + 0x58",
        "FLAME_UFS_BASE + 0x80","FLAME_UFS_BASE + 0x78",
    ]
    if any(ufs.count(n) != 1 for n in expected_reads):
        raise RuntimeError("STOP: upstream UFS read register whitelist changed")
    if any(word in ufs for word in ("write32","write64","scsi","memcpy","dma","asm")):
        raise RuntimeError("STOP: this UFS code must contain only ten accessor reads")
    for needle in ('0x01d84000', '"/soc/ufshc@1d84000"', '"qcom,ufshc"'):
        if needle not in platform:
            raise RuntimeError("STOP: controller device-tree gate changed")
    for needle in ("LIVE DT METADATA VERIFIED", "UFS PRECONDITIONS FAILED - NO ACCESS",
                   "NO REGISTER WRITES / NO DMA", "NO STORAGE COMMANDS OR MEDIA ACCESS",
                   "if (READ(\"CurrentEL\") != 4 || (sctlr & 5) || !platform_ufs_check(&dt))"):
        if needle not in probe:
            raise RuntimeError(f"STOP: runtime hardware protection removed: {needle}")
    # Mode 06 exists already in the pinned source and is independently
    # host-verified by its mock-register tests.
    base.command("bash","flame/build.sh","06",cwd=base.WORK)
    base.command(sys.executable,"flame/check.py","06",cwd=base.WORK)
    src = source / "out/flame-probe-06.img"
    dst = base.OUT / "coral-ufs-reg-12-NO-MEDIA-IO.img"
    shutil.copyfile(src,dst)
    result = {
        "device": "Google Pixel 4 XL / coral",
        "source_sha": base.FLAME_SHA,
        "mode": "06 read-only controller register snapshot",
        "kernel_entry": False,
        "ufs_mmio_base": "0x01d84000",
        "ufs_reg_reads": [hex(int(n.rsplit("+",1)[-1],16)) for n in expected_reads],
        "ufs_write_ops": 0,
        "scsi_commands": 0,
        "dma": False,
        "partitions_accessed": False,
        "full_ios_boot": False,
        "temporary_boot_only": True,
        "physical_device_tested": False,
        "boot_img": dst.name,
        "size": dst.stat().st_size,
        "sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
        "warning": "MMIO reads may freeze hardware. Does not mount UFS or touch disk blocks. Do not flash.",
    }
    (base.OUT/"ufs12.json").write_text(json.dumps(result,indent=2)+"\n")
    (base.OUT/"SHA256SUMS").write_text(f"{result['sha256']}  {dst.name}\n")
    (base.OUT/"README-ufs12.txt").write_text(
        "CORAL UFS 12 — READ CONTROLLER REGISTERS ONLY\n"
        "Expected: LIVE DT METADATA VERIFIED, UFS BASE, CAP, VERSION, HCE, HCS,\n"
        "LIST BASE, LIST RUN, DOORBELL, REGISTER SNAPSHOT COMPLETE.\n"
        "If FDT or execution state differs, it prints PRECONDITIONS FAILED.\n"
        "No SCSI, DMA, UFS MMIO writes or block commands. No XNU/iOS.\n"
        "Temporary boot only via fastboot boot after checksum and product verification.\n"
        "NEVER fastboot flash, erase or format any partition.\n"
        "Experimental firmware/MMIO can still hang or reset. Backup and recovery plan required.\n"
    )
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
