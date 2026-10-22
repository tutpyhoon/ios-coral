#!/usr/bin/env python3
"""CORAL Phase 12 read-only source-volume inventory and HFS root space estimate.

Run on the owner's Mac after successful IPSW extraction:
  python3 coral/survey_ios_volumes.py ~/Coral-iOS-16-images

For each previously SHA-verified image, briefly attach -readonly and walk
the mounted filesystem without following symbolic links. Estimates apparent
(uncompressed) sizes and counts distinct file inodes. Records actual shared-
cache subfiles instead of assuming the small main cache is the entire cache.
Always detaches the just-attached image via inspect_mounted_ipsw.py.

This script DOES NOT create a destination image or write firmware files;
does not mount the phone, flash, or upload proprietary data.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import sys

from inspect_mounted_ipsw import run as inspect_all

LIMIT = 1_000_000
CACHE_DIR = "System/Library/Caches/com.apple.dyld"
TARGETS = {
    "os": ("sbin/launchd","usr/lib/dyld","usr/libexec/backboardd",
           "System/Library/CoreServices/SpringBoard.app/SpringBoard",
           "System/Library/xpc/launchd.plist"),
    "systemos": ("System/Library/Caches/com.apple.dyld", "usr/lib"),
    "appos": ("System/Library","usr/lib"),
}

def survey(root: Path, role: str):
    """Read metadata only; never follow symlinks or read full file contents."""
    stats = {"role":role, "entries":0, "regular_files":0, "directories":0,
             "symlinks":0, "hardlink_duplicates":0,
             "apparent_bytes_unique_inodes":0, "allocated_bytes_upper_bound":0,
             "permissions_not_preserved_yet": True,
             "cache": [], "selected_paths": {}}
    pending=[root]
    seen=set()
    while pending:
        directory=pending.pop()
        with os.scandir(directory) as it:
            for item in it:
                stats["entries"]+=1
                if stats["entries"]>LIMIT:
                    raise ValueError(f"Volume too large to survey under limit={LIMIT}")
                meta=item.stat(follow_symlinks=False)
                if stat.S_ISLNK(meta.st_mode):
                    stats["symlinks"]+=1
                elif stat.S_ISDIR(meta.st_mode):
                    stats["directories"]+=1
                    pending.append(Path(item.path))
                elif stat.S_ISREG(meta.st_mode):
                    stats["regular_files"]+=1
                    key=(meta.st_dev,meta.st_ino)
                    if key not in seen:
                        seen.add(key)
                        stats["apparent_bytes_unique_inodes"]+=meta.st_size
                        stats["allocated_bytes_upper_bound"]+=meta.st_blocks*512
                    else:
                        stats["hardlink_duplicates"]+=1
    for relative in TARGETS[role]:
        candidate=root / relative
        if candidate.is_symlink():
            stats["selected_paths"][relative]={"type":"symlink","target":os.readlink(candidate)}
        elif candidate.is_file():
            stats["selected_paths"][relative]={"type":"file","bytes":candidate.stat().st_size}
        elif candidate.is_dir():
            stats["selected_paths"][relative]={"type":"directory"}
        else:
            stats["selected_paths"][relative]={"type":"missing"}
    if role=="systemos":
        folder=root / CACHE_DIR
        if folder.is_dir() and not folder.is_symlink():
            total=0
            with os.scandir(folder) as entries:
                for entry in entries:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    # Scan names and size only; read at most 16 bytes per file.
                    size=entry.stat(follow_symlinks=False).st_size
                    total+=size
                    prefix=b""
                    try:
                        with open(entry.path,"rb") as f:
                            prefix=f.read(16)
                    except (PermissionError,OSError):
                        pass
                    stats["cache"].append({
                        "name":entry.name,
                        "bytes":size,
                        "header":prefix.decode("ascii","backslashreplace")})
            stats["cache"].sort(key=lambda x:x["name"])
            stats["cache_total_apparent_bytes"]=total
            stats["cache_file_count"]=len(stats["cache"])
            # Limit user-facing detail rather than truncating the total.
            stats["cache"]=stats["cache"][:80]
    return stats


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("images_directory",type=Path)
    args=p.parse_args()
    if sys.platform!="darwin":
        p.error("Run the filesystem survey on macOS")
    output=inspect_all(args.images_directory, scanner=survey)
    all_surveys=[v["survey"] for image in output["images"]
                 for v in image.get("mounts",()) if "survey" in v]
    for image in output["images"]:
        if image.get("detach_success") is not True:
            output["warning"] = "A source image may remain attached; inspect before retrying"
    if len(all_surveys)==3:
        apparent=sum(v["apparent_bytes_unique_inodes"] for v in all_surveys)
        output["combined_apparent_bytes_pre_dedup"]=apparent
        output["recommended_destination"] = (
            "Mac-created sparse HFS+X candidate; size depends on copied "
            "file bytes, HFS metadata and required runtime free space; "
            "no image created yet.")
        output["copy_ready"] = all(image.get("detach_success") is True
                                   for image in output["images"])
        output["root_merge_warning"]=(
            "Apparent bytes double-count cross-volume duplicate files. "
            "Some APFS compression/sparse files may use less physical "
            "storage. Do not choose a root image size solely from this total.")
    print(json.dumps(output,indent=2))
    if any(image.get("detach_success") is False for image in output["images"]):
        return 2
    return 0


if __name__=="__main__":
    sys.exit(main())
