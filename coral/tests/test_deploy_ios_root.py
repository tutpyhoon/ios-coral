#!/usr/bin/env python3
"""Synthetic no-phone tests for guarded raw HFS USERDATA installer."""
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import deploy_ios_root as app

def sparse_raw(path):
    with path.open("wb") as f:
        f.truncate(8*1024**3)
        f.seek(1024)
        f.write(b"HX")
        f.seek(1024+40)
        f.write(struct.pack(">II",4096,(8*1024**3)//4096))

def stub_remote(cmd):
    if "getprop ro.product.device" in cmd:return "coral"
    if "getprop ro.product.vendor.device" in cmd:return "coral"
    if "getprop ro.bootmode" in cmd:return "recovery"
    if "getprop ro.boot.mode" in cmd:return "recovery"
    if "id -u" in cmd:return "0"
    if "cat /proc/mounts" in cmd:return "tmpfs /tmp tmpfs rw 0 0"
    if "readlink -f" in cmd:return "/dev/block/sda15"
    if "uevent" in cmd:return "MAJOR=8\nMINOR=15\nPARTNAME=userdata\n"
    if "blockdev --getsize64" in cmd:return str(64*1024**3)
    if "blockdev --getro" in cmd:return "0"
    raise AssertionError("Unexpected synthetic device command: "+cmd)

class DeployTests(unittest.TestCase):
    def test_valid_mock_coral_read_only_preflight(self):
        with tempfile.TemporaryDirectory() as d:
            img=Path(d)/"raw.img"
            sparse_raw(img)
            with mock.patch.object(app,"adb",return_value="List of devices attached\nFAKE123\tdevice"), \
                 mock.patch.object(app,"remote",side_effect=stub_remote):
                result=app.plan(img)
            self.assertEqual(result["device"]["partname"],"userdata")
            self.assertEqual(result["source_raw_hfs"]["hfs"]["signature"],"HX")
            self.assertEqual(result["source_raw_hfs"]["bytes"],8*1024**3)
            self.assertEqual(result["status"],"INSPECT ONLY — NO WRITES")

    def test_refuse_wrong_phone(self):
        def remote(cmd):
            if "getprop" in cmd: return "flame"
            return stub_remote(cmd)
        with mock.patch.object(app,"adb",return_value="List of devices attached\nFAKE123\tdevice"), \
             mock.patch.object(app,"remote",side_effect=remote):
            with self.assertRaisesRegex(app.DeployError,"does not match"):
                app.device_info()

    def test_refuse_rooted_android_not_in_recovery(self):
        def remote(cmd):
            if "getprop ro.bootmode" in cmd:return "normal"
            if "getprop ro.boot.mode" in cmd:return "normal"
            return stub_remote(cmd)
        with mock.patch.object(app,"adb",return_value="List of devices attached\nFAKE123\tdevice"), \
             mock.patch.object(app,"remote",side_effect=remote):
            with self.assertRaisesRegex(app.DeployError,"NOT in recovery mode"):
                app.device_info()

    def test_refuse_mounted_data(self):
        def remote(cmd):
            if "cat /proc/mounts" in cmd:return "/dev/block/dm-0 /data ext4 rw 0 0"
            return stub_remote(cmd)
        with mock.patch.object(app,"adb",return_value="List of devices attached\nFAKE123\tdevice"), \
             mock.patch.object(app,"remote",side_effect=remote):
            with self.assertRaisesRegex(app.DeployError,"mounted"):
                app.device_info()

    def test_refuse_wrong_partition_label(self):
        def remote(cmd):
            if "/uevent" in cmd:return "PARTNAME=modemst1\n"
            return stub_remote(cmd)
        with mock.patch.object(app,"adb",return_value="List of devices attached\nFAKE123\tdevice"), \
             mock.patch.object(app,"remote",side_effect=remote):
            with self.assertRaisesRegex(app.DeployError,"partition as userdata"):
                app.device_info()

    def test_refuse_gpt_wrapped_image(self):
        with tempfile.TemporaryDirectory() as d:
            img=Path(d)/"bad.img"
            sparse_raw(img)
            with img.open("r+b") as f:
                f.seek(512)
                f.write(b"EFI PART")
            with self.assertRaisesRegex(app.DeployError,"GPT container"):
                app.raw_info(img)

    def test_refuse_dangerous_unconfirmed_operation_before_adb(self):
        with mock.patch.object(app,"adb") as adb:
            with self.assertRaisesRegex(app.DeployError,"confirmation token"):
                app.install(Path("/irrelevant"),Path("/tmp/irrelevant"),"NO")
            adb.assert_not_called()

if __name__=="__main__":
    unittest.main(verbosity=2)
