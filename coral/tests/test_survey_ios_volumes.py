#!/usr/bin/env python3
"""Small local-fs synthetic survey tests; no hdiutil or Apple files."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("survey_ios_volumes",root/"survey_ios_volumes.py")
# The app module imports the neighbouring inspector by its basename.
import sys
sys.path.insert(0,str(root))
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class SurveyTests(unittest.TestCase):
    def test_cache_subfiles_counted(self):
        with tempfile.TemporaryDirectory() as d:
            mount=Path(d)
            cache=mount/"System/Library/Caches/com.apple.dyld"
            cache.mkdir(parents=True)
            (cache/"dyld_shared_cache_arm64").write_bytes(b"dyld_v1" + b"\0"*20)
            (cache/"dyld_shared_cache_arm64.01").write_bytes(b"dyld_v1" + b"X"*90)
            result=app.survey(mount,"systemos")
            self.assertEqual(result["cache_file_count"],2)
            self.assertEqual(result["cache_total_apparent_bytes"],len(b"dyld_v1"+b"\0"*20)+len(b"dyld_v1"+b"X"*90))
            self.assertEqual(result["selected_paths"]["System/Library/Caches/com.apple.dyld"]["type"],"directory")

    def test_symlinks_not_followed_and_hardlinks_counted_once(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as elsewhere:
            base=Path(d)
            (base/"file").write_bytes(b"hello")
            os.link(base/"file",base/"file2")
            (base/"loop").symlink_to(base)
            (base/"escape").symlink_to(elsewhere)
            result=app.survey(base,"os")
            self.assertEqual(result["regular_files"],2)
            self.assertEqual(result["hardlink_duplicates"],1)
            self.assertEqual(result["symlinks"],2)
            self.assertEqual(result["apparent_bytes_unique_inodes"],5)

    def test_entry_cap_blocks_unbounded_scan(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            (base/"a").write_bytes(b"a")
            (base/"b").write_bytes(b"b")
            with mock.patch.object(app,"LIMIT",1):
                with self.assertRaises(ValueError):
                    app.survey(base,"os")


if __name__=="__main__":
    unittest.main(verbosity=2)
