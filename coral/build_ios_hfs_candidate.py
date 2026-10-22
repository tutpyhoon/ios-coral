#!/usr/bin/env python3
"""CORAL Phase 12: construct an OFFLINE macOS HFS+ iOS root candidate.

Default is a read-only PLAN. Real creation requires --execute and a new
output file. The sparse disk image is NOT flashable or bootable as-is.
Sources: the user's three validated iPhone X iOS 16.7.16 DMGs.

The only privileges requested are for ownership-preserving ditto/rsync,
directory creation and hard links *inside the new HFS+ image*. Source
images are attached -readonly. There is no adb, fastboot or phone I/O.

Examples:
  python3 coral/build_ios_hfs_candidate.py ~/Coral-iOS-16-images \
     ~/Coral-iOS-16-work/CoralIOSRoot.sparseimage
  python3 coral/build_ios_hfs_candidate.py ~/Coral-iOS-16-images \
     ~/Coral-iOS-16-work/CoralIOSRoot.sparseimage --execute

Do not copy or flash the .sparseimage to Pixel userdata. CORAL UFS read support
has NOT been demonstrated. All Apple files remain solely on the user's Mac.
"""
import argparse
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile


class BuildError(RuntimeError):
    pass


SOURCE_NAMES = {"os": "os.dmg", "systemos": "systemos.dmg", "appos": "appos.dmg"}
SOURCE_BYTES = {"os": 4730814044, "systemos": 2743074816, "appos": 10485760}
MIN_FREE_GIB = 18


def run_checked(args, *, timeout=None):
    print("+", " ".join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True,
                          timeout=timeout)


def verify_inputs(directory):
    root = directory.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise BuildError("Source must be the extracted image directory")
    manifest = root / "local-image-report.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise BuildError("Missing trusted local-image-report.json")
    doc = json.loads(manifest.read_text())
    if (doc.get("version"), doc.get("build"), doc.get("device"), doc.get("board")) != (
        "16.7.16", "20H392", "iPhone10,3", "d22ap"
    ):
        raise BuildError("Incorrect IPSW extraction identity")
    entries = doc.get("files", [])
    if not isinstance(entries, list) or len(entries) != 3:
        raise BuildError("Need exactly 3 source images")
    rows = {x.get("role"): x for x in entries}
    if set(rows) != set(SOURCE_NAMES):
        raise BuildError("Need OS, SystemOS and AppOS")
    for role, name in SOURCE_NAMES.items():
        row = rows[role]
        source = root / name
        if row.get("name") != name or source.is_symlink() or not source.is_file():
            raise BuildError(f"Missing/invalid {role} image")
        if row.get("bytes") != SOURCE_BYTES[role] or source.stat().st_size != SOURCE_BYTES[role]:
            raise BuildError(f"{role} source size changed; verify hashes again")
        if not isinstance(row.get("sha256"), str) or len(row["sha256"]) != 64:
            raise BuildError(f"Missing recorded checksum for {role}")
    return root


def validate_output(output):
    p = output.expanduser().absolute()
    if p.suffix != ".sparseimage":
        raise BuildError("Only a named .sparseimage output is accepted")
    if p.exists() or p.is_symlink():
        raise BuildError("Refusing to overwrite an existing output file")
    if any(x in ("..", "") for x in p.parts[1:]):
        raise BuildError("Invalid output path")
    if not p.parent.exists() or not p.parent.is_dir() or p.parent.is_symlink():
        raise BuildError("Create a real output directory first")
    return p


def plan(directory, output, size_gib=24):
    root = verify_inputs(directory)
    out = validate_output(output)
    if size_gib < 24 or size_gib > 128:
        raise BuildError("Use a sparse image size between 24 and 128 GiB")
    if str(out).startswith(str(root) + os.sep):
        raise BuildError("Output cannot be inside the extracted source directory")
    if str(out).startswith(str(Path.home() / "ios-coral-phase12") + os.sep):
        raise BuildError("Keep proprietary root images outside the Git repository")
    free = shutil.disk_usage(out.parent).free
    return {
        "status": "preflight only: NO FILESYSTEM CHANGES",
        "source_images": [SOURCE_NAMES[x] for x in ("os", "systemos", "appos")],
        "output": str(out),
        "sparse_volume_max_gib": size_gib,
        "filesystem": "Case-sensitive Journaled HFS+",
        "free_gib": round(free / (1024 ** 3), 2),
        "minimum_free_gib": MIN_FREE_GIB,
        "free_space_ok": free >= MIN_FREE_GIB * 1024 ** 3,
        "work": "copy OS root, embed SystemOS/AppOS cryptexes, add cache hardlinks and non-overwriting cryptex aliases",
        "not_yet_implemented": "SWEET root tweaks, storage driver and Pixel boot; NOT flash-ready",
        "host_writes_only_on_execute": True,
    }


