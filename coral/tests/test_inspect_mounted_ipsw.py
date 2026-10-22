#!/usr/bin/env python3
"""Synthetic mount responses only, no hdiutil process is ever executed."""
import importlib.util
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest

path=Path(__file__).resolve().parents[1]/"inspect_mounted_ipsw.py"
spec=importlib.util.spec_from_file_location("inspect_mounted_ipsw",path)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def plist_for(root):
    return plistlib.dumps({"system-entities":[
        {"dev-entry":"/dev/disk999"},
        {"dev-entry":"/dev/disk999s1","mount-point":str(root)}
    ]})


class TestMacReadOnly(unittest.TestCase):
    def test_reads_and_detaches_only_fresh_disk(self):
        with tempfile.TemporaryDirectory() as d:
            mount=Path(d)
            p=mount/"sbin/launchd"
            p.parent.mkdir()
            p.write_bytes(b"synthetic")
            calls=[]
            def runner(cmd, **kwargs):
                calls.append(cmd)
                if cmd[1]=="attach":
                    self.assertIn("-readonly",cmd)
                    self.assertIn("-nobrowse",cmd)
                    return subprocess.CompletedProcess(cmd,0,plist_for(mount),b"")
                return subprocess.CompletedProcess(cmd,0,b"detached",b"")
            result=mod.inspect_one(Path("/temporary/os.dmg"),"os",runner=runner)
            self.assertTrue(result["mounted"])
            self.assertTrue(result["detach_success"])
            self.assertEqual(calls[-1],["hdiutil","detach","/dev/disk999"])
            self.assertEqual(result["mounts"][0]["paths"]["sbin/launchd"]["bytes"],9)

    def test_failure_still_detaches_parseable_disk(self):
        with tempfile.TemporaryDirectory() as d:
            calls=[]
            def runner(cmd, **kwargs):
                calls.append(cmd)
                if cmd[1]=="attach":
                    return subprocess.CompletedProcess(cmd,1,plist_for(d),b"read-only mount failed")
                return subprocess.CompletedProcess(cmd,0,b"",b"")
            result=mod.inspect_one(Path("/temporary/os.dmg"),"os",runner=runner)
            self.assertIn("read-only mount failed",result["error"])
            self.assertTrue(result["detach_success"])
            self.assertEqual(calls[-1],["hdiutil","detach","/dev/disk999"])

    def test_no_mounted_volume_reported(self):
        data=plistlib.dumps({"system-entities":[{"dev-entry":"/dev/disk7"}]})
        calls=[]
        def runner(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd,0,data if cmd[1]=="attach" else b"",b"")
        r=mod.inspect_one(Path("os.dmg"),"os",runner=runner)
        self.assertFalse(r["mounted"])
        self.assertTrue(r["attached_readonly"])
        self.assertEqual(calls[-1],["hdiutil","detach","/dev/disk7"])

    def test_no_base_disk_never_detaches_unrelated_one(self):
        data=plistlib.dumps({"system-entities":[{"dev-entry":"/dev/rdisk1s1"}]})
        calls=[]
        def runner(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd,0,data,b"")
        r=mod.inspect_one(Path("os.dmg"),"os",runner=runner)
        self.assertIsNotNone(r["error"])
        self.assertEqual(len(calls),1)

    def test_inspection_does_not_follow_absolute_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"sbin").mkdir()
            (root/"sbin/launchd").symlink_to("/etc/passwd")
            details=mod.inspect_at_mount(root,"os")
            self.assertEqual(details["paths"]["sbin/launchd"]["type"],"symlink")
            self.assertEqual(details["paths"]["sbin/launchd"]["target"],"/etc/passwd")

    def test_parse_attached_disk(self):
        device,mounts=mod.parse_attach_response(plist_for("/Volumes/Fake Test"))
        self.assertEqual(device,"/dev/disk999")
        self.assertEqual(mounts,["/Volumes/Fake Test"])


if __name__=="__main__":
    unittest.main(verbosity=2)
