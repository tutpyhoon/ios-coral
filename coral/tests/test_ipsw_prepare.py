#!/usr/bin/env python3
"""Synthetic manifest+ZipFile tests, never embeds an Apple IPSW."""
import importlib.util
import json
from pathlib import Path
import plistlib
import tempfile
import unittest
import zipfile

p = Path(__file__).resolve().parents[1] / "ipsw_prepare.py"
spec = importlib.util.spec_from_file_location("ipsw_prepare", p)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

ROLES = ("OS", "Cryptex1,SystemOS", "Cryptex1,AppOS")
PATHS = ("Firmware/042-os.dmg", "Firmware/041-sysos.dmg", "Firmware/040-appos.dmg")


def fixture(path, *, build="20H392", version="16.7.16", board="d22ap",
            include_roles=ROLES, one_path_override=None):
    components = {}
    for index, role in enumerate(include_roles):
        member = PATHS[ROLES.index(role)]
        if one_path_override and index == 0:
            member = one_path_override
        components[role] = {"Info": {"Path": member}}
    manifest = {
        "ProductVersion": version, "ProductBuildVersion": build,
        "SupportedProductTypes": ["iPhone10,3", "iPhone10,6"],
        "BuildIdentities": [
            {"Info": {"DeviceClass": "d221ap", "RestoreBehavior": "Erase"},
             "Manifest": {"OS": {"Info": {"Path": "ignore.dmg"}}}},
            {"Info": {"DeviceClass": board, "RestoreBehavior": "Erase"},
             "Manifest": components},
        ],
    }
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("BuildManifest.plist", plistlib.dumps(manifest))
        for i, member in enumerate(PATHS):
            z.writestr(member, b"synthetic synthetic\0" + bytes([i]) * 64)


class IPSWTests(unittest.TestCase):
    def test_select_d22ap_all_three(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"example.ipsw"
            fixture(p)
            with zipfile.ZipFile(p) as z:
                result=a.identify(z)
                self.assertEqual(result["build"], "20H392")
                self.assertEqual([x["role"] for x in result["files"]],
                                 ["os","systemos","appos"])
                self.assertEqual([x["output"] for x in result["files"]],
                                 ["os.dmg","systemos.dmg","appos.dmg"])

    def test_extract_without_touching_original(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            ipsw=root/"test.ipsw"
            fixture(ipsw)
            target=root/"extracted"
            original=ipsw.read_bytes()
            result=a.run(ipsw,target)
            self.assertEqual(len(result["files"]),3)
            self.assertTrue((target/"os.dmg").is_file())
            self.assertTrue((target/"local-image-report.json").is_file())
            self.assertEqual(ipsw.read_bytes(),original)

    def test_never_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            ipsw=root/"test.ipsw"
            fixture(ipsw)
            output=root/"imgs"
            output.mkdir()
            (output/"os.dmg").write_bytes(b"keep")
            with self.assertRaises(a.IPSWError):
                a.run(ipsw,output)
            self.assertEqual((output/"os.dmg").read_bytes(),b"keep")

    def test_wrong_firmware_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"old.ipsw"
            fixture(p,version="16.7.15",build="20H380")
            with self.assertRaises(a.IPSWError):
                a.run(p)

    def test_missing_cryptex_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"short.ipsw"
            fixture(p,include_roles=ROLES[:2])
            with self.assertRaises(a.IPSWError):
                a.run(p)

    def test_wrong_board_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"board.ipsw"
            fixture(p,board="d20ap")
            with self.assertRaises(a.IPSWError):
                a.run(p)

    def test_reject_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"unsafe.ipsw"
            fixture(p,one_path_override="../steal.dmg")
            with self.assertRaises(a.IPSWError):
                a.run(p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
