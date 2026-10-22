#!/usr/bin/env python3
"""CORAL Phase 12: read-only validation of locally extracted iPhone X images.

Run on the owner's Mac:
  python3 coral/probe_macos_images.py ~/Coral-iOS-16-images

Checks the extraction report and independently rehashes the three DMGs.
Attempts hdiutil imageinfo and 'file' inspection; NEVER attaches, mounts,
modifies, uploads, downloads, or accesses a phone or block device.
Unrecognized disk-image formats are reported, not silently treated as valid.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

TARGET_NAMES = {"os", "systemos", "appos"}
TARGET_BUILD = "20H392"
TARGET_VERSION = "16.7.16"
EXPECTED_EXTRACTED_SIZES = {
    "os": 4730814044,
    "systemos": 2743074816,
    "appos": 10485760,
}


class ImageCheckError(ValueError):
    pass


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as data:
        for buf in iter(lambda: data.read(8 * 1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()


def tools_info(path, *, tools=True):
    out = {"file_identification": None, "hdiutil_supported": None,
           "hdiutil_format": None, "hdiutil_error": None}
    if not tools:
        return out
    if shutil.which("file"):
        p = subprocess.run(["file", "-b", str(path)], capture_output=True, text=True,
                           timeout=45, check=False)
        out["file_identification"] = p.stdout.strip()[:512] if p.returncode == 0 else None
    if sys.platform != "darwin":
        out["hdiutil_error"] = "hdiutil only runs on macOS"
        return out
    if not shutil.which("hdiutil"):
        out["hdiutil_error"] = "hdiutil not found in PATH"
        return out
    try:
        p = subprocess.run(["hdiutil", "imageinfo", "-plist", str(path)],
                           capture_output=True, timeout=180, check=False)
        if p.returncode:
            out["hdiutil_supported"] = False
            out["hdiutil_error"] = p.stderr.decode("utf-8", "replace").strip()[-800:]
        else:
            details = plistlib.loads(p.stdout)
            out["hdiutil_supported"] = True
            out["hdiutil_format"] = details.get("Format") or details.get("Format Description")
            out["hdiutil_partitioned"] = details.get("Partitioned")
    except (OSError, subprocess.TimeoutExpired, plistlib.InvalidFileException,
            ValueError) as exc:
        out["hdiutil_supported"] = False
        out["hdiutil_error"] = str(exc)[:800]
    return out


def inspect(root, *, skip_hash=False, run_tools=True):
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ImageCheckError("Expected a directory containing extracted DMGs")
    manifest_path = root / "local-image-report.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ImageCheckError("Missing extraction report: local-image-report.json")
    report = json.loads(manifest_path.read_text())
    if report.get("version") != TARGET_VERSION or report.get("build") != TARGET_BUILD:
        raise ImageCheckError("Unexpected iOS version/build; expected 16.7.16 (20H392)")
    if report.get("device") != "iPhone10,3" or report.get("board") != "d22ap":
        raise ImageCheckError("Unexpected device; expected iPhone X D22AP")
    inputs = report.get("files", [])
    if len(inputs) != 3 or {e.get("role") for e in inputs} != TARGET_NAMES:
        raise ImageCheckError("Expected exactly OS, SystemOS and AppOS in the report")
    outcome = {"build": TARGET_BUILD, "device": "iPhone10,3",
               "mode": "read-only; no attach, mount, flash or file writes",
               "files": [], "checksum_verification": not skip_hash}
    for entry in inputs:
        role = entry["role"]
        filename = entry.get("name")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ImageCheckError("Invalid extraction report file name")
        path = root / filename
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ImageCheckError(f"Missing, symlinked or unsafe local image: {filename}")
        actual_bytes = path.stat().st_size
        expected = EXPECTED_EXTRACTED_SIZES[role]
        if entry.get("bytes") != expected or actual_bytes != expected:
            raise ImageCheckError(
                f"{role}: size mismatch. Expected {expected}, got {actual_bytes}.")
        row = {"role": role, "file": filename, "bytes": actual_bytes}
        if not skip_hash:
            measured = digest(path)
            row["sha256_verified"] = (measured == entry.get("sha256"))
            if not row["sha256_verified"]:
                raise ImageCheckError(f"{role}: SHA-256 mismatch (corrupt/exchanged image)")
        row.update(tools_info(path, tools=run_tools))
        outcome["files"].append(row)
    outcome["images_usable_on_macos"] = (
        all(x.get("hdiutil_supported") is True for x in outcome["files"])
        if run_tools and sys.platform == "darwin" else None)
    outcome["note"] = (
        "hdiutil imageinfo indicates recognizability only, NOT that APFS "
        "contents can be safely mounted/read or merged. No disk image was attached.")
    return outcome


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("images_directory", type=Path)
    parser.add_argument("--skip-hash", action="store_true",
                        help="skip SHA-256 for speed (does not establish file integrity)")
    args = parser.parse_args()
    try:
        report = inspect(args.images_directory, skip_hash=args.skip_hash)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
