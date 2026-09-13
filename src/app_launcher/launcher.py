from pathlib import Path
import subprocess


def open_with_application(
    file_path: Path,
    application_path: Path,
) -> None:
    if not file_path.is_file():
        raise FileNotFoundError(
            f"対象ファイルが見つかりません: {file_path}"
        )

    if not application_path.is_file():
        raise FileNotFoundError(
            f"対象アプリケーションが見つかりません: {application_path}"
        )

    subprocess.Popen([
        str(application_path),
        str(file_path),
    ])


def launch_application(application_path: Path) -> None:
    if not application_path.is_file():
        raise FileNotFoundError(
            f"対象アプリケーションが見つかりません: {application_path}"
        )

    subprocess.Popen([
        str(application_path),
    ])