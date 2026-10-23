#!/usr/bin/env python3
"""Synthetic-only one-shot orchestration tests; does not call gh/adb/fastboot."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import one_shot_coral as app


class OneShotTests(unittest.TestCase):
    def test_refuses_destroy_without_exact_confirmation(self):
        with mock.patch.object(app,"ensure_mac") as x:
            with self.assertRaisesRegex(RuntimeError,"--confirm"):
                app.execute(Path("/fake"),Path("/fake"),39889361147,None,"")
            x.assert_not_called()

    def test_refuses_mismatched_boot_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            img=folder/"coral-full-flame-UFS-UNTESTED.img"
            img.write_bytes(b"fake\0not-a-boot-image")
            j={
                "root_mode":"ufs",
                "userdata_must_be_installed_first":True,
                "full_flame_source_pin":app.UPSTREAM_SHA,
                "model":"Pixel 4 XL (coral)",
                "boot_sha256":"deadbeef"
            }
            (folder/"manifest.json").write_text(json.dumps(j))
            (folder/"SHA256SUMS").write_text("deadbeef  "+img.name+"\n")
            with self.assertRaisesRegex(RuntimeError,"checksum mismatch"):
                app.checked_boot_img(folder)

    def test_valid_manifest_and_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            img=folder/"coral-full-flame-UFS-UNTESTED.img"
            data=b"synthetic boot"
            img.write_bytes(data)
            digest=hashlib.sha256(data).hexdigest()
            j={
                "root_mode":"ufs",
                "userdata_must_be_installed_first":True,
                "full_flame_source_pin":app.UPSTREAM_SHA,
                "model":"Pixel 4 XL (coral)",
                "boot_sha256":digest
            }
            (folder/"manifest.json").write_text(json.dumps(j))
            (folder/"SHA256SUMS").write_text(digest+"  "+img.name+"\n")
            self.assertEqual(app.checked_boot_img(folder),img)

    def test_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            (folder/"existing").write_text("keep")
            with self.assertRaisesRegex(RuntimeError,"Refusing to overwrite"):
                app.fresh_folder(folder)


if __name__=="__main__":
    unittest.main(verbosity=2)
