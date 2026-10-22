#!/usr/bin/env python3
"""No real DMGs/sudo/hdiutil: mocked Phase 12 HFS+ candidate safety tests."""
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

module_path=Path(__file__).resolve().parents[1] / "build_ios_hfs_candidate.py"
spec=importlib.util.spec_from_file_location("build_ios_hfs_candidate", module_path)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def setup_sources(directory):
    roles={"os":"os.dmg","systemos":"systemos.dmg","appos":"appos.dmg"}
    entries=[]
    sizes={}
    for role,name in roles.items():
        path=directory/name
        path.write_bytes(role.encode())
        sizes[role]=path.stat().st_size
        entries.append({"role":role,"name":name,"bytes":sizes[role],
                        "sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    (directory/"local-image-report.json").write_text(json.dumps({
        "version":"16.7.16","build":"20H392","device":"iPhone10,3",
        "board":"d22ap","files":entries
    }))
    return sizes


class CandidateTests(unittest.TestCase):
    def test_plan_never_creates_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            src=root/"images"
            src.mkdir()
            sizes=setup_sources(src)
            out=root/"candidate.sparseimage"
            with mock.patch.object(m,"SOURCE_BYTES",sizes):
                plan=m.plan(src,out)
            self.assertFalse(out.exists())
            self.assertEqual(plan["sparse_volume_max_gib"],24)
            self.assertIn("NO FILESYSTEM CHANGES",plan["status"])

    def test_wrong_build_fails_before_any_change(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            src=base/"images"
            src.mkdir()
            sizes=setup_sources(src)
            manifest=src/"local-image-report.json"
            j=json.loads(manifest.read_text())
            j["build"]="invalid"
            manifest.write_text(json.dumps(j))
            with mock.patch.object(m,"SOURCE_BYTES",sizes), self.assertRaises(m.BuildError):
                m.plan(src,base/"candidate.sparseimage")
            self.assertFalse((base/"candidate.sparseimage").exists())

    def test_never_overwrites_sparseimage(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            src=base/"images";src.mkdir()
            sizes=setup_sources(src)
            out=base/"candidate.sparseimage"
            out.write_text("DO NOT TOUCH")
            with mock.patch.object(m,"SOURCE_BYTES",sizes), self.assertRaisesRegex(m.BuildError,"overwrite"):
                m.plan(src,out)
            self.assertEqual(out.read_text(),"DO NOT TOUCH")

    def test_rejects_source_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);src=base/"images";src.mkdir()
            sizes=setup_sources(src)
            (src/"os.dmg").unlink()
            (src/"os.dmg").symlink_to(src/"systemos.dmg")
            with mock.patch.object(m,"SOURCE_BYTES",sizes), self.assertRaisesRegex(m.BuildError,"Missing/invalid"):
                m.verify_inputs(src)

    def test_parse_hdiutil_base_and_mount(self):
        plist=plistlib.dumps({"system-entities":[
            {"dev-entry":"/dev/disk20"},
            {"dev-entry":"/dev/disk20s1", "mount-point":"/Volumes/Test"}
        ]})
        self.assertEqual(m.base_device(plist),
                         ("/dev/disk20",Path("/Volumes/Test")))

    def test_requires_new_not_git_repo_output(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);src=base/"images";src.mkdir()
            sizes=setup_sources(src)
            with mock.patch.object(m,"SOURCE_BYTES",sizes):
                with self.assertRaises(m.BuildError):
                    m.plan(src,src/"candidate.sparseimage")
        with self.assertRaisesRegex(m.BuildError,"sparseimage"):
            m.validate_output(Path("/tmp/out.img"))

    def test_rejects_tiny_or_absurd_volume(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);src=base/"images";src.mkdir()
            sizes=setup_sources(src)
            with mock.patch.object(m,"SOURCE_BYTES",sizes):
                for bad_size in (8, 12, 129):
                    with self.assertRaises(m.BuildError):
                        m.plan(src,base/"candidate.sparseimage",bad_size)

    def test_attach_cleanup_uses_only_returned_device(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            work=base/"test"
            def run(args,**kwargs):
                if args[1]=="attach":
                    output=plistlib.dumps({"system-entities":[
                        {"dev-entry":"/dev/disk911"},
                        {"dev-entry":"/dev/disk911s1","mount-point":str(work)}
                    ]})
                    return subprocess.CompletedProcess(args,0,output,b"")
                if args[1]=="detach":
                    self.assertEqual(args,["hdiutil","detach","/dev/disk911"])
                    return subprocess.CompletedProcess(args,0,b"",b"")
                raise AssertionError(args)
            with mock.patch.object(m.subprocess,"run",side_effect=run):
                with m.mounted(base/"source.dmg",work,readonly=True) as mount:
                    self.assertEqual(mount,work)


if __name__=="__main__":
    unittest.main(verbosity=2)
