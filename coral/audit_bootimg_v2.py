#!/usr/bin/env python3
"""Read-only Android boot image v2 source inspection for CORAL.

Extracts the DTB only on explicit --extract-dtb to a new file.
Prior Phase11 experimental boot images are **not** proof their embedded
DTB is the correct Pixel 4 XL board revision. No flashing/booting.

See Android Open Source Project boot image header v2 specification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

MAGIC=b"ANDROID!"
FDT_MAGIC=b"\xd0\x0d\xfe\xed"
HEADER_V2=1660
MAX_SIZE=128*1024*1024

def align(n, page):
    return (n+page-1)//page*page

def inspect(raw: bytes):
    if not HEADER_V2<=len(raw)<=MAX_SIZE or raw[:8]!=MAGIC:
        raise ValueError("not a bounded Android boot.img v2")
    (ksize,kaddr,rsize,raddr,ssize,saddr,taddr,page,version,osver)=struct.unpack_from("<10I",raw,8)
    if version != 2 or page not in (2048,4096,8192,16384):
        raise ValueError(f"requires Android boot header version 2 and supported pagesize, got {version}/{page}")
    (rec_size,rec_off,header_size,dtb_size,dtb_addr)=struct.unpack_from("<IQIIQ",raw,1632)
    if header_size!=HEADER_V2 or not (0<dtb_size<16*1024*1024):
        raise ValueError("unexpected boot v2 header size or missing DTB")
    cursor=page
    sections={}
    for key,size in (("kernel",ksize),("ramdisk",rsize),("second",ssize),("recovery_dtbo",rec_size),("dtb",dtb_size)):
        if size and cursor+size>len(raw):
            raise ValueError(f"truncated {key} in boot image")
        sections[key]={"offset":cursor,"size":size}
        cursor+=align(size,page)
    off=sections["dtb"]["offset"]
    dtb=raw[off:off+dtb_size]
    if dtb[:4]!=FDT_MAGIC:
        raise ValueError("DTB section lacks expected flattened device tree magic")
    totalsize=struct.unpack_from(">I",dtb,4)[0]
    if not 40<=totalsize<=dtb_size:
        raise ValueError("invalid first DTB header total size")
    # Multiple DTB slices may coexist in a stock boot image.
    return {"header_version":version,"page_size":page,
            "kernel_addr":hex(kaddr),"ramdisk_addr":hex(raddr),
            "dtb_addr":hex(dtb_addr),"sections":sections,
            "dtb_magic":dtb[:4].hex(),
            "first_dtb_total_bytes":totalsize,
            "dtb_sha256":hashlib.sha256(dtb).hexdigest(),
            "boot_sha256":hashlib.sha256(raw).hexdigest(),
            "read_only_by_default":True,
            "board_identity_verified":False,
            "not_a_bootable_coral_validation":True},dtb

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("boot_img",type=Path)
    p.add_argument("--extract-dtb",type=Path,help="write only a NEW local DTB output file")
    a=p.parse_args()
    raw=a.boot_img.expanduser().read_bytes()
    report,dtb=inspect(raw)
    if a.extract_dtb:
        out=a.extract_dtb.expanduser()
        with out.open("xb") as f:
            f.write(dtb)
        report["dtb_extracted_to"]=str(out)
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
