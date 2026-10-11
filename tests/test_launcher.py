from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app_launcher.launcher import open_with_application


class OpenWithApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp(prefix="app_launcher_open_"))
        self.app = self._tmp / "app.exe"
        self.app.write_bytes(b"")
        self.folder = self._tmp / "folder"
        self.folder.mkdir()

    def tearDown(self) -> None:
        for path in sorted(self._tmp.rglob("*"), reverse=True):
            path.rmdir() if path.is_dir() else path.unlink()
        self._tmp.rmdir()

    def test_passes_directory_as_argument(self) -> None:
        with patch("app_launcher.launcher.subprocess.Popen") as popen:
            open_with_application(file_paths=[self.folder], application_path=self.app)
        popen.assert_called_once_with([str(self.app), str(self.folder)])

    def test_passes_file_as_argument(self) -> None:
        target = self._tmp / "note.txt"
        target.write_text("x", encoding="utf-8")
        with patch("app_launcher.launcher.subprocess.Popen") as popen:
            open_with_application(file_paths=[target], application_path=self.app)
        popen.assert_called_once_with([str(self.app), str(target)])

    def test_passes_all_files_in_one_launch(self) -> None:
        first = self._tmp / "a.txt"
        second = self._tmp / "b.txt"
        first.write_text("x", encoding="utf-8")
        second.write_text("y", encoding="utf-8")
        with patch("app_launcher.launcher.subprocess.Popen") as popen:
            open_with_application(file_paths=[first, second], application_path=self.app)
        popen.assert_called_once_with([str(self.app), str(first), str(second)])

    def test_missing_target_is_rejected_without_launching(self) -> None:
        missing = self._tmp / "missing"
        with patch("app_launcher.launcher.subprocess.Popen") as popen:
            with self.assertRaises(FileNotFoundError):
                open_with_application(file_paths=[missing], application_path=self.app)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
