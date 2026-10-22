#!/usr/bin/env python3
"""Stage CORAL's first optional XNU UFS READ-ONLY driver for compile testing.

Requires a fresh pinned dimasmds/ios-flame checkout after stage05.py prepare,
a pinned blacktop/darwin-xnu-build checkout after
source/flame/stage_kernel.py stage, and before dxb/build.sh.

This only adds upstream 0028 read-only UFS source. It does NOT add 0029+
(unsealed root bypass, write support, GPU, etc), does NOT change rd=md0,
does not bundle iOS files or create a device test image. A kernel compile
does not prove runtime media access or peripheral compatibility.
"""
from pathlib import Path
import argparse
import re

EXPECTED_FLAME = "b91463ab1ef083f81f6c3393593385aa996ceaf0"
CORAL_UFS_BASE = "0x01d84000"
READ_PATCH = "0028-sweet-ufs-root-device.patch"

def once(path: Path, old: str, new: str):
    s=path.read_text()
    if s.count(old)!=1:
        raise RuntimeError(f"{path}: unexpected pinned source {old!r} seen {s.count(old)} times")
    path.write_text(s.replace(old,new))

def setup(root: Path):
    stage=root/"flame/stage_kernel.py"
    source=(root/"xnu/patches"/READ_PATCH).read_text()
    if "bsd/dev/sweet_ufs.c" not in source or "Writes are refused." not in source:
        raise RuntimeError("Missing pinned upstream read-only driver")
    if "ufs_scsi(const uint8_t *cdb, unsigned cdb_len, uint32_t len)" not in source:
        raise RuntimeError("Unexpected upstream read-only SCSI interface")
    if not all(marker in source for marker in
               ("(flags & FWRITE) ? EROFS : 0", "ufs_read_blocks(", "UFS_BLOCK       4096u",
                "rdBootVar, \"ufsroot0\"", '0x28, 0,')):
        # The root hook uses a literal strcmp(rdBootVar,"ufsroot0");
        # explicit compile guards prevent unintentional activation.
        if 'strcmp(rdBootVar, "ufsroot0")' not in source:
            raise RuntimeError("Read-only driver missing required root opt-in")
    if any(p.exists() for p in (root/"xnu/patches"/name for name in
                                 ("0030-sweet-ufs-writes.patch",))):
        # The upstream repository contains these later patches by design.
        # We MUST not stage them as compile inputs, but do not delete source.
        pass
    once(stage, "numbers = set(range(1, 28))", "numbers = set(range(1, 29))")
    once(stage, '''    if (source / "bsd/dev/sweet_ufs.c").exists():
        raise SystemExit("Storage driver present: this is not the intended early-console source tree")''',
         '''    ufs_driver=source / "bsd/dev/sweet_ufs.c"
    if not ufs_driver.exists():
        raise SystemExit("Expected optional read-only SWEET UFS source is absent")
    ufs=ufs_driver.read_text()
    if "Writes are refused." not in ufs or "ufs_read_blocks(" not in ufs:
        raise SystemExit("Expected read-only driver contract changed")
    if "ufs_write_blocks" in ufs or "ufsrw" in ufs:
        raise SystemExit("STOP: unexpected UFS write support")''')
    once(stage, 'print("Pixel source profile verified; storage driver excluded")',
         'print("Pixel source profile verified; optional read-only UFS driver compiled, not activated")')
    once(stage, 'print(f"Staged {len(selected)} source inputs (core providers and Pixel console); peripheral drivers excluded")',
         'print(f"Staged {len(selected)} source inputs (optional UFS read-only driver; later peripheral/write patches excluded)")')
    print("PASS: pinned Flame patch selection extended ONLY to source patch 0028")

def hook(dxb: Path, checkout: Path):
    build=dxb/"build.sh"
    if not build.is_file():
        raise RuntimeError("Missing pinned dxb/build.sh")
    old='python3 "${GITHUB_WORKSPACE}/coral/postpatch05.py" "${WORK_DIR}/xnu"'
    new='python3 "${GITHUB_WORKSPACE}/coral/postpatch_ufs12.py" "${WORK_DIR}/xnu"'
    once(build,old,new)
    # Verify upstream was already prepared but not compiled.
    stage=checkout/"flame/stage_kernel.py"
    if "numbers = set(range(1, 29))" not in stage.read_text():
        raise RuntimeError("Read-only source patch has not been enabled")
    if not (dxb/"patches"/READ_PATCH).is_file():
        raise RuntimeError("Read-only 0028 patch was not staged")
    if any((dxb/"patches"/f"{n:04d}-sweet-ufs-writes.patch").exists()
           for n in (30,)):
        raise RuntimeError("Write-capable patch staged unexpectedly")
    patches=sorted(p.name for p in (dxb/"patches").glob("0[0-9][0-9][0-9]-*.patch"))
    if not patches or READ_PATCH not in patches or any(int(x[:4])>=29 and
                                                     int(x[:4])<99 for x in patches):
        raise RuntimeError("Unexpected port patch selection")
    print("PASS: optional read-only UFS source + isolated postpatch hook installed")

if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode",choices=("setup","hook"))
    ap.add_argument("checkout",type=Path)
    ap.add_argument("dxb",nargs="?",type=Path)
    args=ap.parse_args()
    if args.mode=="setup":
        setup(args.checkout.resolve())
    else:
        if not args.dxb:
            ap.error("hook requires dxb path")
        hook(args.dxb.resolve(),args.checkout.resolve())
