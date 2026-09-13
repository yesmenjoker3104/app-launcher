import json
from pathlib import Path

from .models import AppRegistry, App

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

    @staticmethod
    def _normalize_path(path: str) -> str:
        return str(Path(path).resolve()).casefold()