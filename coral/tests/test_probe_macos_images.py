#!/usr/bin/env python3
"""Synthetic-only tests for the local read-only Mac image probe."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

p=Path(__file__).resolve().parents[1]/"probe_macos_images.py"
spec=importlib.util.spec_from_file_location("probe_macos_images",p)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def make_fake_images(root):
    records=[]
    data_map={"os":b"raw os", "systemos":b"small systemos", "appos":b"small appos"}
    for role,data in data_map.items():
        filename=role+".dmg"
        (root/filename).write_bytes(data)
        records.append({"role":role,"name":filename,"bytes":len(data),
                        "sha256":hashlib.sha256(data).hexdigest()})
    (root/"local-image-report.json").write_text(json.dumps({
        "version":"16.7.16","build":"20H392","device":"iPhone10,3",
        "board":"d22ap","files":records
    }))
    return {k:len(v) for k,v in data_map.items()}


class ProbeTests(unittest.TestCase):
    def test_complete_report_and_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            sizes=make_fake_images(root)
            with mock.patch.object(mod,"EXPECTED_EXTRACTED_SIZES",sizes):
                result=mod.inspect(root,run_tools=False)
            self.assertEqual(len(result["files"]),3)
            self.assertTrue(all(x["sha256_verified"] for x in result["files"]))
            self.assertIsNone(result["images_usable_on_macos"])

    def test_corrupt_image_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            sizes=make_fake_images(root)
            (root/"appos.dmg").write_bytes(b"x"*sizes["appos"])
            with mock.patch.object(mod,"EXPECTED_EXTRACTED_SIZES",sizes):
                with self.assertRaisesRegex(mod.ImageCheckError,"SHA-256 mismatch"):
                    mod.inspect(root,run_tools=False)

    def test_report_size_mismatch_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            sizes=make_fake_images(root)
            sizes["os"]+=1
            with mock.patch.object(mod,"EXPECTED_EXTRACTED_SIZES",sizes):
                with self.assertRaisesRegex(mod.ImageCheckError,"size mismatch"):
                    mod.inspect(root,run_tools=False)

    def test_rejects_symlinked_image(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            sizes=make_fake_images(root)
            (root/"os.dmg").unlink()
            (root/"os.dmg").symlink_to(root/"systemos.dmg")
            with mock.patch.object(mod,"EXPECTED_EXTRACTED_SIZES",sizes):
                with self.assertRaisesRegex(mod.ImageCheckError,"symlinked"):
                    mod.inspect(root,run_tools=False)

    def test_rejects_changed_version(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            sizes=make_fake_images(root)
            report=root/"local-image-report.json"
            j=json.loads(report.read_text())
            j["build"]="other"
            report.write_text(json.dumps(j))
            with mock.patch.object(mod,"EXPECTED_EXTRACTED_SIZES",sizes):
                with self.assertRaisesRegex(mod.ImageCheckError,"Unexpected iOS"):
                    mod.inspect(root,run_tools=False)


if __name__=="__main__":
    unittest.main(verbosity=2)
