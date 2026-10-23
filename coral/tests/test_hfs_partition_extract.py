#!/usr/bin/env python3
"""Generate a tiny entirely synthetic GUID HFS disk for CRC/extraction tests."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hfs_partition_extract as p


def fake_gpt(path):
    total_lbas=4130
    start,end=2048,4095
    f=bytearray(total_lbas*512)
    f[510:512]=b"\x55\xaa"
    # protective MBR partition and GPT array
    f[446+4]=0xee
    e=bytearray(128*128)
    e[:16]=p.APPLE_HFS
    struct.pack_into("<QQ",e,32,start,end)
    f[1024:1024+len(e)]=e
    h=bytearray(512)
    h[:8]=b"EFI PART"
    struct.pack_into("<III",h,8,0x00010000,92,0)
    struct.pack_into("<QQ",h,24,1,total_lbas-1)
    struct.pack_into("<QQ",h,40,34,total_lbas-34)
    struct.pack_into("<Q",h,72,2)
    struct.pack_into("<III",h,80,128,128,zlib.crc32(e)&0xffffffff)
    struct.pack_into("<I",h,16,zlib.crc32(h[:92])&0xffffffff)
    f[512:1024]=h
    fs=start*512
    f[fs+1024:fs+1026]=b"HX"
    struct.pack_into(">II",f,fs+1024+40,4096,256)
    path.write_bytes(f)
    return end-start+1


class GPTExtractTests(unittest.TestCase):
    def test_partition_is_found_and_moved(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"fake.dmg"
            blocks=fake_gpt(path)
            result=p.locate_gpt_hfs(path)
            self.assertTrue(result["gpt_header_crc_verified"])
            self.assertTrue(result["gpt_entry_array_crc_verified"])
            self.assertEqual(result["start_lba"],2048)
            self.assertEqual(result["volume_bytes"],blocks*512)
            info=p.remove_gpt_inplace(path)
            self.assertEqual(info["raw_bytes"],blocks*512)
            self.assertEqual(path.stat().st_size,1024*1024)
            with path.open("rb") as f:
                self.assertEqual(f.read(8),b"\0"*8)
                hdr=p.hfs_header_at(f,0,path.stat().st_size)
            self.assertEqual(hdr["signature"],"HX")

    def test_bad_primary_crc_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"bad.dmg"
            fake_gpt(path)
            with path.open("r+b") as f:
                f.seek(512+24)
                f.write(b"\x04")
            with self.assertRaisesRegex(p.GPTError,"header CRC"):
                p.locate_gpt_hfs(path)

    def test_bad_partition_crc_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"bad.dmg"
            fake_gpt(path)
            with path.open("r+b") as f:
                f.seek(1024+60)
                f.write(b"\x01")
            with self.assertRaisesRegex(p.GPTError,"array CRC"):
                p.locate_gpt_hfs(path)

    def test_reject_non_hfs_guid(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"bad.dmg"
            fake_gpt(path)
            with path.open("r+b") as f:
                f.seek(1024)
                f.write(b"\x11")
                f.seek(1024)
                entries=f.read(128*128)
                crc=zlib.crc32(entries)&0xffffffff
                f.seek(512+88)
                f.write(struct.pack("<I",crc))
                f.seek(512)
                header=bytearray(f.read(92))
                header[16:20]=b"\0"*4
                f.seek(512+16)
                f.write(struct.pack("<I",zlib.crc32(header)&0xffffffff))
            with self.assertRaisesRegex(p.GPTError,"exactly one"):
                p.locate_gpt_hfs(path)

if __name__=="__main__":
    unittest.main(verbosity=2)
