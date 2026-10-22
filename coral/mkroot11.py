#!/usr/bin/env python3
"""Build a private 16 MiB HFS+ RAM root containing Phase 11 PID1 and child.

macOS hdiutil is used only on a disposable local disk image. This script
NEVER accesses any attached/physical phone or existing Mac volume. Uses the
upstream pinned FLAME HFS inspector and keeps its metadata contract so the
existing CORAL loader/packer can validate the new HFS test.
"""
import argparse
import hashlib
import json
import plistlib
from pathlib import Path
import subprocess
import sys
import tempfile

def call(*args):
    subprocess.run([str(x) for x in args], check=True)

def build(upstream: Path, parent: Path, child: Path, out: Path):
    sys.path.insert(0, str((upstream / "flame").resolve()))
    from mkroot import inspect_hfs, raw_udrw, CHECK_CONTENTS
    if sys.platform != "darwin":
        raise RuntimeError("This phase requires macOS hdiutil")
    parent, child, out = parent.resolve(), child.resolve(), out.resolve()
    if out.exists() or out.with_suffix(".json").exists():
        raise FileExistsError("Refusing to overwrite existing root or manifest")
    binaries={}
    for tag, p in (("parent", parent), ("child", child)):
        b=p.read_bytes()
        if not (1024 < len(b) < 131072 and b[:4] == b"\xcf\xfa\xed\xfe"):
            raise ValueError(f"{tag}: not bounded 64-bit Mach-O")
        binaries[tag]=b
    with tempfile.TemporaryDirectory(prefix="coral-phase11-") as d:
        work=Path(d)
        image=work/"root.dmg"
        mount=work/"mnt"
        mount.mkdir()
        call("hdiutil", "create", "-size", "16m", "-fs", "HFS+", "-volname",
             "CoralRAM", "-layout", "NONE", "-type", "UDIF", image)
        attached=False
        try:
            result=subprocess.check_output([
                "hdiutil","attach","-nobrowse","-owners","on",
                "-mountpoint", str(mount), "-plist", str(image)])
            attached=True
            entities=plistlib.loads(result)["system-entities"]
            device=next(e["dev-entry"] for e in entities if e.get("mount-point")==str(mount))
            for sub in ("sbin", "bin", "dev", "etc", "tmp", "private", "private/var"):
                call("sudo", "install", "-d", "-o", "0", "-g", "0", "-m", "0755", mount/sub)
            call("sudo", "chown", "0:0", mount)
            call("sudo", "chmod", "0755", mount)
            call("sudo", "install", "-o", "0", "-g", "0", "-m", "0755", parent, mount/"sbin/launchd")
            call("sudo", "install", "-o", "0", "-g", "0", "-m", "0755", child, mount/"bin/coral-child")
            marker=work/"flame-test"
            marker.write_bytes(CHECK_CONTENTS)
            call("sudo", "install", "-o", "0", "-g", "0", "-m", "0644", marker, mount/"etc/flame-test")
            assert (mount/"sbin/launchd").read_bytes()==binaries["parent"]
            assert (mount/"bin/coral-child").read_bytes()==binaries["child"]
            assert (mount/"etc/flame-test").read_bytes()==CHECK_CONTENTS
            call("hdiutil", "detach", device)
            attached=False
        finally:
            if attached:
                call("hdiutil","detach",mount)
        raw=raw_udrw(image.read_bytes())
    metadata=inspect_hfs(raw)
    metadata.update({
        "volume_name": "CoralRAM",
        "root_sha256": hashlib.sha256(raw).hexdigest(),
        "init_sha256": hashlib.sha256(binaries["parent"]).hexdigest(),
        "child_sha256": hashlib.sha256(binaries["child"]).hexdigest(),
        "child_path": "/bin/coral-child",
        "check_path": "/etc/flame-test",
        "check_contents": CHECK_CONTENTS.decode(),
        "source": "coral/phase11_pid1.S and coral/phase11_child.S",
    })
    out.write_bytes(raw)
    out.with_suffix(".json").write_text(json.dumps(metadata,indent=2)+"\n")
    print(json.dumps(metadata,indent=2))

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("upstream",type=Path)
    ap.add_argument("parent",type=Path)
    ap.add_argument("child",type=Path)
    ap.add_argument("output",type=Path)
    args=ap.parse_args()
    build(args.upstream,args.parent,args.child,args.output)
