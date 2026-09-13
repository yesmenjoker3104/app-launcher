# app-launcher 設計メモ

## 目的

`assist-chat`から自然文でWindowsアプリを操作するためのローカルCLI。
アプリ一覧を表示するだけのランチャーではなく、LLMが解釈したファイルとアプリを実際に起動する。

例:

```text
〇〇.xlsxをExcelで開いて
```

## 役割分担

### assist-chat

- 自然文をLLMで解釈する
- 対象ファイルとアプリ名をJSON化する
- 破壊的でない起動操作についても必要に応じて確認を表示する
- app-launcher CLIを呼び出す
- CLIのJSON結果をチャットに表示する

想定JSON:

```json
{
  "action": "app_open",
  "path": "D:\\documents\\sample.xlsx",
  "application": "Excel"
}
```

### app-launcher

- LLMから渡されたアプリ名を実際のWindowsアプリへ解決する
- 登録済みExeを検索する
- 対象ファイルの存在を確認する
- 指定アプリで対象ファイルを起動する
- アプリの登録・スキャン・一覧表示・削除を行う
- stdoutへ1行のJSONを返す

## plugin.jsonの方針

アプリごとに`plugin.json`を書く方式にはしない。

`assist-chat/plugin/`にはAppLauncher用の汎用プラグインを一つだけ置き、以下のアクションを定義する。

- `app_open`
- `app_register`
- `app_scan`
- `app_list`
- 必要に応じて`app_remove`

Excel、Word、個別のExeなどを追加するたびに`plugin.json`を編集する必要はない。

## アプリ登録

登録情報は`app-launcher`独自のファイルで管理する。

登録DBは、カレントディレクトリに依存せず、app-launcherの配置場所を基準に保存する。

- ソース実行時: `app-launcher/data/apps.json`
- Exe実行時: `AppLauncherCli.exe`と同じ場所の`data/apps.json`
- assist-chatから利用時: `assist-chat/plugin/AppLauncher/data/apps.json`

実行時に変更される`apps.json`は、実行ファイルの配置先にある`data`フォルダへ保存する。

登録例:

```json
{
  "apps": [
    {
      "name": "MyApp",
      "path": "D:\\Tools\\MyApp\\MyApp.exe",
      "aliases": ["myapp"],
      "enabled": true,
      "source": "manual"
    }
  ]
}
```

### 個別Exeの直接登録

インストーラーが存在しないExeを登録できるようにする。

```text
app-launcher register "D:\Tools\MyApp\MyApp.exe"
```

必要に応じて表示名を指定する。

```text
app-launcher register "D:\Tools\MyApp\MyApp.exe" --name "MyApp"
```

### フォルダ再帰スキャン

指定フォルダ配下のExeを再帰的に探して登録する。

```text
app-launcher scan "D:\Tools" --recursive
```

スキャンの方針:

- `.exe`のみを対象にする
- 同じパスは重複登録しない
- 既定で`Windows`、`Program Files`などのシステム領域は除外する
- 登録候補を一覧表示できるようにする
- スキャンしただけではアプリを実行しない
- 必要なら登録前にユーザー確認を行う

## アプリ検索

アプリ名から実行ファイルを解決する。

検索対象の優先順位:

1. `data/apps.json`の登録済みアプリ
2. Windowsのスタートメニューショートカット
3. `PATH`上のExe
4. Windowsレジストリや既知のインストール情報
5. ファイル拡張子の既定アプリ

例:

- `Excel`
- `エクセル`
- `Microsoft Excel`

これらを同じアプリとして解決できるよう、表示名・Exe名・自動生成エイリアスを利用する。

アプリ名が省略された場合は、Windowsの既定アプリで開く。

## 起動

```text
app-launcher open "D:\資料\sample.xlsx" --application "Excel"
```

アプリ指定なしの場合:

```text
app-launcher open "D:\資料\sample.xlsx"
```

この場合はWindowsの既定アプリを使用する。

## 登録アプリ一覧

```text
app-launcher list
```

自然文の例:

```text
登録中のアプリを一覧表示して
登録されているアプリを見せて
```

一覧には次の情報を表示する。

- 表示名
- 実行ファイルのパス
- エイリアス
- 登録元
- 有効・無効状態

## 自然文の利用例

```text
〇〇.xlsxをExcelで開いて
```

```text
D:\Tools\MyApp\MyApp.exeを登録して
```

```text
D:\Tools配下のアプリを登録して
```

```text
登録中のアプリを一覧表示して
```

```text
MyAppでD:\資料\data.xlsxを開いて
```

```text
登録した画像編集ソフトでphoto.pngを開いて
```

## 安全方針

