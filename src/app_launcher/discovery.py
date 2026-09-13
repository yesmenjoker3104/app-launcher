from pathlib import Path
from .models import App

def scan_directory(directory: Path,
                   recursive: bool = True,
                   excluded_directories: set[str] | None =None,) -> list[App]:
    if not directory.is_dir():
        return []

    excluded_names = excluded_directories or set()

    paths =(
        directory.rglob("*")
        if recursive
        else directory.iterdir()
    )

    apps: list[App] = []

    for path in paths:
        if not path.is_file():
            continue
        if path.suffix.casefold() != ".exe":
            continue
        if is_excluded_path(path, excluded_names):
            continue
        apps.append(App(
            name=path.stem,
            path=str(path),
            aliases = [path.stem.casefold()],
            source="scanned"
        ))

    return apps

def is_excluded_path(path: Path, excluded_directories: set[str]) -> bool:
    return any(part.casefold() in excluded_directories for part in path.parts)