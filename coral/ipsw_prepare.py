#!/usr/bin/env python3
"""Phase 12: identify and optionally extract iPhone X iOS 16.7.16 OS/Cryptex DMGs.

Uses only local, user-owned IPSW ZIP bytes and Python stdlib.
No network, phone access, flashing, mounting, overwriting, GitHub upload,
or Apple code execution. ZIP entries are selected via BuildManifest.plist,
never by filename guessing.

Examples:
  python3 coral/ipsw_prepare.py ~/Downloads/iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw
  python3 coral/ipsw_prepare.py ~/Downloads/iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw --extract ~/Coral-iOS-16-images
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import sys
import zipfile

TARGET_VERSION = "16.7.16"
TARGET_BUILD = "20H392"
TARGET_DEVICE = "iPhone10,3"
TARGET_BOARD = "d22ap"
KINDS = (("os", "OS"), ("systemos", "Cryptex1,SystemOS"), ("appos", "Cryptex1,AppOS"))


class IPSWError(ValueError):
    pass


def identify(zf):
    if "BuildManifest.plist" not in zf.namelist():
        raise IPSWError("Missing BuildManifest.plist")
    raw = zf.read("BuildManifest.plist")
    if len(raw) > 16 * 1024 * 1024:
        raise IPSWError("Unreasonably large BuildManifest.plist")
    manifest = plistlib.loads(raw)
    version = str(manifest.get("ProductVersion"))
    build = str(manifest.get("ProductBuildVersion"))
    supported = manifest.get("SupportedProductTypes", [])
    if version != TARGET_VERSION or build != TARGET_BUILD:
        raise IPSWError(f"Expected iOS {TARGET_VERSION} ({TARGET_BUILD}); got {version} ({build})")
    if TARGET_DEVICE not in supported:
        raise IPSWError(f"Expected {TARGET_DEVICE} IPSW; supported={supported!r}")
    identities = manifest.get("BuildIdentities")
    if not isinstance(identities, list) or not identities:
        raise IPSWError("Missing BuildIdentities")
    eligible = []
    for entry in identities:
        info = entry.get("Info", {})
        if str(info.get("DeviceClass", "")).lower() != TARGET_BOARD:
            continue
        found = {}
        components = entry.get("Manifest", {})
        for slug, name in KINDS:
            obj = components.get(name)
            if not isinstance(obj, dict):
                continue
            path = obj.get("Info", {}).get("Path") or obj.get("Path")
            if isinstance(path, str):
                found[slug] = path
        if len(found) == len(KINDS):
            eligible.append((info, found))
    if not eligible:
        classes = sorted({str(x.get("Info", {}).get("DeviceClass")) for x in identities})
        raise IPSWError(
            "No D22AP restore identity provides OS + Cryptex1,SystemOS + "
            f"Cryptex1,AppOS; available board classes: {classes}. "
            "This IPSW may require a different extraction method.")
    # The common iPhone X IPSW contains multiple d22ap restore identities;
    # select the explicitly complete one, preferring erase/restore behavior
    # but never merge component paths between identities.
    info, selected = sorted(
        eligible,
        key=lambda pair: str(pair[0].get("RestoreBehavior", "")).lower() not in {"erase", "restore"}
    )[0]
    available = set(zf.namelist())
    results = []
    for slug, _ in KINDS:
        path = selected[slug]
        # Prevent traversal / absolute-path/multi-level extraction ambiguity.
        if path.startswith(("/", "\\\\")) or any(x == ".." for x in path.replace("\\\\", "/").split("/")):
            raise IPSWError(f"Unsafe manifest member path: {path!r}")
        if path not in available:
            raise IPSWError(f"IPSW ZIP is missing manifest member {path!r}")
        record = zf.getinfo(path)
        if record.is_dir():
            raise IPSWError(f"Unexpected directory member: {path!r}")
        results.append({"role": slug, "zip_path": path, "bytes": record.file_size,
                        "compressed_bytes": record.compress_size, "crc32": f"{record.CRC:08x}",
                        "output": f"{slug}.dmg" if path.lower().endswith(".dmg") else
                        f"{slug}{Path(path).suffix.lower()}"})
    return {
        "product_version": version, "build": build, "device": TARGET_DEVICE,
        "board": TARGET_BOARD, "restore_behavior": info.get("RestoreBehavior", "unspecified"),
        "files": results,
        "note": "Local OS/Cryptex image selection only: does not build an iOS root or flash a phone."
    }


def extract(zf, inventory, output: Path):
    output = output.expanduser()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise IPSWError("Output directory must not exist or must be empty; refusing overwrite")
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for record in inventory["files"]:
        destination = output / record["output"]
        partial = output / (record["output"] + ".partial")
        sha = hashlib.sha256()
        total = 0
        try:
            # ZipExtFile validates the IPSW's CRC32 when fully consumed.
            with zf.open(record["zip_path"]) as reader, partial.open("xb") as writer:
                while True:
                    data = reader.read(4 * 1024 * 1024)
                    if not data:
                        break
                    sha.update(data)
                    writer.write(data)
                    total += len(data)
            if total != record["bytes"]:
                raise IPSWError(f"Truncated {record['role']}: expected {record['bytes']}, got {total}")
            partial.rename(destination)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        records.append({"role": record["role"], "name": destination.name,
                        "bytes": total, "sha256": sha.hexdigest()})
        print(f"Extracted {record['role']}: {destination} ({total} bytes)", flush=True)
    report = {
        "version": inventory["product_version"], "build": inventory["build"],
        "device": inventory["device"], "board": inventory["board"],
        "files": records,
        "warning": "Contains Apple proprietary data; DO NOT upload this folder to public GitHub."
    }
    (output / "local-image-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def run(ip, destination=None):
    path = ip.expanduser().resolve(strict=True)
    if not path.is_file():
        raise IPSWError("Expected IPSW file")
    with zipfile.ZipFile(path) as zf:
        inventory = identify(zf)
        print(json.dumps(inventory, indent=2), flush=True)
        if destination is not None:
            return extract(zf, inventory, destination)
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ipsw", type=Path, help="locally downloaded iPhone X IPSW")
    parser.add_argument("--extract", type=Path, metavar="EMPTY_DIR",
                        help="extract just the three selected DMGs; no phone access")
    args = parser.parse_args()
    try:
        run(args.ipsw, args.extract)
    except (OSError, IPSWError, zipfile.BadZipFile, plistlib.InvalidFileException) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
