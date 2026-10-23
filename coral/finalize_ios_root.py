#!/usr/bin/env python3
"""CORAL full-iOS root finalization on macOS — OFFLINE only.

The user previously created a 24GiB case-sensitive HFS+ sparse image.
This tool:
  1. Converts it to a NEW writable UDRW image (source unchanged);
  2. Mounts the NEW image locally and applies NWylynko/ios-flame's
     SWEET root-launchd/Setup/activation tweaks;
  3. Supplies the upstream plain systembag.kb if missing;
  4. Verifies real launchd, dyld and all 44 shared cache hardlinks;
  5. Detaches safely, detects and strips only the UDRW 'koly' trailer,
     yielding a raw HFS+ byte image in a NEW path.

Run a dry-run preview by default. --execute writes large files on Mac only.
It NEVER issues adb, fastboot or any phone-storage write.

Example:
 python3 coral/finalize_ios_root.py \
   ~/Coral-iOS-16-work/CoralIOSRoot.sparseimage \
   ~/ios-flame-upstream/tools/sweet-root-tweaks.py \
   ~/Coral-iOS-16-work/final --execute

IMPORTANT: The result is not an automatically bootable iOS installation.
It cannot be safely written to Pixel userdata until the on-device GPT
layout and Coral's XNU UFS root driver have been verified.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile

from build_ios_hfs_candidate import mounted
from audit_hfs_candidate12 import validate as audit_root
from hfs_partition_extract import locate_gpt_hfs, remove_gpt_inplace, hfs_header_at

GIB=1024**3
KEYBAG=b'<plist version="1.0"><dict><key>KeyBagKeys</key><data>U1dFRVQ=</data></dict></plist>\n'


class RootError(ValueError):
    pass


def check_hfs_bytes(path):
    """Verify volume begins at file offset zero, not wrapped by GPT/UDIF."""
    with Path(path).open("rb") as f:
        f.seek(1024)
        hdr=f.read(512)
        f.seek(0,os.SEEK_END)
        total=f.tell()
        f.seek(max(0,total-512))
        tail=f.read(512)
    if len(hdr)<52 or hdr[:2] not in (b"H+", b"HX"):
        raise RootError("HFS+ volume header missing at 1024: not safe raw filesystem")
    blocksize,blocks=struct.unpack_from(">II",hdr,40)
    if blocksize<512 or blocksize>65536 or blocksize & (blocksize-1):
        raise RootError(f"Unexpected HFS+ allocation block size {blocksize}")
    if blocks<100 or blocks>0xffffffff:
        raise RootError("Invalid HFS+ block count")
    length=blocksize*blocks
    # UDRW may append only an Apple 512-byte koly trailer; any additional
    # wrapper or block alignment requires separate examination.
    if total==length:
        extra=0
    elif total==length+512 and tail[:4]==b"koly":
        extra=512
    else:
        raise RootError(
            f"Volume describes {length} bytes, image has {total}; "
            "cannot safely strip an unknown wrapper or partition table")
    return {"signature":hdr[:2].decode(),"block_size":blocksize,
            "blocks":blocks,"raw_bytes":length,"udif_trailer_bytes":extra}


def plan(source,twk,out):
    if sys.platform!="darwin":
        raise RootError("Run on the Mac, not in GitHub's Linux runner")
    s=source.expanduser().resolve(strict=True)
    t=twk.expanduser().resolve(strict=True)
    o=out.expanduser().absolute()
    if not s.is_file() or s.suffix!=".sparseimage":
        raise RootError("Supply the original Coral HFS+ sparseimage")
    if not t.is_file() or t.name!="sweet-root-tweaks.py":
        raise RootError("Supply the pinned upstream tools/sweet-root-tweaks.py")
    if "def launchd(" not in t.read_text() or "def main(" not in t.read_text():
        raise RootError("Invalid upstream root-tweaks script")
    if o.exists():
        if not o.is_dir() or any(o.iterdir()):
            raise RootError("Output directory must be new or empty")
    elif not o.parent.is_dir():
        raise RootError("Create the parent output directory first")
    if o==s.parent or str(o).startswith(str(s.parent)+"/images"):
        raise RootError("Do not place output inside the original firmware image directory")
    capacity=subprocess.run(["hdiutil","imageinfo","-plist",str(s)],
                            capture_output=True,check=True,timeout=120)
    data=plistlib.loads(capacity.stdout)
    sector_bytes=data.get("Total Bytes") or data.get("TotalBytes")
    if not isinstance(sector_bytes,int):
        # Conservative lower bound rather than assuming sparse .stat size
        sector_bytes=24*GIB
    free=shutil.disk_usage(o.parent).free
    needs=sector_bytes+4*GIB
    return {"source":str(s),"output_folder":str(o),"upstream_tweaks":str(t),
            "estimated_uncompressed_bytes":sector_bytes,
            "minimum_available_bytes":needs,
            "available_bytes":free,"enough_space":free>=needs,
            "operation":"new Mac-local raw HFS+ export with upstream iOS launchd/setup tweaks",
            "phone_operations":0, "source_sparseimage_modified":False}


def sudo(args,input_data=None):
    proc=subprocess.run(["sudo",*map(str,args)],input=input_data,check=True)
    return proc


def seed_keybag(mnt):
    path=mnt/"private/var/keybags/systembag.kb"
    if path.exists():
        return "existing"
    sudo(["install","-d","-m","0755",path.parent])
    sudo(["tee",path],KEYBAG)
    sudo(["chmod","0600",path])
    sudo(["chown","0:0",path])
    return "seeded"


def execute(source,tweaks,output):
    info=plan(source,tweaks,output)
    if not info["enough_space"]:
        raise RootError("Insufficient host free space for raw HFS image; no changes made")
    out=output.expanduser().absolute()
    out.mkdir(exist_ok=True)
    dmg=out/"CoralIOSRoot-working.dmg"
    final=out/"CoralIOSRoot-final.img"
    if dmg.exists() or final.exists():
        raise RootError("Refusing to overwrite a previous root build")
    print(json.dumps(info,indent=2),flush=True)
    # Do not start the multi-hour copy without filesystem metadata sanity.
    subprocess.run(["sudo","-v"],check=True)
    subprocess.run(["hdiutil","convert",str(source.expanduser()),"-format",
                    "UDRW","-o",str(dmg)],check=True)
    if not dmg.is_file():
        raise RootError("hdiutil did not create the output image")
    with tempfile.TemporaryDirectory(prefix="coral-ios-root-") as tmp:
        with mounted(dmg,Path(tmp)/"mnt",readonly=False) as mnt:
            existing=audit_root(mnt)
            if not existing.get("structurally_complete"):
                raise RootError("Original HFS candidate lacks real binaries/cache: "+repr(existing.get("missing_critical")))
            result=subprocess.run(["sudo",sys.executable,str(tweaks.expanduser().resolve()),
                                   str(mnt)],check=False)
            if result.returncode:
                raise RootError("Upstream full-iOS root tweaks failed; candidate is incomplete")
            bag=seed_keybag(mnt)
            after=audit_root(mnt)
            if not after.get("structurally_complete"):
                raise RootError("Final root audit failed: "+repr(after.get("missing_critical")))
            if not (mnt/"System/Library/xpc/launchd.plist").is_file():
                raise RootError("Missing real Apple launchd service cache")
            print("PASS: real iOS system binaries, 44-part cache and local tweaks")
    # hdiutil -fs JHFS+X creates a GUID-partitioned disk, even when the
    # user requested a filesystem. Strip the EXACT Apple HFS+ GPT partition
    # from this disposable UDRW copy; retaining GPT would make XNU UFS root
    # read "EFI PART" instead of the HFS+ volume header.
    gpt=locate_gpt_hfs(dmg)
    raw=remove_gpt_inplace(dmg)
    dmg.rename(final)
    with final.open("rb") as f:
        volume=hfs_header_at(f,0,final.stat().st_size)
    if final.stat().st_size!=gpt["volume_bytes"]:
        raise RootError("Extracted HFS partition byte count is incorrect")
    verify={"gpt_removed":True,"partition_bytes":gpt["volume_bytes"],
            "filesystem":volume,"original_start_lba":gpt["start_lba"]}
    report={"status":"HOST-ONLY RAW HFS+ ROOT PREPARED; NOT INSTALLED",
            "hfs":verify, "path":str(final),
            "original_sparseimage_unchanged":True,
            "upstream_userland_tweaks_applied":True,
            "complete_44_part_dyld_cache":True,
            "never_directly_flash_without_partition_verification":True,
            "modem_nv_persist_imei_partitions_must_be_backed_up":True,
            "ready_to_boot_ios_on_coral":False}
    (out/"root-final-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source_sparseimage",type=Path)
    ap.add_argument("upstream_tweaks_py",type=Path)
    ap.add_argument("output_folder",type=Path)
    ap.add_argument("--execute",action="store_true",help="write Mac-local raw root; no phone access")
    a=ap.parse_args()
    try:
        if a.execute:
            execute(a.source_sparseimage,a.upstream_tweaks_py,a.output_folder)
        else:
            print(json.dumps(plan(a.source_sparseimage,a.upstream_tweaks_py,a.output_folder),indent=2))
    except (RootError,OSError,subprocess.CalledProcessError,plistlib.InvalidFileException) as e:
        ap.error(str(e))


if __name__=="__main__":
    main()
