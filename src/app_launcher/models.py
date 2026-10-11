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
    show_in_list: bool = True    # 一覧（ore-filer の L キー）に表示するか


@dataclass
class SourceFolder:
    """
    exe を検知するために登録したフォルダ
    """
    path: str
    recursive: bool = False


@dataclass
class AppRegistry:
    """
    登録済みアプリ一覧（apps.json全体）
    """
    apps: list[App] = field(default_factory=list)
    sources: list[SourceFolder] = field(default_factory=list)

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
                    "show_in_list": app.show_in_list,
                }
                for app in self.apps
            ],
            "sources": [
                {
                    "path": source.path,
                    "recursive": source.recursive,
                }
                for source in self.sources
            ],
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
                show_in_list=app_data.get("show_in_list", True),
            )
            for app_data in data.get("apps", [])
        ]
        sources = [
            SourceFolder(
                path=source_data["path"],
                recursive=source_data.get("recursive", False),
            )
            for source_data in data.get("sources", [])
        ]
        return cls(apps=apps, sources=sources)