from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import PkgExtractor
from mkpfs.game_metadata import read_game_metadata


def create_dummy_pkg(file_path: Path, title_id: str = "PPSA18463", title_name: str = "Baldur's Gate 3",
                     is_ps5: bool = True) -> Path:
    """Create a minimal valid-header PKG file with outer CNT metadata for testing."""
    # Build param.json or param.sfo payload
    if is_ps5:
        param_payload = json.dumps({
            "titleId": title_id,
            "titleName": title_name,
            "contentId": f"HP0000-{title_id}_00-0000000000000000",
            "contentVersion": "01.800.700"
        }).encode("utf-8")
        entry_id = 0x2000  # CntEntryId.ParamJson
    else:
        # Minimal SFO payload
        param_payload = b"\x00PSF\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        entry_id = 0x1000

    icon_payload = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"

    entry_table_offset = 0x100
    param_offset = 0x200
    icon_offset = param_offset + len(param_payload)

    content_id_bytes = f"HP0000-{title_id}_00-0000000000000000".encode("ascii").ljust(48, b"\x00")

    header = bytearray(0x400)
    # Magic \x7fCNT
    header[0:4] = b"\x7fCNT"
    # flags
    struct.pack_into(">I", header, 0x04, 0x00000001)
    # entry count: 2
    struct.pack_into(">I", header, 0x10, 2)
    # entry table offset
    struct.pack_into(">I", header, 0x18, entry_table_offset)
    # content_id at 0x40
    header[0x40:0x40 + len(content_id_bytes)] = content_id_bytes

    # Entry 0: param (0x2000 or 0x1000)
    e0_base = entry_table_offset
    struct.pack_into(">I", header, e0_base, entry_id)
    struct.pack_into(">I", header, e0_base + 0x10, param_offset)
    struct.pack_into(">I", header, e0_base + 0x14, len(param_payload))

    # Entry 1: icon0.png (0x1200)
    e1_base = entry_table_offset + 0x20
    struct.pack_into(">I", header, e1_base, 0x1200)
    struct.pack_into(">I", header, e1_base + 0x10, icon_offset)
    struct.pack_into(">I", header, e1_base + 0x14, len(icon_payload))

    # Write full file
    with open(file_path, "wb") as f:
        f.write(header[:param_offset])
        f.write(param_payload)
        f.write(icon_payload)

    return file_path