def base_device(attach_output):
    d = plistlib.loads(attach_output)
    entities = d.get("system-entities", ())
    base = next((x.get("dev-entry") for x in entities
                 if isinstance(x.get("dev-entry"), str) and
                 x["dev-entry"].startswith("/dev/disk") and
                 x["dev-entry"][9:].isdigit()), None)
    mount = next((x.get("mount-point") for x in entities
                  if x.get("mount-point")), None)
    if base is None:
        raise BuildError("hdiutil did not supply safe base /dev/diskN")
    if mount is None:
        raise BuildError("hdiutil attached image but no readable mount point")
    return base, Path(mount)


@contextmanager
def mounted(image, directory, readonly=True):
    directory.mkdir()
    args = ["hdiutil", "attach", "-nobrowse", "-noautoopen",
            "-owners", "on", "-mountpoint", str(directory), "-plist"]
    args += ["-readonly" if readonly else "-readwrite", str(image)]
    proc = subprocess.run(args, capture_output=True, timeout=300)
    device = None
    try:
        if proc.stdout:
            try:
                device, actual = base_device(proc.stdout)
            except (ValueError, plistlib.InvalidFileException, BuildError):
                pass
        if proc.returncode != 0 or device is None:
            raise BuildError(
                f"hdiutil attach failed ({image.name}): " +
                proc.stderr.decode("utf-8", "replace")[-900:])
        if actual.resolve() != directory.resolve():
            raise BuildError(f"Mounted at unexpected path {actual}")
        print(f"Attached {image.name}: {device} at {actual}", flush=True)
        yield actual
    finally:
        if device is not None:
            detached = subprocess.run(["hdiutil", "detach", device],
                                      capture_output=True, timeout=180)
            if detached.returncode != 0:
                print(f"WARNING: could not detach {device}. Inspect only this disk: "
                      f"hdiutil detach {device}", file=sys.stderr)
            else:
                print(f"Detached {device}", flush=True)


def sudo(*args):
    run_checked(["sudo", *args])


def verify_candidate(destination):
    needed = [
        "sbin/launchd", "usr/lib/dyld", "usr/libexec/backboardd",
        "System/Library/CoreServices/SpringBoard.app/SpringBoard",
        "System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64",
        "private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64",
        "private/preboot/Cryptexes/App/System/Library",
    ]
    missing = [p for p in needed if not (destination / p).is_file()
               and not (destination / p).is_dir()]
    if missing:
        raise BuildError("Created root is missing essential files: " + ", ".join(missing))
    cache = destination / "System/Library/Caches/com.apple.dyld"
    parts = [p for p in cache.iterdir() if p.name.startswith("dyld_shared_cache_arm64")]
    if len(parts) < 40:
        raise BuildError("Expected roughly 44 dyld shared-cache companion files")
    return len(parts)


