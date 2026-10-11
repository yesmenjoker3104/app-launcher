from collections.abc import Sequence
from pathlib import Path
import subprocess


def open_with_application(
    file_paths: Sequence[Path],
    application_path: Path,
) -> None:
    for file_path in file_paths:
        if not file_path.exists():
            raise FileNotFoundError(
                f"対象が見つかりません: {file_path}"
            )

    if not application_path.is_file():
        raise FileNotFoundError(
            f"対象アプリケーションが見つかりません: {application_path}"
        )

    subprocess.Popen([
        str(application_path),
        *(str(file_path) for file_path in file_paths),
    ])


def launch_application(application_path: Path) -> None:
    if not application_path.is_file():
        raise FileNotFoundError(
            f"対象アプリケーションが見つかりません: {application_path}"
        )

    subprocess.Popen([
        str(application_path),
    ])