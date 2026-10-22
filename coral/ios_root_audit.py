#!/usr/bin/env python3
"""CORAL Phase 12 read-only local iOS root dependency inventory.

Run *on your computer* against an existing OS + cryptex merged directory:
    python3 coral/ios_root_audit.py /path/to/ios-root [--strict]
No downloads, mounts, writes, upload, network, code execution or partition I/O.
A structural scan is NOT proof that Apple userland can run on CORAL.
"""
import argparse
import json
import os
from pathlib import Path
import struct
import sys

MACHO_LE64 = b"\xcf\xfa\xed\xfe"
CPU_TYPE_ARM64 = 0x0100000c
MH_EXECUTE = 2
LC_LOAD_DYLINKER = 0xe
LC_LOAD_DYLIB = 0xc
LC_ID_DYLIB = 0xd
LC_LOAD_WEAK_DYLIB = 0x18
LC_REEXPORT_DYLIB = 0x1f
LC_LOAD_UPWARD_DYLIB = 0x23
LC_LAZY_LOAD_DYLIB = 0x20
LC_RPATH = 0x1c
LC_CODE_SIGNATURE = 0x1d
MAX_LOAD_CMDS = 4096
MAX_COMMAND_BYTES = 4 * 1024 * 1024
RAM_CANDIDATE = 1 << 30

FILES = {
    "launchd": ("/sbin/launchd",),
    "dyld": ("/usr/lib/dyld", "/System/Library/dyld/dyld"),
    "backboardd": ("/usr/libexec/backboardd",),
    "springboard": ("/System/Library/CoreServices/SpringBoard.app/SpringBoard",),
    "dyld_shared_cache": (
        "/System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64",
        "/System/Library/dyld/dyld_shared_cache_arm64",
        "/System/Cryptexes/OS/System/Library/dyld/dyld_shared_cache_arm64",
        "/System/Library/dyld/dyld_shared_cache_arm64e",
    ),
}


def bounded_resolve(root: Path, virtual: str):
    """Follow in-root links only. Absolute iOS links refer to the root, not macOS."""
    pending = [c for c in virtual.split("/") if c not in ("", ".")]
    parts = []
    hops = 0
    while pending:
        name = pending.pop(0)
        if name == "..":
            if not parts:
                raise ValueError("Link escapes root")
            parts.pop()
            continue
        parts.append(name)
        candidate = root.joinpath(*parts)
        if candidate.is_symlink():
            hops += 1
            if hops > 32:
                raise ValueError("Too many or circular symlinks")
            target = os.readlink(candidate)
            if target.startswith("/"):
                parts = []
            else:
                parts.pop()
            pending = [x for x in target.split("/") if x not in ("", ".")] + pending
    result = root.joinpath(*parts)
    if not result.is_file():
        raise FileNotFoundError(virtual)
    if not result.resolve().is_relative_to(root):
        raise ValueError("File resolves outside audited root")
    return result


