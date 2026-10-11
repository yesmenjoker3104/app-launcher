import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from . import __version__

from .discovery import find_application, scan_directory
from .config import load_excluded_directories
from .errors import AppLauncherError
from .models import App, AppRegistry, SourceFolder
from .registry import (
    RegistryStore,
    absorb_nested_sources,
    find_covering_source,
    find_source,
    normalize_path,
    owner_of,
    scanned_apps_owned_by,
)
from .launcher import launch_application, open_with_application


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="App Launcher CLI",
        prog="app-launcher"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(
        dest="command",
        required=True
    )
    register_parser = subparsers.add_parser(
        "register",
        help="Register a new application"
    )
    register_parser.add_argument("path", type=Path, help="Path to the application to register")
    register_parser.add_argument("--name", type=str, help="Name of the application to register")

    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan a directory for applications and remember it as a source folder"
    )
    scan_parser.add_argument("directory", type=Path, help="Directory to scan for applications")
    scan_parser.add_argument("--recursive", action="store_true", help="Recursively scan subdirectories for applications")
    unscan_parser = subparsers.add_parser(
        "unscan",
        help="Forget a source folder and the applications detected in it"
    )
    unscan_parser.add_argument("directory", type=Path, help="Source folder to forget")
    subparsers.add_parser(
        "list",
        help="List all registered applications"
    )
    remove_parser = subparsers.add_parser(
        "remove",
        help="Remove a registered application"
    )
    remove_parser.add_argument("path", type=str, help="Name of the application to remove")

    update_parser = subparsers.add_parser(
        "update",
        help="Update the name, path, aliases or list visibility of a registered application",
    )
    update_parser.add_argument("name", type=str, help="Name or path of the application to update")
    update_parser.add_argument("--name", dest="new_name", type=str, help="New name")
    update_parser.add_argument("--path", type=Path, help="New path to the executable")
    update_parser.add_argument(
        "--aliases",
        type=str,
        help="Comma-separated aliases (replaces the existing aliases)",
    )
    visibility_group = update_parser.add_mutually_exclusive_group()
    visibility_group.add_argument(
        "--show-in-list",
        dest="show_in_list",
        action="store_true",
        default=None,
        help="Show the application in the ore-filer launcher list",
    )
    visibility_group.add_argument(
        "--hide-from-list",
        dest="show_in_list",
        action="store_false",
        default=None,
        help="Hide the application from the ore-filer launcher list (it can still be opened by alias)",
    )

    open_parser = subparsers.add_parser(
        "open",
        help="Open or launch a registered application",
    )
    open_parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Optional file or folder paths to open",
    )
    open_parser.add_argument(
        "--application",
        type=str,
        required=True,
        help="Registered application name or alias",
    )

    return parser


def output_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=True))


def load_registry(store: RegistryStore) -> AppRegistry:
    registry = store.load()
    if registry is None:
        return AppRegistry()
    return registry


def legacy_data_directory() -> Path:
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parents[2]
    return base_dir / "data"


def data_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base_dir = Path(local_app_data)
    else:
        base_dir = Path.home() / "AppData" / "Local"
    return base_dir / "app-launcher"


def migrate_legacy_data() -> None:
    old_dir = legacy_data_directory()
    new_dir = data_directory()

    if old_dir.resolve() == new_dir.resolve():
        return

    for filename in ("apps.json", "config.json"):
        old_file = old_dir / filename
        new_file = new_dir / filename
        if old_file.exists() and not new_file.exists():
            new_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(old_file), str(new_file))


def registry_path() -> Path:
    return data_directory() / "apps.json"


def config_path() -> Path:
    return data_directory() / "config.json"


def handle_register(
    args: argparse.Namespace,
    store: RegistryStore,
) -> int:
    registry = load_registry(store)
    app_path = args.path.resolve()
    app = App(
        path=str(app_path),
        name=args.name or app_path.stem,
        aliases=[app_path.stem.casefold()],
        source="manual",
    )
    added = store.add(registry, app)
    if not added:
        output_json({
            "ok": False,
            "error": "同じアプリがすでに登録されています。",
        })
        return 1
    store.save(registry)
    output_json({
        "ok": True,
        "action": "app_register",
        "app": {
            "name": app.name,
            "path": app.path,
        },
    })
    return 0


