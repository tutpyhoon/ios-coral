#!/usr/bin/env python3
"""Validate a macOS UDRW GPT and unwrap its sole Apple_HFSX partition.

HFS+ disks created by hdiutil -fs JHFS+X have a GPT wrapper. Pixel XNU's
/ufsroot0 driver needs raw HFS+ volume bytes at LBA0 of its logical root
partition, NOT the outer Macintosh GUID-partitioned .dmg.
This module checks primary GPT header CRC, partition-array CRC, type GUID,
volume signature and partition bounds; then optionally shifts only the
local, disposable UDRW file to remove the GPT wrapper. NEVER touches phone
storage or the original sparseimage.

Use ONLY on a NEW private copy of the image. An interrupted in-place
shift makes that copy unusable; the source .sparseimage stays unchanged.
"""
import os
from pathlib import Path
import struct
import uuid
import zlib

SECTOR=512
GPT_MAGIC=b"EFI PART"
APPLE_HFS=uuid.UUID("48465300-0000-11aa-aa11-00306543ecac").bytes_le

class GPTError(ValueError): pass


def hfs_header_at(f,base,length):
    f.seek(base+1024)
    hdr=f.read(64)
    if len(hdr)<52 or hdr[:2] not in (b"H+",b"HX"):
        raise GPTError("Apple HFS GPT partition is not HFS+ at its volume header")
    blksz,count=struct.unpack_from(">II",hdr,40)
    if blksz not in (512,1024,2048,4096,8192,16384,32768,65536):
        raise GPTError(f"Invalid HFS+ block size {blksz}")
    if count<100 or blksz*count>length:
        raise GPTError("HFS+ filesystem extends beyond the GPT HFS partition")
    # hdiutil can reserve a little tail slack in the HFS partition.
    if length-blksz*count>65536:
        raise GPTError("Too much unexplained space after HFS volume")
    return {"signature":hdr[:2].decode(),
            "allocation_block_size":blksz,"allocation_blocks":count,
            "actual_fs_bytes":blksz*count}


def locate_gpt_hfs(image):
    file=Path(image)
    total=file.stat().st_size
    with file.open("rb") as f:
        f.seek(SECTOR)
        sector=f.read(SECTOR)
        if sector[:8]!=GPT_MAGIC:
            raise GPTError("Missing primary GPT header at LBA1")
        header_size,crc=struct.unpack_from("<II",sector,12)
        if not 92<=header_size<=SECTOR:
            raise GPTError("Malformed GPT header size")
        copy=bytearray(sector[:header_size])
        struct.pack_into("<I",copy,16,0)
        if zlib.crc32(copy)&0xffffffff!=crc:
            raise GPTError("Primary GPT header CRC mismatch")
        current_lba, backup_lba=struct.unpack_from("<QQ",sector,24)
        first_usable,last_usable=struct.unpack_from("<QQ",sector,40)
        entry_lba=struct.unpack_from("<Q",sector,72)[0]
        num,ent_size,array_crc=struct.unpack_from("<III",sector,80)
        if current_lba!=1 or not 1<=num<=512 or not 128<=ent_size<=512:
            raise GPTError("Unexpected primary GPT geometry")
        if first_usable<2 or last_usable>=backup_lba or backup_lba*SECTOR>total:
            raise GPTError("Unexpected GPT usable LBA bounds")
        arr_bytes=num*ent_size
        if (entry_lba*SECTOR+arr_bytes)>total or arr_bytes>262144:
            raise GPTError("Unexpected partition entry bounds")
        f.seek(entry_lba*SECTOR)
        entries=f.read(arr_bytes)
        if len(entries)!=arr_bytes or zlib.crc32(entries)&0xffffffff!=array_crc:
            raise GPTError("Partition-entry array CRC mismatch")
        matches=[]
        for index in range(num):
            ent=entries[index*ent_size:(index+1)*ent_size]
            if ent[:16]!=APPLE_HFS:
                continue
            start,end=struct.unpack_from("<QQ",ent,32)
            if start<first_usable or end>last_usable or end<start:
                raise GPTError(f"HFS partition {index} falls outside GPT data bounds")
            base=start*SECTOR
            length=(end-start+1)*SECTOR
            if base+length>total:
                raise GPTError("HFS partition is truncated")
            hdr=hfs_header_at(f,base,length)
            matches.append({
                "gpt_index":index+1,"start_lba":start,"end_lba":end,
                "offset_bytes":base,"volume_bytes":length,**hdr
            })
        if len(matches)!=1:
            raise GPTError(f"Expected exactly one Apple HFS+ GPT partition, found {len(matches)}")
        result=matches[0]
        result.update({"gpt_header_crc_verified":True,
                       "gpt_entry_array_crc_verified":True,
                       "container_file_bytes":total,
                       "sector_size":SECTOR})
        return result


def remove_gpt_inplace(image):
    """Shift sole HFS partition down over GPT in a disposable UDRW file."""
    src=Path(image)
    info=locate_gpt_hfs(src)
    length=info["volume_bytes"]
    start=info["offset_bytes"]
    if start<SECTOR*3:
        raise GPTError("HFS partition start overlaps GPT metadata")
    chunk=4*1024*1024
    with src.open("r+b",buffering=0) as f:
        fd=f.fileno()
        pos=0
        while pos<length:
            n=min(chunk,length-pos)
            buf=os.pread(fd,n,start+pos)
            if len(buf)!=n:
                raise GPTError(f"Truncated source UDRW at byte offset {pos}")
            wrote=os.pwrite(fd,buf,pos)
            if wrote!=n:
                raise GPTError("Short write while extracting HFS partition")
            pos+=n
        os.fsync(fd)
        f.truncate(length)
        os.fsync(fd)
    with src.open("rb") as f:
        raw=hfs_header_at(f,0,length)
    if raw["actual_fs_bytes"]>length:
        raise GPTError("Invalid extracted HFS size")
    return {"gpt_source":info,"raw_bytes":length,
            "extracted_hfs_header":raw,
            "new_file_contains_no_gpt":True}
