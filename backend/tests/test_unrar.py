import os
import tempfile
import unittest
from pathlib import Path

try:
    from unrar import rarfile
    HAS_UNRAR = True
except ImportError:
    HAS_UNRAR = False
    rarfile = None

SAMPLE_RAR = Path(__file__).parent.parent / "test_data" / "sample.rar"


@unittest.skipIf(not HAS_UNRAR, "unrar native C extension not built on this environment")
class TestUnrar(unittest.TestCase):
    def test_rarfile_imports(self):
        self.assertTrue(hasattr(rarfile, "RarFile"))
        self.assertTrue(hasattr(rarfile, "BadRarFile"))
        self.assertTrue(hasattr(rarfile, "RarWrongPassword"))

    @unittest.skipIf(not SAMPLE_RAR.exists(), "sample.rar not available")
    def test_rarfile_list(self):
        rf = rarfile.RarFile(SAMPLE_RAR)
        names = rf.namelist()
        self.assertGreater(len(names), 0)
        infos = rf.infolist()
        self.assertEqual(len(infos), len(names))
        for info in infos:
            self.assertIsInstance(info.filename, str)
            self.assertGreaterEqual(info.file_size, 0)

    @unittest.skipIf(not SAMPLE_RAR.exists(), "sample.rar not available")
    def test_rarfile_extractall(self):
        rf = rarfile.RarFile(SAMPLE_RAR)
        with tempfile.TemporaryDirectory() as tmpdir:
            rf.extractall(tmpdir)
            for info in rf.infolist():
                if not info.isdir():
                    extracted = Path(tmpdir) / info.filename
                    self.assertTrue(extracted.exists())
                    self.assertEqual(extracted.stat().st_size, info.file_size)

    def test_rarfile_bad_archive(self):
        with tempfile.NamedTemporaryFile(suffix=".rar", delete=False) as f:
            f.write(b"not a rar file")
            bad_path = f.name
        try:
            with self.assertRaises(rarfile.BadRarFile):
                rarfile.RarFile(bad_path).infolist()
        finally:
            os.unlink(bad_path)


if __name__ == "__main__":
    unittest.main()