def handle_scan(
    args: argparse.Namespace,
    store: RegistryStore,
) -> int:
    registry = load_registry(store)
    directory = str(args.directory.resolve())
    recursive = args.recursive
    covered_by: str | None = None

    # 再帰登録元の配下なら、子フォルダは登録せず親を再スキャンする（重複登録を防ぐ）
    if find_source(registry, directory) is None:
        covering = find_covering_source(registry, directory)
        if covering is not None:
            covered_by = covering.path
            directory = covering.path
            recursive = True

    apps = scan_directory(
        Path(directory),
        recursive=recursive,
        excluded_directories=load_excluded_directories(config_path()),
    )

    source = find_source(registry, directory)
    if source is None:
        source = SourceFolder(path=directory, recursive=recursive)
        registry.sources.append(source)
    else:
        source.recursive = recursive

    # 子の登録元は親へ統合する。子のアプリは所有者が親になり、設定（エイリアス等）は保持される
    absorbed = absorb_nested_sources(registry)

    found_keys = {normalize_path(app.path) for app in apps}
    directory_key = normalize_path(directory)

    def _is_stale(app: App) -> bool:
        if app.source != "scanned":
            return False
        owner = owner_of(registry, app)
        if owner is None:
            return True
        return normalize_path(owner.path) == directory_key and normalize_path(app.path) not in found_keys

    stale = [app for app in registry.apps if _is_stale(app)]
    stale_ids = {id(app) for app in stale}
    registry.apps = [app for app in registry.apps if id(app) not in stale_ids]

    added_count = 0
    for app in apps:
        if store.add(registry, app):
            added_count += 1
    store.save(registry)
    output_json({
        "ok": True,
        "action": "app_scan",
        "directory": directory,
        "found": len(apps),
        "added": added_count,
        "removed": len(stale),
        "absorbed": [source.path for source in absorbed],
        "covered_by": covered_by,
    })

    return 0


def handle_unscan(
    args: argparse.Namespace,
    store: RegistryStore,
) -> int:
    registry = load_registry(store)
    directory = str(args.directory.resolve())
    source = find_source(registry, directory)
    if source is None:
        output_json({
            "ok": False,
            "error": "指定されたフォルダは登録されていません。",
        })
        return 1

    detected = scanned_apps_owned_by(registry, directory)
    detected_ids = {id(app) for app in detected}
    registry.apps = [app for app in registry.apps if id(app) not in detected_ids]
    registry.sources.remove(source)
    store.save(registry)
    output_json({
        "ok": True,
        "action": "app_unscan",
        "directory": directory,
        "removed": len(detected),
    })
    return 0


def handle_list(
    store: RegistryStore,
) -> int:
    registry = load_registry(store)

    apps = []
    for app in registry.apps:
        owner = owner_of(registry, app) if app.source == "scanned" else None
        apps.append({
            "name": app.name,
            "path": app.path,
            "aliases": app.aliases,
            "enabled": app.enabled,
            "source": app.source,
            "show_in_list": app.show_in_list,
            "source_path": owner.path if owner is not None else None,
        })
    sources = [
        {
            "path": source.path,
            "recursive": source.recursive,
        }
        for source in registry.sources
    ]
    output_json({
        "ok": True,
        "action": "app_list",
        "apps": apps,
        "sources": sources,
    })
    return 0

def handle_remove(
    args: argparse.Namespace,
    store: RegistryStore,
) -> int:
    registry = load_registry(store)
    removed = store.remove(registry, args.path)

    if not removed:
        output_json({
            "ok": False,
            "error": "指定されたアプリは登録されていません。",
        })
        return 1
    store.save(registry)
    output_json({
        "ok": True,
        "action": "app_remove",
        "app": {
            "path": args.path,
        },
    })
    return 0

