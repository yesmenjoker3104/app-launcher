from pathlib import Path

from .models import App, AppRegistry


def scan_directory(
    directory: Path,
    recursive: bool = True,
    excluded_directories: set[str] | None = None,
) -> list[App]:
    if not directory.is_dir():
        return []

    excluded_names = excluded_directories or set()
    paths = directory.rglob("*") if recursive else directory.iterdir()

    apps: list[App] = []

    for path in paths:
        if not path.is_file():
            continue
        if path.suffix.casefold() != ".exe":
            continue
        if is_excluded_path(path, directory, excluded_names):
            continue

        apps.append(App(
            name=path.stem,
            path=str(path),
            aliases=[path.stem.casefold()],
            source="scanned",
        ))

    return apps


def find_application(
    registry: AppRegistry,
    query: str,
) -> App | None:
    normalized_query = query.strip().casefold()

    for app in registry.apps:
        if not app.enabled:
            continue

        names = [app.name, *app.aliases]
        if any(
            name.strip().casefold() == normalized_query
            for name in names
        ):
            return app

    return None


def is_excluded_path(
    path: Path,
    root: Path,
    excluded_directories: set[str],
) -> bool:
    # スキャン元より上の親フォルダ名（例: Program Files）では除外しない
    relative_dirs = path.relative_to(root).parts[:-1]
    return any(
        part.casefold() in excluded_directories
        for part in relative_dirs
    )