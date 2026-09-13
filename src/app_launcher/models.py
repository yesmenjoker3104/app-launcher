from dataclasses import dataclass, field
from typing import Literal

@dataclass
class App:
    """
    Windows アプリケーション情報
    """
    name: str                    # 表示名（例: "Microsoft Excel"）
    path: str                    # 実行ファイルの絶対パス
    aliases: list[str] = field(default_factory=list)  # エイリアス（例: ["excel", "xls"]）
    enabled: bool = True         # 有効・無効状態
    source: Literal["manual", "scanned"] = "manual"  # 登録元


@dataclass
class AppRegistry:
    """
    登録済みアプリ一覧（apps.json全体）
    """
    apps: list[App] = field(default_factory=list)

    def to_dict(self) -> dict:
        """辞書形式に変換（JSON保存用）"""
        return {
            "apps": [
                {
                    "name": app.name,
                    "path": app.path,
                    "aliases": app.aliases,
                    "enabled": app.enabled,
                    "source": app.source,
                }
                for app in self.apps
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppRegistry":
        """辞書から復元（JSON読み込み用）"""
        apps = [
            App(
                name=app_data["name"],
                path=app_data["path"],
                aliases=app_data.get("aliases", []),
                enabled=app_data.get("enabled", True),
                source=app_data.get("source", "manual"),
            )
            for app_data in data.get("apps", [])
        ]
        return cls(apps=apps)