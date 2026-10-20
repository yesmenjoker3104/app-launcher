import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .discovery import find_application, scan_directory
from .config import load_excluded_directories
from .errors import AppLauncherError
from .models import App, AppRegistry
from .registry import RegistryStore
from .launcher import launch_application, open_with_application


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="App Launcher CLI",
        prog="app-launcher"
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
        help="Scan a directory for applications"
    )
    scan_parser.add_argument("directory", type=Path, help="Directory to scan for applications")
    scan_parser.add_argument("--recursive", action="store_true", help="Recursively scan subdirectories for applications")
    subparsers.add_parser(
        "list",
        help="List all registered applications"
    )
    unscan_parser = subparsers.add_parser(
        "unscan",
        help="Remove a scanned folder and the applications detected from it"
    )
    unscan_parser.add_argument("directory", type=Path, help="Scanned folder to remove")

    update_parser = subparsers.add_parser(
        "update",
        help="Update a registered application (matched by path)"
    )
    update_parser.add_argument("target", type=str, help="Path of the application to update")
    update_parser.add_argument("--name", type=str, help="New display name")
    update_parser.add_argument("--path", type=Path, help="New executable path")
    update_parser.add_argument("--aliases", type=str, help="Comma-separated aliases (empty to clear)")
    visibility = update_parser.add_mutually_exclusive_group()
    visibility.add_argument(
        "--show-in-list",
        dest="show_in_list",
        action="store_true",
        default=None,
        help="Show the application in the launcher list",
    )
    visibility.add_argument(
        "--hide-from-list",
        dest="show_in_list",
        action="store_false",
        default=None,
        help="Hide the application from the launcher list",
    )
    remove_parser = subparsers.add_parser(
        "remove",
        help="Remove a registered application"
    )
    remove_parser.add_argument("path", type=str, help="Name of the application to remove")

    open_parser = subparsers.add_parser(
        "open",
        help="Open or launch a registered application",
    )
    open_parser.add_argument(
        "file",
        nargs="*",
        type=Path,
        help="Optional file paths to open",
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


def data_directory() -> Path:
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parents[2]
    return base_dir / "data"


def app_data_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "app-launcher"


def registry_path() -> Path:
    return app_data_directory() / "apps.json"


def legacy_registry_path() -> Path:
    return data_directory() / "apps.json"


def migrate_legacy_registry() -> None:
    """旧バージョンの exe 横の data/apps.json を、初回だけ新しい保存先へコピーする。"""
    target = registry_path()
    legacy = legacy_registry_path()
    if target.exists() or not legacy.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(legacy, target)


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
    directory = args.directory.resolve()
    recursive = args.recursive
    covered_by = None

    # 再帰スキャン済みの親フォルダに含まれる場合は、親フォルダとして扱う
    covering = store.find_covering_source(registry, directory)
    if covering is not None:
        covered_by = covering.path
        directory = Path(covering.path)
        recursive = covering.recursive

    apps = scan_directory(
        directory,
        recursive=recursive,
        excluded_directories=load_excluded_directories(config_path()),
    )
    for app in apps:
        app.source_path = str(directory)
    result = store.apply_scan(registry, directory, recursive, apps)
    store.save(registry)
    output_json({
        "ok": True,
        "action": "app_scan",
        "found": len(apps),
        "added": result["added"],
        "covered_by": covered_by,
        "absorbed": result["absorbed"],
    })

    return 0


def handle_list(
    store: RegistryStore,
) -> int:
    registry = load_registry(store)

    apps = [
        {
            "name": app.name,
            "path": app.path,
            "aliases": app.aliases,
            "enabled": app.enabled,
            "source": app.source,
            "source_path": app.source_path,
            "show_in_list": app.show_in_list,
        }
        for app in registry.apps
    ]
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

def handle_unscan(
    args: argparse.Namespace,
    store: RegistryStore,
) -> int:
    registry = load_registry(store)
    directory = args.directory.resolve()
    if not store.remove_source(registry, directory):
        output_json({
            "ok": False,
            "error": "指定されたフォルダは登録されていません。",
        })
        return 1
    store.save(registry)
    output_json({
        "ok": True,
        "action": "app_unscan",
        "source": {
            "path": str(directory),
        },
    })
    return 0


def handle_update(
    args: argparse.Namespace,
    store: RegistryStore,
) -> int:
    registry = load_registry(store)
    app = store.find(registry, args.target)
    if app is None:
        output_json({
            "ok": False,
            "error": "指定されたアプリは登録されていません。",
        })
        return 1

    if args.path is not None:
        new_path = str(args.path.resolve())
        other = store.find(registry, new_path)
        if other is not None and other is not app:
            output_json({
                "ok": False,
                "error": "同じパスのアプリがすでに登録されています。",
            })
            return 1
        app.path = new_path
    if args.name is not None:
        app.name = args.name
    if args.aliases is not None:
        app.aliases = [alias.strip() for alias in args.aliases.split(",") if alias.strip()]
    if args.show_in_list is not None:
        app.show_in_list = args.show_in_list

    store.save(registry)
    output_json({
        "ok": True,
        "action": "app_update",
        "app": {
            "name": app.name,
            "path": app.path,
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

        files = args.file or []
        if not files:
            launch_application(application_path)
            result["action"] = "app_launch"
        else:
            for file_path in files:
                open_with_application(
                    file_path=file_path,
                    application_path=application_path,
                )
            result["action"] = "app_open"
            result["files"] = [str(file_path) for file_path in files]
            if len(files) == 1:
                result["file"] = result["files"][0]

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
        migrate_legacy_registry()
        store = RegistryStore(registry_path())
        if args.command == "register":
            return handle_register(args, store)
        if args.command == "scan":
            return handle_scan(args, store)
        if args.command == "list":
            return handle_list(store)
        if args.command == "remove":
            return handle_remove(args, store)
        if args.command == "unscan":
            return handle_unscan(args, store)
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