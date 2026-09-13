import argparse
import json
import sys
from pathlib import Path

from .discovery import scan_directory
from .errors import AppLauncherError
from .models import App, AppRegistry
from .registry import RegistryStore


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
    remove_parser = subparsers.add_parser(
        "remove",
        help="Remove a registered application"
    )
    remove_parser.add_argument("path", type=str, help="Name of the application to remove")

    return parser


def output_json(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False))


def load_registry(store: RegistryStore) -> AppRegistry:
    registry = store.load()
    if registry is None:
        return AppRegistry()
    return registry


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
    apps = scan_directory(
        args.directory,
        recursive=args.recursive,
        )
    added_count = 0
    for app in apps:
        if store.add(registry, app):
            added_count += 1
    store.save(registry)
    output_json({
        "ok": True,
        "action": "app_scan",
        "found": len(apps),
        "added": added_count,
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
        }
        for app in registry.apps
    ]
    output_json({
        "ok": True,
        "action": "app_list",
        "apps": apps,
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

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    store = RegistryStore("data/apps.json")

    try:
        if args.command == "register":
            return handle_register(args, store)
        if args.command == "scan":
            return handle_scan(args, store)
        if args.command == "list":
            return handle_list(store)
        if args.command == "remove":
            return handle_remove(args, store)

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