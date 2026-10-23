#!/usr/bin/env python3
"""Synthetic HFS+ byte-level tests. No Apple files, mounts, or device calls."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

path=Path(__file__).resolve().parents[1]/"finalize_ios_root.py"
spec=importlib.util.spec_from_file_location("finalize_ios_root",path)
import sys
sys.path.insert(0,str(path.parent))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def fake(path, *, trailer=False, signature=b"H+"):
    blocks=128
    blocksize=4096
    length=blocks*blocksize
    with path.open("wb") as f:
        f.truncate(length+(512 if trailer else 0))
        f.seek(1024)
        hdr=bytearray(512)
        hdr[:2]=signature
        struct.pack_into(">II",hdr,40,blocksize,blocks)
        f.write(hdr)
        if trailer:
            f.seek(length)
            f.write(b"koly"+b"\0"*508)
    return length


class RawHfsTests(unittest.TestCase):
    def test_valid_bare_hfs_plus(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.img"
            size=fake(p)
            r=m.check_hfs_bytes(p)
            self.assertEqual(r["raw_bytes"],size)
            self.assertEqual(r["udif_trailer_bytes"],0)

    def test_valid_udrw_trailer(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.dmg"
            size=fake(p,trailer=True)
            r=m.check_hfs_bytes(p)
            self.assertEqual(r["raw_bytes"],size)
            self.assertEqual(r["udif_trailer_bytes"],512)

    def test_unknown_trailer_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.dmg"
            fake(p,trailer=True)
            with p.open("r+b") as f:
                f.seek(-512,2)
                f.write(b"BAD!")
            with self.assertRaises(m.RootError):
                m.check_hfs_bytes(p)

    def test_unknown_filesystem_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.dmg"
            fake(p,signature=b"NT")
            with self.assertRaises(m.RootError):
                m.check_hfs_bytes(p)

    def test_bad_blocksize_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.dmg"
            fake(p)
            with p.open("r+b") as f:
                f.seek(1024+40)
                f.write(struct.pack(">I",4095))
            with self.assertRaises(m.RootError):
                m.check_hfs_bytes(p)

if __name__=="__main__":
    unittest.main(verbosity=2)