def handle_update(
    args: argparse.Namespace,
    store: RegistryStore,
) -> int:
    if (
        args.new_name is None
        and args.path is None
        and args.aliases is None
        and args.show_in_list is None
    ):
        output_json({
            "ok": False,
            "error": "変更する名前・パス・エイリアス・一覧表示のいずれかを指定してください。",
        })
        return 1

    registry = load_registry(store)
    matches = store.find_targets(registry, args.name)
    if not matches:
        output_json({
            "ok": False,
            "error": "指定されたアプリは登録されていません。",
        })
        return 1
    if len(matches) > 1:
        output_json({
            "ok": False,
            "error": "同じ名前のアプリが複数登録されています。パスを指定してください。",
        })
        return 1

    app = matches[0]
    if args.path is not None:
        new_path = args.path.resolve()
        if not new_path.is_file():
            output_json({
                "ok": False,
                "error": f"実行ファイルが見つかりません: {new_path}",
            })
            return 1
        other = store.find_by_path(registry, str(new_path))
        if other is not None and other is not app:
            output_json({
                "ok": False,
                "error": "同じパスのアプリがすでに登録されています。",
            })
            return 1
        app.path = str(new_path)

    if args.new_name is not None:
        if not args.new_name.strip():
            output_json({
                "ok": False,
                "error": "アプリ名を空にすることはできません。",
            })
            return 1
        app.name = args.new_name.strip()

    if args.aliases is not None:
        aliases = [alias.strip() for alias in args.aliases.split(",") if alias.strip()]
        taken = {
            name.casefold()
            for other in registry.apps
            if other is not app
            for name in [other.name, *other.aliases]
        }
        conflicts = [alias for alias in aliases if alias.casefold() in taken]
        if conflicts:
            output_json({
                "ok": False,
                "error": f"他のアプリの名前またはエイリアスと重複しています: {', '.join(conflicts)}",
            })
            return 1
        app.aliases = list(dict.fromkeys(aliases))

    if args.show_in_list is not None:
        app.show_in_list = args.show_in_list

    store.save(registry)
    output_json({
        "ok": True,
        "action": "app_update",
        "app": {
            "name": app.name,
            "path": app.path,
            "aliases": app.aliases,
            "show_in_list": app.show_in_list,
        },
    })
    return 0


def handle_open(
    args: argparse.Namespace,
    store: RegistryStore,
) -> int:
    try:
        registry = load_registry(store)
        app = find_application(registry, args.application)

        if app is None:
            output_json({
                "ok": False,
                "error": (
                    f"登録されているアプリが見つかりません: "
                    f"{args.application}"
                ),
            })
            return 1

        application_path = Path(app.path)

        result = {
            "ok": True,
            "application": app.name,
        }

        if not args.files:
            launch_application(application_path)
            result["action"] = "app_launch"
        else:
            open_with_application(
                file_paths=args.files,
                application_path=application_path,
            )
            result["action"] = "app_open"
            result["files"] = [str(path) for path in args.files]

        output_json(result)
        return 0

    except FileNotFoundError as error:
        output_json({
            "ok": False,
            "error": str(error),
        })
        return 1

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        migrate_legacy_data()
        store = RegistryStore(registry_path())

        if args.command == "register":
            return handle_register(args, store)
        if args.command == "scan":
            return handle_scan(args, store)
        if args.command == "unscan":
            return handle_unscan(args, store)
        if args.command == "list":
            return handle_list(store)
        if args.command == "remove":
            return handle_remove(args, store)
        if args.command == "update":
            return handle_update(args, store)
        if args.command == "open":
            return handle_open(args, store)

        parser.print_help()
        return 1
    except AppLauncherError as e:
        output_json({
            "ok": False,
            "error": str(e),
        })
        return 1
    except Exception as e:
        print(
            f"unexpected error: {str(e)}",
            file=sys.stderr,
        )
        output_json({
            "ok": False,
            "error": "予期しないエラーが発生しました。",
        })
        return 1

if __name__ == "__main__":
    sys.exit(main())