def parse_macho_header(path: Path):
    with path.open("rb") as f:
        hdr = f.read(32)
        if len(hdr) != 32 or hdr[:4] != MACHO_LE64:
            raise ValueError("Not an unwrapped little-endian 64-bit Mach-O")
        _, cputype, subtype, kind, ncmds, sizeofcmds, _, _ = struct.unpack("<8I", hdr)
        if ncmds > MAX_LOAD_CMDS or sizeofcmds > MAX_COMMAND_BYTES or sizeofcmds < ncmds * 8:
            raise ValueError("Invalid or excessive load-command range")
        cmds = f.read(sizeofcmds)
        if len(cmds) != sizeofcmds:
            raise ValueError("Truncated Mach-O load commands")
    needed, loader, rpaths, signed = [], None, [], False
    off = 0
    for _ in range(ncmds):
        if off + 8 > len(cmds):
            raise ValueError("Truncated Mach-O command header")
        cmd, size = struct.unpack_from("<2I", cmds, off)
        if size < 8 or off + size > len(cmds):
            raise ValueError("Bad Mach-O load command size")
        base = cmd & 0x7fffffff
        if base in {LC_LOAD_DYLINKER, LC_LOAD_DYLIB, LC_ID_DYLIB,
                    LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LOAD_UPWARD_DYLIB,
                    LC_LAZY_LOAD_DYLIB, LC_RPATH}:
            # lc_str offset lies at +8 for dylinker/rpath, +8 for dylib
            if size < 12:
                raise ValueError("Short string command")
            pos = struct.unpack_from("<I", cmds, off + 8)[0]
            if not 8 <= pos < size:
                raise ValueError("Invalid load-command string offset")
            token = cmds[off + pos:off + size].split(b"\0", 1)[0].decode("utf-8", "replace")
            if base == LC_LOAD_DYLINKER:
                loader = token
            elif base == LC_RPATH:
                rpaths.append(token)
            elif base != LC_ID_DYLIB:
                needed.append(token)
        if base == LC_CODE_SIGNATURE:
            signed = True
        off += size
    return {
        "format": "Mach-O 64", "arm64": cputype == CPU_TYPE_ARM64,
        "cpu_subtype": subtype, "filetype": kind,
        "dynamic_loader": loader, "required_dylibs": needed,
        "rpaths": rpaths, "has_code_signature_command": signed,
    }


def audit(root: Path):
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Expected a local extracted iOS root directory")
    result = {
        "audit": "offline structural inspection only",
        "files": {}, "warnings": [], "all_critical_present": True,
        "ram_candidate_bytes": RAM_CANDIDATE,
        "disk_root_required_for_full_ios": "unknown; measure source root locally",
    }
    sizes = []
    for role, locations in FILES.items():
        for virtual in locations:
            try:
                path = bounded_resolve(root, virtual)
                break
            except (FileNotFoundError, ValueError, OSError):
                continue
        else:
            result["files"][role] = {"present": False}
            result["all_critical_present"] = False
            continue
        item = {"present": True, "virtual_path": virtual,
                "bytes": path.stat().st_size}
        sizes.append(item["bytes"])
        if role == "dyld_shared_cache":
            with path.open("rb") as f:
                magic = f.read(16)
            item["dyld_cache_magic"] = magic.decode("ascii", "backslashreplace")
            item["valid_dyld_cache_header"] = magic.startswith(b"dyld_v1")
            if not item["valid_dyld_cache_header"]:
                result["warnings"].append("dyld shared cache: unexpected header")
                result["all_critical_present"] = False
        else:
            try:
                item.update(parse_macho_header(path))
            except ValueError as e:
                item["mach_o_error"] = str(e)
                result["warnings"].append(f"{role}: {e}")
            if not item.get("arm64", False):
                result["all_critical_present"] = False
            if role != "dyld" and item.get("filetype") != MH_EXECUTE:
                result["warnings"].append(f"{role}: expected MH_EXECUTE")
                result["all_critical_present"] = False
            if role == "launchd" and not item.get("dynamic_loader"):
                result["warnings"].append("launchd: missing LC_LOAD_DYLINKER")
                result["all_critical_present"] = False
        result["files"][role] = item
    # This lower bound is intentionally NOT the total install size; cryptex,
    # shared-cache subfiles, services, frameworks and app resources add more.
    result["known_files_size_lower_bound"] = sum(sizes)
    result["known_files_alone_exceed_candidate_ram"] = sum(sizes) > RAM_CANDIDATE
    result["full_root_fits_in_ram"] = "not established"
    result["note"] = ("Finding binaries proves neither bootability nor code-signing "
                      "trust, dyld compatibility, IOKit support, or SpringBoard output.")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", type=Path, help="user-owned, locally extracted merged iOS root")
    p.add_argument("--strict", action="store_true", help="fail if missing/invalid essential paths")
    a = p.parse_args()
    try:
        outcome = audit(a.root)
    except (ValueError, OSError) as e:
        p.error(str(e))
    print(json.dumps(outcome, indent=2))
    if a.strict and not outcome["all_critical_present"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
