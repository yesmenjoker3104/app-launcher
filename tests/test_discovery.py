from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app_launcher.discovery import scan_directory


class ScanDirectoryExclusionTests(unittest.TestCase):
    def test_parent_folder_names_do_not_exclude_scan_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Program Files" / "Microsoft Office" / "root"
            (root / "Office16").mkdir(parents=True)
            (root / "Office16" / "EXCEL.EXE").write_bytes(b"")
            (root / "Office16" / "WINWORD.EXE").write_bytes(b"")

            apps = scan_directory(
                root / "Office16",
                recursive=False,
                excluded_directories={"program files", "windows"},
            )

        self.assertEqual(sorted(app.name for app in apps), ["EXCEL", "WINWORD"])

    def test_excluded_subfolder_is_still_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tools"
            (root / "node_modules").mkdir(parents=True)
            (root / "node_modules" / "helper.exe").write_bytes(b"")
            (root / "app.exe").write_bytes(b"")

            apps = scan_directory(
                root,
                recursive=True,
                excluded_directories={"node_modules"},
            )

        self.assertEqual([app.name for app in apps], ["app"])


if __name__ == "__main__":
    unittest.main()
