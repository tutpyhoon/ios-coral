#!/usr/bin/env python3
"""CORAL Phase 12: inspect the extracted iPhone X OS/cryptex filesystems safely.

macOS only. Attaches each existing image READ-ONLY, briefly inspects names
and selected file metadata, then detaches only devices from this invocation.
No root image creation, file copying, Internet, GitHub uploads, block-device
writes or phone access. Results are printed locally as JSON.

Usage:
    python3 coral/inspect_mounted_ipsw.py ~/Coral-iOS-16-images

If a particular APFS/cryptex image fails to mount, its error is recorded
and the remaining images are attempted. DO NOT run with sudo.
"""
import argparse
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys

CHECK_PATHS = {
    "os": (
        "sbin/launchd", "usr/lib/dyld", "usr/libexec/backboardd",
        "System/Library/CoreServices/SpringBoard.app/SpringBoard",
        "System/Library/xpc/launchd.plist",
        "System/Library/Caches/com.apple.dyld",
        "System/Cryptexes/OS",
        "private/preboot/Cryptexes/OS",
    ),
    "systemos": (
        "System/Library/dyld",
        "System/Library/Caches/com.apple.dyld",
        "System/Library/dyld/dyld_shared_cache_arm64",
        "System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64",
        "usr/lib/dyld",
        "usr/lib",
    ),
    "appos": (
        "Applications", "System/Applications", "System/Library",
        "System/Applications/Preferences.app",
    ),
}
IMAGE_NAMES = {"os": "os.dmg", "systemos": "systemos.dmg",
               "appos": "appos.dmg"}
DEV_RE = re.compile(r"^/dev/disk\d+$")


def parse_attach_response(data):
    info = plistlib.loads(data)
    entities = info.get("system-entities", ())
    mounts = []
    devices = []
    for entry in entities:
        dev = entry.get("dev-entry")
        if isinstance(dev, str):
            devices.append(dev)
        mounted = entry.get("mount-point")
        if isinstance(mounted, str) and mounted.startswith("/"):
            mounts.append(mounted)
    base = next((dev for dev in devices if DEV_RE.fullmatch(dev)), None)
    if not base:
        raise ValueError("hdiutil did not report a base /dev/diskN for cleanup")
    return base, mounts


def inspect_at_mount(mount, role):
    root = Path(mount)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Mounted root is not a plain directory")
    # Report top-level directory names for alternate /root layouts,
    # but do not follow symlinks or traverse the full filesystem.
    top = sorted(os.listdir(root))[:35]
    checks = {}
    for sub in CHECK_PATHS[role]:
        path = root / sub
        # iOS contains absolute symlinks. Never let a nested lookup
        # escape into a local macOS path by following a parent link.
        prefixes = list(Path(sub).parts)
        symlink_prefix = None
        for length in range(1, len(prefixes) + 1):
            candidate = root.joinpath(*prefixes[:length])
            if candidate.is_symlink():
                symlink_prefix = candidate
                break
        if symlink_prefix is not None and symlink_prefix != path:
            checks[sub] = {
                "type": "symlink_in_parent",
                "component": str(symlink_prefix.relative_to(root)),
                "target": os.readlink(symlink_prefix),
            }
            continue
        if path.is_symlink():
            checks[sub] = {"type": "symlink", "target": os.readlink(path)}
        elif path.is_file():
            checks[sub] = {"type": "file", "bytes": path.stat().st_size}
        elif path.is_dir():
            checks[sub] = {"type": "directory"}
        else:
            checks[sub] = {"type": "missing"}
    return {"mount_point": str(root), "top_level": top, "paths": checks}


def inspect_one(path, role, *, runner=subprocess.run):
    """Mount and detach only the device freshly returned by THIS attach."""
    output = {"role": role, "image": path.name, "attached_readonly": False,
              "mounted": False, "mounts": [], "error": None,
              "detach_success": None}
    base = None
    try:
        proc = runner(["hdiutil", "attach", "-readonly", "-nobrowse",
                       "-noautoopen", "-plist", str(path)],
                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      timeout=240, check=False)
        # On a nonzero status hdiutil may still have attached something.
        # Try parsing the response before raising, so we detach it.
        try:
            base, mounts = parse_attach_response(proc.stdout)
        except (ValueError, plistlib.InvalidFileException):
            mounts = []
        if proc.returncode != 0:
            message = proc.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(f"hdiutil attach exit {proc.returncode}: {message[-600:]}")
        if not base:
            raise RuntimeError("hdiutil attach returned no recoverable device reference")
        output["attached_readonly"] = True
        if not mounts:
            output["error"] = ("Disk image attached, but no volume was mounted. "
                               "May require different filesystem tooling.")
        for mount in mounts:
            try:
                output["mounts"].append(inspect_at_mount(mount, role))
            except (OSError, ValueError) as e:
                output["mounts"].append({"mount_point": mount, "scan_error": str(e)})
        output["mounted"] = bool(mounts)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as e:
        output["error"] = str(e)[:800]
    finally:
        if base:
            try:
                done = runner(["hdiutil", "detach", base],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=120, check=False)
                output["detach_success"] = done.returncode == 0
                if done.returncode != 0:
                    output["detach_warning"] = (
                        f"Could not detach {base} automatically. Check: "
                        f"diskutil list; then hdiutil detach {base}. "
                        "Do not detach any unrelated disk.")
            except (OSError, subprocess.TimeoutExpired) as e:
                output["detach_success"] = False
                output["detach_warning"] = (
                    f"Unable to detach {base}: {e}. Check only that attached disk.")
    return output


def run(directory, *, runner=subprocess.run):
    if sys.platform != "darwin":
        raise RuntimeError("Use this command on macOS only")
    directory = Path(directory).expanduser().resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("Expected an extracted-image directory")
    report_file = directory / "local-image-report.json"
    if report_file.is_symlink() or not report_file.is_file():
        raise ValueError("Missing local-image-report.json")
    report = json.loads(report_file.read_text())
    if report.get("build") != "20H392" or report.get("device") != "iPhone10,3":
        raise ValueError("Expected verified iPhone X 20H392 extraction report")
    by_role = {item.get("role"): item.get("name") for item in report.get("files", ())}
    findings = []
    for role, filename in IMAGE_NAMES.items():
        if by_role.get(role) != filename:
            raise ValueError(f"Expected {role} image named {filename}; found {by_role.get(role)}")
        image = directory / filename
        if image.is_symlink() or not image.is_file():
            raise ValueError(f"Missing regular local image {filename}")
        findings.append(inspect_one(image, role, runner=runner))
    return {"stage": "coral-phase12-readonly-mounted-image-inspection",
            "images": findings,
            "note": "No files or partitions changed. Mounts should be detached now. "
                    "This is not a merged iOS root or bootable image."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("images_directory", type=Path)
    a = p.parse_args()
    try:
        report = run(a.images_directory)
    except (ValueError, OSError, RuntimeError) as e:
        p.error(str(e))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
