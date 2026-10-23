#!/usr/bin/env python3
"""Synthetic tests; no GitHub artifact downloads or connected devices."""
import hashlib,json
from pathlib import Path
import sys,tempfile,unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_full_xnu_ufs as diag

class Tests(unittest.TestCase):
    def test_manifest_and_hash_are_checked(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            img=folder/diag.IMAGE_NAME
            # A sparse file is sufficient for SHA256 verification.
            with img.open("wb") as f:f.truncate(67108864)
            digest=diag.digest(img)
            info={
                "root_mode":"ufsdiag","coralufsdiag":True,
                "kernel_has_three_ufs_write_fences":True,
                "ufs_media_write_commands_enabled":False,
                "hfs_sha256":"synthetic",
                "model":"Pixel 4 XL (coral)",
                "dtb_sha256":"f582348d19807e8f4681e6c226c9947ef64a380ef1c85c487458f7bf085b89da",
                "boot_sha256":digest}
            (folder/"manifest.json").write_text(json.dumps(info))
            (folder/"SHA256SUMS").write_text(f"{digest}  {img.name}\n")
            self.assertEqual(diag.verify(folder)["root_mode"],"ufsdiag")
            info["ufs_media_write_commands_enabled"]=True
            (folder/"manifest.json").write_text(json.dumps(info))
            with self.assertRaises(AssertionError):
                diag.verify(folder)

    def test_no_device_action_without_confirmation(self):
        with mock.patch.object(diag.shutil,"which") as which:
            with self.assertRaisesRegex(ValueError,"--confirm"):
                diag.execute(123,Path("/tmp/test-synth"),"")
            which.assert_not_called()

    def test_refuse_wrong_fastboot_device(self):
        m=mock.Mock(returncode=0,stdout="",stderr="(bootloader) product: flame\n")
        with mock.patch.object(diag.subprocess,"run",return_value=m):
            with self.assertRaisesRegex(ValueError,"not report product"):
                diag.check_fastboot_coral()

    def test_read_only_by_default(self):
        p=diag.plan(123)
        self.assertTrue(p["no_userdata_install"])
        self.assertTrue(p["no_scsi_media_writes"])
        self.assertTrue(p["uses_ufs_dma"])

if __name__=="__main__": unittest.main(verbosity=2)
