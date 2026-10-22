#!/usr/bin/env python3
"""Synthetic Mach-O/virtual-root regression tests. No Apple binaries."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

modfile = Path(__file__).resolve().parents[1] / "ios_root_audit.py"
spec = importlib.util.spec_from_file_location("ios_root_audit", modfile)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def command(cmd, body):
    return struct.pack("<II", cmd, 8 + len(body)) + body


def string_command(cmd, value):
    val = value.encode() + b"\0"
    return command(cmd, struct.pack("<I", 12) + val)


def make_macho(loader=None, dylibs=(), kind=2, arch=0x0100000c):
    cmds = [string_command(0xe, loader)] if loader else []
    cmds.extend(string_command(0xc, s) for s in dylibs)
    cmds.append(command(0x1d, struct.pack("<II", 1234, 5678)))
    header = struct.pack("<8I", 0xfeedfacf, arch, 0, kind, len(cmds),
                         sum(map(len, cmds)), 0, 0)
    return header + b"".join(cmds) + b"ignored text"


def put(root, name, data):
    target = root / name.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


class AuditTests(unittest.TestCase):
    def test_parse_macho(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "testbin"
            p.write_bytes(make_macho("/usr/lib/dyld", ("/usr/lib/libSystem.B.dylib",)))
            j=m.parse_macho_header(p)
            self.assertTrue(j["arm64"])
            self.assertEqual(j["filetype"], 2)
            self.assertEqual(j["dynamic_loader"], "/usr/lib/dyld")
            self.assertEqual(j["required_dylibs"], ["/usr/lib/libSystem.B.dylib"])
            self.assertTrue(j["has_code_signature_command"])

    def test_complete_synthetic_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            exe = make_macho("/usr/lib/dyld")
            for path in ["/sbin/launchd", "/usr/libexec/backboardd",
                         "/System/Library/CoreServices/SpringBoard.app/SpringBoard"]:
                put(root, path, exe)
            put(root, "/usr/lib/dyld", make_macho(kind=7))
            put(root, "/System/Cryptexes/OS/System/Library/dyld/dyld_shared_cache_arm64",
                b"dyld_v1  arm64\0" + b"\0" * 64)
            j=m.audit(root)
            self.assertTrue(j["all_critical_present"])
            self.assertTrue(j["files"]["dyld_shared_cache"]["valid_dyld_cache_header"])
            self.assertEqual(j["files"]["springboard"]["dynamic_loader"], "/usr/lib/dyld")
            self.assertIsNone(j.get("executable"))
            self.assertEqual(j["full_root_fits_in_ram"], "not established")

    def test_absolute_symlink_lives_inside_ios_root(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            put(root, "/System/Cryptexes/OS/dyld", make_macho(kind=7))
            (root / "usr/lib").mkdir(parents=True)
            (root / "usr/lib/dyld").symlink_to("/System/Cryptexes/OS/dyld")
            p=m.bounded_resolve(root, "/usr/lib/dyld")
            self.assertEqual(p, root/"System/Cryptexes/OS/dyld")

    def test_reject_root_escape(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"usr").mkdir()
            (root/"usr/lib").symlink_to("../../../../etc")
            with self.assertRaises((ValueError,FileNotFoundError)):
                m.bounded_resolve(root, "/usr/lib/passwd")

    def test_missing_is_not_ready(self):
        with tempfile.TemporaryDirectory() as d:
            j=m.audit(Path(d))
            self.assertFalse(j["all_critical_present"])
            self.assertFalse(j["files"]["launchd"]["present"])

    def test_truncated_command_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"bad"
            p.write_bytes(struct.pack("<8I",0xfeedfacf,0x0100000c,0,2,1,2000,0,0)+b"x")
            with self.assertRaises(ValueError):
                m.parse_macho_header(p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
