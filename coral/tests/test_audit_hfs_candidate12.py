#!/usr/bin/env python3
"""Synthetic source-only regression tests, no real Apple binaries and no hdiutil."""
import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

folder=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(folder))
spec=importlib.util.spec_from_file_location("audit_hfs_candidate12",folder/"audit_hfs_candidate12.py")
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

def create_file(root,relative,b):
    p=root/relative
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(b)
    return p

def macho(kind=2, dynamic=False):
    # LC_LOAD_DYLINKER is required by the strict audit for real launchd.
    command=(struct.pack("<3I",0xe,12+len(b"/usr/lib/dyld")+1,12) +
             b"/usr/lib/dyld\0") if dynamic else b""
    return struct.pack("<8I",0xfeedfacf,0x100000c,0,kind,
                       int(dynamic),len(command),0,0)+command

def fixture(root):
    for relative in ("sbin/launchd","usr/libexec/backboardd",
                     "System/Library/CoreServices/SpringBoard.app/SpringBoard"):
        create_file(root,relative,macho(dynamic=(relative=="sbin/launchd")) )
    create_file(root,"usr/lib/dyld",macho(7))
    source=root/"private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld"
    target=root/"System/Library/Caches/com.apple.dyld"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    (root/"private/preboot/Cryptexes/App/System/Library").mkdir(parents=True)
    total=3330359296
    for n in range(44):
        name="dyld_shared_cache_arm64" + (f".{n:02d}" if n else "")
        data=b"dyld_v1  arm64\x00" if n==0 else b"x"
        p=source/name
        p.write_bytes(data)
        if n==43:
            with p.open("ab") as f:
                f.truncate(total - sum(x.stat().st_size for x in source.iterdir() if x!=p))
        os.link(p,target/name)

class CandidateAuditTests(unittest.TestCase):
    def test_valid_44_part_synthetic_cache(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            fixture(root)
            report=app.validate(root)
            self.assertTrue(report["structurally_complete"],report)
            self.assertEqual(report["cache_subfiles"]["count"],44)
            self.assertEqual(report["cache_subfiles"]["total_apparent_bytes"],3330359296)
            self.assertFalse(report["ready_for_runtime_testing"])

    def test_broken_hardlink_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            fixture(root)
            item=root/"System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64.01"
            item.unlink()
            item.write_bytes(b"x")
            report=app.validate(root)
            self.assertFalse(report["structurally_complete"])
            self.assertTrue(report["cache_subfiles"]["hardlink_errors"])

if __name__=="__main__":
    unittest.main(verbosity=2)
