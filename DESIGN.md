# app-launcher 設計メモ

## 現在の状態

実装済みの範囲と、計画のみの範囲を分けて記載する。

- 実装済み
  - フォルダ登録（再帰の有無は後から変更可能）と検知Exeの一覧
  - 登録元の統合（親フォルダへの移行と子の登録削除）
  - 登録アプリの一覧、エイリアス設定、一覧表示の有無
  - 登録アプリでのファイル・フォルダ起動（複数指定に対応）
  - 旧データの移行（`data\` から `%LOCALAPPDATA%\app-launcher\` へ）
  - `--version`
- 未実装（計画）
  - `assist-chat`連携と`plugin.json`
  - アプリ名の自動解決（スタートメニュー、PATH、レジストリ、拡張子の既定アプリ）
  - アプリ省略時のWindows既定アプリ起動
  - `apps.json`の原子的な保存（現状は直接書き込み）

ore-filerのUIでは、フォルダの登録・再帰設定・一覧表示と、エイリアスの設定を行う。CLIの`register`は手動登録（`source: manual`）用に残している。

## 目的

`assist-chat`から自然文でWindowsアプリを操作するためのローカルCLI。
アプリ一覧を表示するだけのランチャーではなく、指定されたファイルやフォルダを登録済みアプリで実際に開く。

例（計画）:

```text
〇〇.xlsxをExcelで開いて
```

## 役割分担

### assist-chat（計画・未実装）

- 自然文をLLMで解釈する
- 対象ファイルとアプリ名をJSON化する
- 起動前に必要に応じて確認を表示する
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

- 登録済みアプリの名前またはエイリアスから、起動するExeを決める
- 指定されたファイルやフォルダを、登録済みアプリで開く
- 登録元フォルダを指定し、配下のExeを検知して登録する（再帰の有無を選べる）
- 登録元フォルダと、登録アプリの名前・エイリアス・一覧表示の有無を変更する
- 登録アプリの一覧表示と削除
- stdoutへ1行のJSONを返す

ore-filerでは`L`キーからダイアログを開き、同じレジストリを参照する。

## plugin.jsonの方針（計画・未実装）

アプリごとに`plugin.json`を書く方式にはしない。

`assist-chat/plugin/`にはAppLauncher用の汎用プラグインを一つだけ置き、以下のアクションを定義する。

- `app_open`
- `app_register`
- `app_scan`
- `app_list`
- 必要に応じて`app_remove`

Excel、Word、個別のExeなどを追加するたびに`plugin.json`を編集する必要はない。

## データ保存先

実行時に変更されるデータは、ユーザーごとの`%LOCALAPPDATA%\app-launcher\`に保存する。
カレントディレクトリには依存しない。

| ファイル | 内容 |
| --- | --- |
| `apps.json` | 登録アプリと登録元フォルダ |
| `config.json` | 検知時に除外するフォルダ名 |

`LOCALAPPDATA`が無い場合は、開発時の`data\`（app-launcherのプロジェクト直下）を使う。

旧`data\`にデータがあり、`%LOCALAPPDATA%\app-launcher\apps.json`が存在しない場合は、起動時に旧データを複製する。新しい`apps.json`が既にあれば何もしない。

## apps.jsonの構造

```json
{
  "apps": [
    {
      "name": "MyApp",
      "path": "D:\\Tools\\MyApp\\MyApp.exe",
      "aliases": ["myapp"],
      "enabled": true,
      "source": "scanned",
      "show_in_list": true
    }
  ],
  "sources": [
    {
      "path": "D:\\Tools",
      "recursive": true
    }
  ]
}
```

- `apps[].source`: `manual`（`register`で登録）または`scanned`（登録元フォルダから検知）
- `apps[].show_in_list`: ore-filerの一覧に表示するか。`false`でも、エイリアスで起動できる
- `sources[]`: 登録元フォルダ。`recursive`は配下のサブフォルダも検知するかを表す

## 登録元フォルダと検知

登録はフォルダ単位で行う。個別Exeの追加はore-filerのUIでは行わない。

```text
app-launcher scan "D:\Tools" --recursive
app-launcher scan "D:\Tools"
app-launcher unscan "D:\Tools"
```

- `scan`は、未登録のフォルダなら登録元として追加する
- 登録済みのフォルダを`scan`し直すと、再帰設定を更新して再スキャンする
- 除外フォルダ名（`config.json`の`excluded_directories`）を、登録元からの相対パスのフォルダ名と照合する。登録元より上のフォルダ名（例: `Program Files`）では除外しない
- `.exe`のみを対象にする
- `unscan`は登録元と、その登録元が検知したアプリを削除する

### 所有ルール

検知したアプリは、最も深い登録元が所有する。

- 非再帰の登録元は、直下のExeだけを所有する
- 再帰の登録元は、配下のすべてのExeを所有する

### 統合ルール

- 再帰の登録元の配下フォルダを`scan`した場合、子フォルダは登録せず、親を再スキャンする。結果の`covered_by`に親のパスが入る
- 再帰の登録元の配下に既存の登録元がある場合、子の登録元を親へ統合する（結果の`absorbed`に子のパスが入る）
- 統合された子のアプリは所有者が親になり、エイリアスと一覧表示の設定を保持する
- 再帰をOFFにすると、子フォルダ由来のアプリは削除される。統合された子の登録元は復活しない
- 所有者のいない検知アプリは、再スキャン時に削除する
- 手動登録（`manual`）のアプリは、再スキャンの対象外

## アプリ検索

`find_application`が、登録済みかつ有効なアプリの名前とエイリアスを、大文字小文字を無視して完全一致で探す。

見つからない場合は、次のエラーをJSONで返す。

```json
{"ok": false, "error": "登録されているアプリが見つかりません: <指定された名前>"}
```

計画（未実装）の検索対象:

1. スタートメニューのショートカット
2. `PATH`上のExe
3. Windowsレジストリや既知のインストール情報
4. ファイル拡張子の既定アプリ

## 起動

```text
app-launcher open "D:\資料\a.xlsx" "D:\資料\b.xlsx" --application "Excel"
```

- `--application`は必須。省略するとargparseのエラーになる
- ファイルを複数指定すると、1つのプロセスにまとめて渡す（`Popen([app, *files])`）
- ファイルを指定しない場合は、アプリ単体で起動する
- ファイルとフォルダは`exists()`で存在を確認する。存在しない場合はエラーを返す
- Windowsの既定アプリで開く機能は未実装

## 登録アプリ一覧

```text
app-launcher list
```

出力される主な項目:

- `apps`: 名前、パス、エイリアス、有効状態、登録元（`source`）、一覧表示（`show_in_list`）、所有する登録元のパス（`source_path`）
- `sources`: 登録元フォルダのパスと再帰設定

## 安全方針

- 登録とスキャンは、Exeを実行しない
- `.exe`以外は検知対象にしない
- CLIは登録済みのアプリしか起動しない。未登録のパスを直接指定して起動することはない
- ファイルとアプリの存在を実行前に確認する
- エラー時はstdoutに`{"ok": false, "error": "説明"}`を1行で返す
- 成功時はstdoutに`{"ok": true, ...}`を1行で返す
- ログやチャットに秘密情報を出力しない
- 起動前の確認表示は`assist-chat`側で行う（計画）

## CLI出力契約

`assist-chat`のプラグイン契約に合わせ、stdoutには必ず1行のJSONだけを出力する。終了コードは成功で`0`、失敗で`1`。

```json
{"ok": true, "action": "app_list", "apps": [], "sources": []}
```

```json
{"ok": false, "error": "登録されているアプリが見つかりません: Excel"}
```

CLIのデバッグ情報や詳細ログはstderrへ出力する。

想定外の例外（`apps.json`の破損など）は、汎用メッセージのエラーJSONを返す。読み込みで失敗した場合は保存されないため、既存の`apps.json`は上書きされない。

## 実装の基本構成

```text
app-launcher/
├── pyproject.toml            # project.scripts: app-launcher = app_launcher.cli:main
├── cli_entry.py              # PyInstaller用のエントリポイント
├── build.ps1                 # dist\app-launcher\app-launcher.exe のビルド
├── .github/workflows/release.yml
├── src/
│   └── app_launcher/
│       ├── __init__.py       # __version__
│       ├── __main__.py       # python -m app_launcher
│       ├── cli.py            # 引数解析、保存先、各処理の呼び出し
│       ├── models.py         # App、SourceFolder、AppRegistry
│       ├── registry.py       # apps.jsonの読み書き、登録元の所有・統合
│       ├── discovery.py      # Exeの検知、登録済みアプリの検索
│       ├── launcher.py       # 登録済みアプリでの起動
│       ├── config.py         # 除外フォルダ設定
│       └── errors.py         # CLIへ返す例外
└── tests/
    ├── test_cli.py
    ├── test_discovery.py
    ├── test_launcher.py
    └── test_registry.py