class TestPkgExtraction(unittest.TestCase):
    def test_locate_tool_priorities(self):
        # PS5 should find ProsperoPkgTool first
        ps5_tool = PkgExtractor.locate_tool(is_ps5=True)
        self.assertIsNotNone(ps5_tool)
        tool_path, tool_type = ps5_tool
        self.assertIn("prospero", tool_type.lower())

        # PS4 should prioritize shadpkg
        ps4_tool = PkgExtractor.locate_tool(is_ps5=False)
        self.assertIsNotNone(ps4_tool)
        tool_path, tool_type = ps4_tool
        self.assertEqual(tool_type, "shadpkg")

    def test_read_pkg_metadata_ps5(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_file = Path(tmpdir) / "test_ps5.pkg"
            create_dummy_pkg(pkg_file, title_id="PPSA18463", title_name="Baldur's Gate 3", is_ps5=True)

            meta = read_game_metadata(pkg_file)
            self.assertEqual(meta.title_id, "PPSA18463")
            self.assertEqual(meta.game_title, "Baldur's Gate 3")
            self.assertIn("PS5", meta.package_type)
            self.assertIsNotNone(meta.icon_bytes)

    def test_extract_pkg_metadata_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_file = Path(tmpdir) / "test_ps5.pkg"
            create_dummy_pkg(pkg_file, title_id="PPSA18463", title_name="Baldur's Gate 3", is_ps5=True)

            sce_sys_dir = Path(tmpdir) / "extracted" / "sce_sys"
            PkgExtractor.extract_pkg_metadata_files(pkg_file, sce_sys_dir)

            param_json = sce_sys_dir / "param.json"
            self.assertTrue(param_json.is_file(), "param.json was not extracted to sce_sys")

            data = json.loads(param_json.read_text(encoding="utf-8"))
            self.assertEqual(data["titleId"], "PPSA18463")
            self.assertEqual(data["titleName"], "Baldur's Gate 3")

            icon_file = sce_sys_dir / "icon0.png"
            self.assertTrue(icon_file.is_file(), "icon0.png was not extracted to sce_sys")
            self.assertTrue(icon_file.read_bytes().startswith(b"\x89PNG"))

    @patch("subprocess.Popen")
    def test_pkg_extractor_command_construction(self, mock_popen):
        # Configure mock process
        mock_proc = MagicMock()
        mock_proc.stdout = ["10% extracted", "50% extracted", "100% extracted"]
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmpdir:
            pkg_file = Path(tmpdir) / "test.pkg"
            create_dummy_pkg(pkg_file, title_id="PPSA18463", is_ps5=True)
            dest_root = Path(tmpdir) / "out"

            out_game = PkgExtractor.extract(pkg_file, dest_root)
            self.assertTrue(out_game.exists())
            self.assertTrue(mock_popen.called)
            cmd = mock_popen.call_args[0][0]

            # Verify ProsperoPkgTool was called with img_extract and passcode 0000...
            self.assertIn("img_extract", cmd)
            self.assertIn("--passcode", cmd)
            self.assertIn("00000000000000000000000000000000", cmd)

    def test_live_prospero_pkg_end_to_end(self):
        """End-to-end test creating and extracting a real PS5 FPKG via ProsperoPkgTool."""
        tool_info = PkgExtractor.locate_tool(is_ps5=True)
        if not tool_info or "prospero" not in tool_info[1].lower():
            self.skipTest("ProsperoPkgTool binary not available for live extraction test.")

        tool_path, _ = tool_info
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            src_dir = tmp_path / "game_src"
            (src_dir / "sce_sys").mkdir(parents=True, exist_ok=True)
            (src_dir / "eboot.bin").write_bytes(b"\x7fELF" + b"\x00" * 60)
            (src_dir / "sce_sys" / "param.json").write_text(
                json.dumps({
                    "titleId": "PPSA18463",
                    "titleName": "Baldur's Gate 3",
                    "contentId": "HP0000-PPSA18463_00-0000000000000000"
                }),
                encoding="utf-8"
            )

            pkg_path = tmp_path / "test_ps5.pkg"
            import subprocess
            res = subprocess.run(
                [tool_path, "img_create", str(src_dir), "--out", str(pkg_path),
                 "--passcode", "00000000000000000000000000000000", "--no_fself"],
                capture_output=True, text=True
            )
            self.assertEqual(res.returncode, 0, f"img_create failed: {res.stderr or res.stdout}")
            self.assertTrue(pkg_path.is_file())

            # 1. Test metadata parsing from real PS5 FIH package
            meta = read_game_metadata(pkg_path)
            self.assertEqual(meta.title_id, "PPSA18463")
            self.assertEqual(meta.game_title, "Baldur's Gate 3")
            self.assertEqual(meta.package_type, "PS5 PKG")

            # 2. Test full extraction via PkgExtractor
            dest_root = tmp_path / "out"
            extracted_game = PkgExtractor.extract(pkg_path, dest_root)
            self.assertTrue(extracted_game.is_dir())
            self.assertTrue((extracted_game / "eboot.bin").is_file())
            self.assertTrue((extracted_game / "sce_sys" / "param.json").is_file())

            # Verify param.json matches
            extracted_json = json.loads((extracted_game / "sce_sys" / "param.json").read_text(encoding="utf-8"))
            self.assertEqual(extracted_json["titleId"], "PPSA18463")
            self.assertEqual(extracted_json["titleName"], "Baldur's Gate 3")


if __name__ == "__main__":
    unittest.main()