- Exeの登録とスキャンは、登録するだけで実行しない
- `.exe`以外の不明な実行形式は対象外にする
- ファイルとアプリの存在を実行前に確認する
- 未登録アプリを実行する場合は明確な確認を表示する
- `assist-chat`側で起動前確認を行う
- エラー時はstdoutに`{"ok": false, "error": "説明"}`を1行で返す
- 成功時はstdoutに`{"ok": true, ...}`を1行で返す
- ログやチャットに秘密情報を出力しない

## CLI出力契約

`assist-chat`のプラグイン契約に合わせ、stdoutには必ず1行のJSONだけを出力する。

```json
{"ok": true, "action": "app_list", "apps": []}
```

```json
{"ok": false, "error": "対象ファイルが見つかりません。"}
```

CLIのデバッグ情報や詳細ログはstderrへ出力する。

## 実装の基本構成

```text
app-launcher/
├── pyproject.toml
├── src/
│   └── app_launcher/
│       ├── __init__.py
│       ├── __main__.py       # python -m app_launcher
│       ├── cli.py            # 引数解析と終了コード
│       ├── models.py         # AppEntryなどのデータ型
│       ├── registry.py       # apps.jsonの読み書き・登録・削除
│       ├── discovery.py      # Exe検索・アプリ名解決
│       ├── launcher.py       # Windowsでのファイル起動
│       └── errors.py         # CLIへ返す例外
├── tests/
│   ├── test_registry.py
│   ├── test_discovery.py
│   └── test_cli.py
└── data/
  └── apps.json             # 開発用。実運用ではLocalAppDataへ保存
```

`src`レイアウトを採用し、インストール後のパッケージを実際にimportしてテストできるようにする。`pyproject.toml`の`project.scripts`から`app_launcher.cli:main`を起動する。

## モジュールの責務

### `cli.py`

- サブコマンドと引数を解析する
- `registry`、`discovery`、`launcher`を呼び出す
- 結果をstdoutへ1行のJSONで出力する
- 業務ロジックやWindows API処理を持たない

### `models.py`

登録情報を`dataclass`などで表現する。

```python
AppEntry(
  name="MyApp",
  path=Path(r"D:\Tools\MyApp\MyApp.exe"),
  aliases=["myapp"],
  enabled=True,
  source="manual",
)
```

### `registry.py`

- JSONファイルの読み書き
- パスの正規化
- 登録・重複判定・削除
- 有効/無効の管理
- 原子的な保存（temporary fileへ書いてから置換）

### `discovery.py`

- 登録済みアプリの名前・エイリアス検索
- スタートメニューのショートカット検索
- `PATH`上のExe検索
- 必要に応じたレジストリ検索
- フォルダ再帰スキャン

検索処理と登録処理は分ける。検索で見つけただけでは`apps.json`を変更しない。

### `launcher.py`

- 対象ファイルの存在確認
- 実行ファイルの存在確認
- 指定Exeへ対象ファイルを引数として渡す
- アプリ指定なしの場合はWindowsの既定アプリで開く
- `subprocess.Popen`や`os.startfile`による起動

## CLIの責務と例

```text
app-launcher register "D:\Tools\MyApp\MyApp.exe" --name "MyApp"
app-launcher scan "D:\Tools" --recursive
app-launcher list
app-launcher remove "MyApp"
app-launcher open "D:\資料\sample.xlsx" --application "Excel"
```

CLIは次の処理を直接実装せず、各モジュールへ委譲する。

- Windowsアプリの探索
- JSONファイルの詳細な更新処理
- 実行ファイルの起動処理

## 設定とデータ

次のデータを混在させない。

- `pyproject.toml`: 開発者が管理するプロジェクト設定
- `data/apps.json`: アプリ登録情報
- `%LOCALAPPDATA%\app-launcher\`: ユーザーごとの実行時データ
- `tests/`: テストコード

`apps.json`が壊れていた場合は、既存ファイルを上書きせずエラーJSONを返す。保存時は一時ファイルを使って破損を避ける。

## テスト方針

- `registry.py`: temporary directory上で登録・一覧・重複・削除をテストする
- `discovery.py`: 実行ファイルを実際には起動せず、パス検索と除外規則をテストする
- `launcher.py`: Windows実行部分はモックし、渡された引数を検証する
- `cli.py`: stdoutが1行JSONになることと終了コードをテストする
- 実際のアプリ起動は手動の統合テストで確認する

自動テストからExcelなどの実アプリを起動しない。

## 初期実装の優先順位

1. `apps.json`の読み書き
2. 個別Exe登録
3. 登録アプリ一覧
4. 登録済みアプリによるファイル起動
5. フォルダ再帰スキャン
6. Windowsの既定アプリ起動
7. スタートメニュー・PATH・レジストリからの自動解決
8. `assist-chat`用の汎用プラグイン追加
