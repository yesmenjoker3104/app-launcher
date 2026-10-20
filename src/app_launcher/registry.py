import json
import os
from pathlib import Path

from .errors import AppLauncherError
from .models import App, AppRegistry, SourceFolder

class RegistryStore:
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)

    def load(self) -> AppRegistry | None:
        if not self.file_path.exists():
            return None
        with self.file_path.open("r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                raise AppLauncherError(
                    f"登録データが壊れています（既存ファイルは変更していません）: {self.file_path}"
                ) from e
        return AppRegistry.from_dict(data)

    def save(self, registry: AppRegistry) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.file_path.with_name(self.file_path.name + ".tmp")
        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(registry.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(temp_path, self.file_path)

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

    def find(self, registry: AppRegistry, path: str) -> App | None:
        normalized_path = self._normalize_path(path)
        for app in registry.apps:
            if self._normalize_path(app.path) == normalized_path:
                return app
        return None

    def find_covering_source(self, registry: AppRegistry, directory: Path) -> SourceFolder | None:
        """再帰スキャン済みの親フォルダで、directory を含むものを返す。"""
        for source in registry.sources:
            if source.recursive and self._is_under(str(directory), source.path):
                return source
        return None

    def apply_scan(
        self,
        registry: AppRegistry,
        directory: Path,
        recursive: bool,
        found: list[App],
    ) -> dict:
        """スキャン結果を登録へ反映する。再帰スキャン時は配下の登録元フォルダを吸収する。"""
        absorbed: list[str] = []
        if recursive:
            for source in list(registry.sources):
                if self._is_under(source.path, directory):
                    registry.sources.remove(source)
                    absorbed.append(source.path)
                    for app in registry.apps:
                        if app.source_path and self._same_path(app.source_path, source.path):
                            app.source_path = str(directory)

        source = self._find_source(registry, directory)
        if source is None:
            registry.sources.append(SourceFolder(path=str(directory), recursive=recursive))
        else:
            source.recursive = recursive

        # このフォルダから検出されなくなったアプリ（再帰OFF後の下位フォルダなど）は外す
        found_keys = {self._normalize_path(app.path) for app in found}
        registry.apps = [
            app for app in registry.apps
            if not (
                app.source_path
                and self._same_path(app.source_path, directory)
                and self._normalize_path(app.path) not in found_keys
            )
        ]

        added = 0
        for app in found:
            existing = self.find(registry, app.path)
            if existing is None:
                registry.apps.append(app)
                added += 1
            elif existing.source == "scanned":
                existing.source_path = str(directory)
        return {"added": added, "absorbed": absorbed}

    def remove_source(self, registry: AppRegistry, directory: Path) -> bool:
        """登録元フォルダと、そこから検出したアプリを外す。"""
        removed = False
        for source in list(registry.sources):
            if self._same_path(source.path, directory):
                registry.sources.remove(source)
                removed = True
        before = len(registry.apps)
        registry.apps = [
            app for app in registry.apps
            if not (app.source_path and self._same_path(app.source_path, directory))
        ]
        return removed or len(registry.apps) != before

    def _find_source(self, registry: AppRegistry, directory: Path) -> SourceFolder | None:
        for source in registry.sources:
            if self._same_path(source.path, directory):
                return source
        return None

    def _is_under(self, child: str, parent: Path | str) -> bool:
        parent_key = self._normalize_path(str(parent))
        return any(
            str(ancestor).casefold() == parent_key
            for ancestor in Path(child).resolve().parents
        )

    def _same_path(self, a: Path | str, b: Path | str) -> bool:
        return self._normalize_path(str(a)) == self._normalize_path(str(b))

    @staticmethod
    def _normalize_path(path: str) -> str:
        return str(Path(path).resolve()).casefold()