def compose(mounts, destination):
    os_mount, sysos_mount, appos_mount = (mounts[k] for k in ("os", "systemos", "appos"))
    # Ditto and rsync preserve file owner/mode/hardlinks only when run as root.
    # Every destination is inside the newly-created sparse HFS+ image.
    sudo("ditto", "--noqtn", str(os_mount), str(destination))
    preboot = destination / "private/preboot/Cryptexes"
    sudo("install", "-d", "-m", "0755", str(preboot / "OS"), str(preboot / "App"))
    sudo("ditto", "--noqtn", str(sysos_mount), str(preboot / "OS"))
    sudo("ditto", "--noqtn", str(appos_mount), str(preboot / "App"))
    cache_source = preboot / "OS/System/Library/Caches/com.apple.dyld"
    cache_dest = destination / "System/Library/Caches/com.apple.dyld"
    sudo("install", "-d", "-m", "0755", str(cache_dest))
    count = 0
    with os.scandir(cache_source) as entries:
        for item in entries:
            if item.is_file(follow_symlinks=False):
                target = cache_dest / item.name
                if target.exists():
                    raise BuildError(f"Unexpected existing shared-cache file {target}")
                sudo("ln", item.path, str(target))
                count += 1
    if count < 40:
        raise BuildError(f"Incomplete dyld cache: only {count} files")
    # Overlay cryptex files absent from OS. Skip shared cache (hardlinked).
    # Keep original source cryptex trees under /private/preboot.
    for source in (preboot / "OS", preboot / "App"):
        for sub in ("System", "usr"):
            src = source / sub
            if not src.is_dir() or src.is_symlink():
                continue
            target = destination / sub
            sudo("install", "-d", "-m", "0755", str(target))
            args = ["rsync", "-aH", "--ignore-existing"]
            if sub == "System":
                args += ["--exclude=/Library/Caches/com.apple.dyld/"]
            args += [str(src) + "/", str(target) + "/"]
            sudo(*args)
    print(f"Added {count} same-volume hard links for split dyld caches", flush=True)
    found = verify_candidate(destination)
    print(f"PASS: essential source files plus {found} dyld cache members", flush=True)


def build(directory, output, size_gib=24):
    if sys.platform != "darwin":
        raise BuildError("Run the build on macOS")
    view = plan(directory, output, size_gib)
    print(json.dumps(view, indent=2), flush=True)
    if not view["free_space_ok"]:
        raise BuildError(f"Need at least {MIN_FREE_GIB} GiB of Mac free disk space")
    for tool in ("hdiutil", "ditto", "rsync", "sudo", "install"):
        if shutil.which(tool) is None:
            raise BuildError(f"Missing macOS tool: {tool}")
    # Authentication before any image creation. We never grant a global sudo
    # shell and do not run the Python script itself as root.
    run_checked(["sudo", "-v"])
    out = validate_output(output)
    source = verify_inputs(directory)
    with tempfile.TemporaryDirectory(prefix="coral-hfs-build-", dir=out.parent) as tmp:
        workspace = Path(tmp).resolve()
        try:
            run_checked(["hdiutil", "create", "-type", "SPARSE",
                         "-size", f"{size_gib}g",
                         "-fs", "Case-sensitive Journaled HFS+",
                         "-volname", "CoralIOSRoot",
                         str(out)])
            if not out.is_file():
                raise BuildError("hdiutil did not create the sparseimage")
            with ExitStack() as stack:
                roots = {}
                for role in ("os", "systemos", "appos"):
                    roots[role] = stack.enter_context(
                        mounted(source / SOURCE_NAMES[role], workspace / role, readonly=True))
                dest = stack.enter_context(mounted(out, workspace / "candidate", readonly=False))
                compose(roots, dest)
                free = shutil.disk_usage(dest).free
                if free < 2 * 1024 ** 3:
                    print("WARNING: fewer than 2 GiB remain free inside candidate image",
                          file=sys.stderr)
        except Exception:
            print(f"Build interrupted. Candidate image remains at {out}; "
                  "it may be INCOMPLETE. Do not flash it.", file=sys.stderr)
            raise
    print(f"OFFLINE CANDIDATE COMPLETE: {out}", flush=True)
    print("NOT flash-ready: this is a macOS sparse disk image, not a raw HFS "
          "partition, and Coral UFS has not been proven", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", type=Path)
    parser.add_argument("output_sparseimage", type=Path)
    parser.add_argument("--size-gib", type=int, default=24)
    parser.add_argument("--execute", action="store_true",
                        help="actually create a new sparse HFS+ image; may ask for sudo")
    args = parser.parse_args()
    try:
        if args.execute:
            build(args.source_dir, args.output_sparseimage, args.size_gib)
        else:
            print(json.dumps(plan(args.source_dir, args.output_sparseimage,
                                  args.size_gib), indent=2))
    except (BuildError, OSError, ValueError, subprocess.CalledProcessError) as e:
        parser.error(str(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