```

`src`レイアウトを採用し、インストール後のパッケージを実際にimportしてテストできるようにする。

## モジュールの責務

### `cli.py`

- サブコマンドと引数を解析する
- 保存先の決定と、旧データの移行を行う
- `registry`、`discovery`、`launcher`を呼び出す
- 結果をstdoutへ1行のJSONで出力する

### `models.py`

- `App`: 登録アプリ。`name`、`path`、`aliases`、`enabled`、`source`、`show_in_list`
- `SourceFolder`: 登録元フォルダ。`path`、`recursive`
- `AppRegistry`: `apps`と`sources`を持つ全体。JSONとの相互変換を行う

### `registry.py`

- `RegistryStore`: JSONの読み込み、保存、登録（重複判定）、削除
- 登録元の検索（`find_source`、`find_covering_source`）
- 登録元の統合（`absorb_nested_sources`）と所有者の判定（`owner_of`）

### `discovery.py`

- `scan_directory`: 指定フォルダのExeを検知する。再帰は引数で切り替える
- `find_application`: 登録済みアプリの名前とエイリアスの検索
- `is_excluded_path`: 登録元からの相対パスで除外フォルダ名を判定する

検索処理と登録処理は分ける。検索で見つけただけでは`apps.json`を変更しない。

### `launcher.py`

- `open_with_application`: 指定ファイルを、1つのプロセスにまとめて登録アプリへ渡す
- `launch_application`: ファイルを指定せずにアプリを起動する

### `config.py`

- `load_excluded_directories`: `config.json`の`excluded_directories`を読み込む。ファイルが無い場合は既定の除外名を使う

### `errors.py`

- `AppLauncherError`と、その派生の例外クラス

## CLIの例

```text
app-launcher --version
app-launcher scan "D:\Tools" --recursive
app-launcher scan "D:\Tools"
app-launcher unscan "D:\Tools"
app-launcher register "D:\Tools\MyApp\MyApp.exe" --name "MyApp"
app-launcher update "MyApp" --aliases "myapp,my" --hide-from-list
app-launcher list
app-launcher remove "MyApp"
app-launcher open "D:\資料\sample.xlsx" --application "Excel"
```

`update`の対象は、名前またはパスで指定する。`--aliases`は既存のエイリアスを置き換える。`--show-in-list`と`--hide-from-list`は同時に指定できない。

## 設定とデータ

次のデータを混在させない。

- `pyproject.toml`: 開発者が管理するプロジェクト設定
- `%LOCALAPPDATA%\app-launcher\apps.json`: 登録アプリと登録元フォルダ
- `%LOCALAPPDATA%\app-launcher\config.json`: 除外フォルダ名
- `data\`: 開発時の旧データ（移行元。新しい保存先が無いときだけ参照する）
- `tests/`: テストコード

除外フォルダの既定値は`Windows`、`Program Files`、`Program Files (x86)`、`ProgramData`。

```json
{
  "excluded_directories": ["Windows", "Program Files", "Program Files (x86)", "ProgramData"]
}
```

## 既知の課題

- `apps.json`の保存は直接書き込みで、原子的ではない。書き込み中に失敗すると、ファイルが壊れる可能性がある
- 破損した`apps.json`のエラーメッセージが汎用的で、原因が分かりにくい
- アプリ名の自動解決と、Windows既定アプリでの起動は未実装

## 配布

GitHub Actions（`.github/workflows/release.yml`）が、次の場合にWindows向けのビルドを行い、Releaseへ添付する。

- タグ`v*.*.*`を push したとき
- `dev-latest`タグを push したとき（プレリリース扱い）
- 手動実行（`workflow_dispatch`）のとき（プレリリース扱い）

流れ:

1. `PYTHONPATH=src`を設定し、`python -m unittest discover -s tests`を実行する（ランナーには editable install が無いため）
2. `build.ps1`が`dist\app-launcher\app-launcher.exe`を作成する（`--onefile --console`）。spec ファイルは`build\`に出力する
3. `dist\app-launcher`を`app-launcher-Windows.zip`にまとめ、zip の中身は`app-launcher\app-launcher.exe`になる

ore-filerでの配置: zip を展開し、`app-launcher\`フォルダを ore-filer.exe と同じフォルダに置く。ore-filerは`app_launcher_path`が未設定なら、このフォルダの`app-launcher.exe`を探す。

データは配布に含めない。`apps.json`と`config.json`は、初回実行時に`%LOCALAPPDATA%\app-launcher\`へ作られる。`data\`は開発時の移行元であり、ビルドには使わない。

バージョンは`src\app_launcher\__init__.py`の`__version__`が正で、タグとは連動しない。リリース前に手動で揃える。

## テスト方針

- `registry.py`: 一時フォルダ上で、登録、重複、登録元の統合、所有者の判定を確認する
- `discovery.py`: Exeを実際には起動せず、検知と除外規則（登録元より上のフォルダ名は対象外）、非再帰と再帰を確認する
- `launcher.py`: 起動処理はモックし、渡された引数（複数ファイルを含む）を検証する
- `cli.py`: stdoutが1行のJSONであること、終了コード、`--version`を確認する
- 実際のアプリ起動は、自動テストでは行わない

実行:

```text
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## 実装の進捗

1. 済: `apps.json`の読み書き（`%LOCALAPPDATA%`への保存、旧データの移行）
2. 済: 手動登録（`register`）
3. 済: 登録アプリの一覧（`list`）と設定（`update`）
4. 済: 登録アプリでのファイル・フォルダ起動（複数指定）
5. 済: フォルダ登録、再帰の切り替え、統合（`scan`、`unscan`）
6. 未: Windows既定アプリでの起動
7. 未: スタートメニュー、PATH、レジストリからの自動解決
8. 未: `assist-chat`用の汎用プラグイン
9. 未: `apps.json`の原子的な保存
