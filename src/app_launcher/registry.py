import json
from pathlib import Path

from .models import App, AppRegistry, SourceFolder


def normalize_path(path: str) -> str:
    return str(Path(path).resolve()).casefold()


def find_source(registry: AppRegistry, path: str) -> SourceFolder | None:
    normalized = normalize_path(path)
    for source in registry.sources:
        if normalize_path(source.path) == normalized:
            return source
    return None


def _is_strictly_under(path: str, ancestor: str) -> bool:
    child = Path(normalize_path(path))
    parent = Path(normalize_path(ancestor))
    return child != parent and parent in child.parents


def find_covering_source(registry: AppRegistry, path: str) -> SourceFolder | None:
    """path を再帰的に含む登録元（path 自身は除く）を返す。"""
    for source in registry.sources:
        if source.recursive and _is_strictly_under(path, source.path):
            return source
    return None


def absorb_nested_sources(registry: AppRegistry) -> list[SourceFolder]:
    """
    再帰登録元の配下にある他の登録元を削除し、削除したものを返す。
    子の検知アプリは削除しない（親の登録元が所有するようになる）。
    """
    absorbed = [
        source
        for source in registry.sources
        if find_covering_source(registry, source.path) is not None
    ]
    if absorbed:
        absorbed_ids = {id(source) for source in absorbed}
        registry.sources = [s for s in registry.sources if id(s) not in absorbed_ids]
    return absorbed


def owner_of(registry: AppRegistry, app: App) -> SourceFolder | None:
    """
    アプリを検知したフォルダ（登録元）を返す。
    複数該当する場合は最も深い（最も具体的な）登録元を選ぶ。
    """
    app_path = Path(normalize_path(app.path))
    owner: SourceFolder | None = None
    owner_depth = -1
    for source in registry.sources:
        source_path = Path(normalize_path(source.path))
        if source.recursive:
            inside = source_path in app_path.parents
        else:
            inside = source_path == app_path.parent
        if inside and len(source_path.parts) > owner_depth:
            owner = source
            owner_depth = len(source_path.parts)
    return owner


def scanned_apps_owned_by(registry: AppRegistry, folder: str) -> list[App]:
    """指定フォルダ（登録元）が検知したアプリ。"""
    key = normalize_path(folder)
    result: list[App] = []
    for app in registry.apps:
        if app.source != "scanned":
            continue
        owner = owner_of(registry, app)
        if owner is not None and normalize_path(owner.path) == key:
            result.append(app)
    return result


class RegistryStore:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def load(self) -> AppRegistry | None:
        if not self.file_path.exists():
            return None
        with self.file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return AppRegistry.from_dict(data)

    def save(self, registry: AppRegistry) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with self.file_path.open("w", encoding="utf-8") as f:
            json.dump(registry.to_dict(), f, ensure_ascii=False, indent=2)

    def add(self, registry: AppRegistry, app: App) -> bool:
        normalized_path = self._normalize_path(app.path)
        for registered_app in registry.apps:
            if self._normalize_path(registered_app.path) == normalized_path:
                return False
        registry.apps.append(app)
        return True

    def remove(self, registry: AppRegistry, path: str) -> bool:
        normalized_path = self._normalize_path(path)
        for index, app in enumerate(registry.apps):
            if self._normalize_path(app.path) == normalized_path:
                del registry.apps[index]
                return True
        return False

    def find_by_path(self, registry: AppRegistry, path: str) -> App | None:
        normalized_path = self._normalize_path(path)
        for app in registry.apps:
            if self._normalize_path(app.path) == normalized_path:
                return app
        return None

    def find_targets(self, registry: AppRegistry, target: str) -> list[App]:
        """パス（完全一致）を優先し、なければ名前（大文字小文字無視）で探す。"""
        by_path = self.find_by_path(registry, target)
        if by_path is not None:
            return [by_path]
        key = target.strip().casefold()
        return [app for app in registry.apps if app.name.strip().casefold() == key]

    @staticmethod
    def _normalize_path(path: str) -> str:
        return normalize_path(path)
