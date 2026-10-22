#!/usr/bin/env python3
"""Read-only audit of the Mac-local Phase12 merged HFS+ candidate.

Runs ONLY on macOS: temporary read-only attach / safe detach; checks real
Apple executables, full split dyld cache, preserved hardlinks/ownership,
and presence of embedded OS and App cryptex trees. No flash or phone I/O.

  python3 coral/audit_hfs_candidate12.py \
      ~/Coral-iOS-16-work/CoralIOSRoot.sparseimage

A PASS means structurally present on macOS, not able to boot on Coral.
"""
from pathlib import Path
import argparse
import json
import os
import sys
import tempfile

from build_ios_hfs_candidate import mounted
from ios_root_audit import audit


def validate(root):
    base = Path(root)
    result = audit(base)
    cache = base / "System/Library/Caches/com.apple.dyld"
    source_cache = base / "private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld"
    result["hfs_candidate"] = "structural read-only mounted filesystem audit"
    result["cache_subfiles"] = {}
    result["missing_critical"] = []
    for name in ("os", "app"):
        folder = base / "private/preboot/Cryptexes" / ("OS" if name == "os" else "App")
        if not folder.is_dir() or folder.is_symlink():
            result["missing_critical"].append(str(folder.relative_to(base)))
    if not (cache.is_dir() and not cache.is_symlink() and source_cache.is_dir()):
        result["missing_critical"].append("missing main or source dyld cache folder")
    else:
        names = sorted(p.name for p in cache.iterdir()
                       if p.is_file() and p.name.startswith("dyld_shared_cache_arm64"))
        total = 0
        mismatched = []
        for n in names:
            p, src = cache / n, source_cache / n
            if not src.is_file():
                mismatched.append(n + ": source unavailable")
                continue
            if p.stat().st_size != src.stat().st_size or p.stat().st_ino != src.stat().st_ino:
                mismatched.append(n + ": not hardlinked")
            total += p.stat().st_size
        result["cache_subfiles"] = {
            "count": len(names), "total_apparent_bytes": total,
            "hardlink_errors": mismatched[:12]
        }
        if len(names) != 44 or total != 3330359296 or mismatched:
            result["missing_critical"].append("shared-cache parts differ from owner survey")
    for rel in ("sbin/launchd","usr/lib/dyld", "usr/libexec/backboardd",
                "System/Library/CoreServices/SpringBoard.app/SpringBoard"):
        p=base/rel
        if not p.is_file() or p.is_symlink():
            result["missing_critical"].append(rel)
    result["ready_for_runtime_testing"] = False
    result["structurally_complete"] = (
        result["all_critical_present"] and not result["missing_critical"])
    result["warning"] = (
        "No code has been executed; XNU still lacks a proven compatible "
        "mounted UFS root, permissions/entitlements/runtime fixes and "
        "SpringBoard graphics services.")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sparseimage",type=Path)
    args=parser.parse_args()
    image=args.sparseimage.expanduser().resolve(strict=True)
    if sys.platform != "darwin":
        parser.error("Run this audit on the Mac only")
    if not image.is_file() or image.suffix!=".sparseimage":
        parser.error("Expected existing local sparseimage")
    with tempfile.TemporaryDirectory(prefix="coral-audit-hfs-") as d:
        # Scoped temp mount only; normal detach even if audit raises an exception.
        with mounted(image,Path(d)/"mnt",readonly=True) as mount:
            report=validate(mount)
    print(json.dumps(report,indent=2))
    return 0 if report["structurally_complete"] else 2

if __name__=="__main__":
    sys.exit(main())
