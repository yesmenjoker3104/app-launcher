import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app_launcher import cli
from app_launcher.models import App, AppRegistry
from app_launcher.registry import RegistryStore, owner_of


class UpdateCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name)
        self.store = RegistryStore(self.root / "apps.json")
        self.alpha_exe = self.root / "alpha.exe"
        self.beta_exe = self.root / "beta.exe"
        self.alpha_exe.touch()
        self.beta_exe.touch()

        registry = AppRegistry()
        self.store.add(registry, App(name="Alpha", path=str(self.alpha_exe)))
        self.store.add(registry, App(name="Beta", path=str(self.beta_exe)))
        self.store.save(registry)

    def tearDown(self) -> None:
        self._temp.cleanup()

    def _update(
        self,
        name: str,
        new_name: str | None = None,
        path: Path | None = None,
        aliases: str | None = None,
        show_in_list: bool | None = None,
    ) -> dict:
        args = argparse.Namespace(
            name=name,
            new_name=new_name,
            path=path,
            aliases=aliases,
            show_in_list=show_in_list,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            cli.handle_update(args, self.store)
        return json.loads(output.getvalue())

    def _saved_apps(self) -> dict[str, str]:
        registry = self.store.load()
        return {app.name: app.path for app in registry.apps}

    def test_sets_aliases_and_list_visibility(self) -> None:
        result = self._update("Alpha", aliases="a, al ,a", show_in_list=False)

        self.assertTrue(result["ok"])
        registry = self.store.load()
        alpha = next(app for app in registry.apps if app.name == "Alpha")
        self.assertEqual(alpha.aliases, ["a", "al"])
        self.assertFalse(alpha.show_in_list)

    def test_rejects_alias_that_conflicts_with_another_application(self) -> None:
        result = self._update("Alpha", aliases="beta")

        self.assertFalse(result["ok"])
        registry = self.store.load()
        alpha = next(app for app in registry.apps if app.name == "Alpha")
        self.assertEqual(alpha.aliases, [])

    def test_finds_application_by_path(self) -> None:
        result = self._update(str(self.beta_exe), new_name="Beta Pro")

        self.assertTrue(result["ok"])
        self.assertIn("Beta Pro", self._saved_apps())

    def test_rejects_ambiguous_name_and_asks_for_path(self) -> None:
        registry = self.store.load()
        other_exe = self.root / "other" / "alpha.exe"
        other_exe.parent.mkdir()
        other_exe.touch()
        self.store.add(registry, App(name="Alpha", path=str(other_exe)))
        self.store.save(registry)

        result = self._update("Alpha", show_in_list=False)

        self.assertFalse(result["ok"])
        self.assertIn("パス", result["error"])

    def test_scan_records_source_and_unscan_removes_detected_apps(self) -> None:
        folder = self.root / "tools"
        folder.mkdir()
        (folder / "tool.exe").touch()

        with patch.object(cli, "load_excluded_directories", return_value=[]):
            scan_args = argparse.Namespace(directory=folder, recursive=False)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.handle_scan(scan_args, self.store), 0)
            registry = self.store.load()
            self.assertEqual(len(registry.sources), 1)
            self.assertIn("tool", {app.name for app in registry.apps})

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    cli.handle_unscan(argparse.Namespace(directory=folder), self.store),
                    0,
                )

        registry = self.store.load()
        self.assertEqual(registry.sources, [])
        self.assertEqual(set(app.name for app in registry.apps), {"Alpha", "Beta"})

    def test_rescan_removes_scanned_apps_that_disappeared(self) -> None:
        folder = self.root / "tools"
        folder.mkdir()
        gone = folder / "gone.exe"
        gone.touch()

        with patch.object(cli, "load_excluded_directories", return_value=[]):
            with contextlib.redirect_stdout(io.StringIO()):
                cli.handle_scan(argparse.Namespace(directory=folder, recursive=False), self.store)
            gone.unlink()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                cli.handle_scan(argparse.Namespace(directory=folder, recursive=False), self.store)

        self.assertEqual(json.loads(output.getvalue())["removed"], 1)
        self.assertNotIn("gone", {app.name for app in self.store.load().apps})

    def _scan(self, folder: Path, recursive: bool) -> dict:
        output = io.StringIO()
        with patch.object(cli, "load_excluded_directories", return_value=[]):
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    cli.handle_scan(argparse.Namespace(directory=folder, recursive=recursive), self.store),
                    0,
                )
        return json.loads(output.getvalue())

    def _make_nested_tree(self) -> tuple[Path, Path]:
        parent = self.root / "parent"
        child = parent / "child"
        child.mkdir(parents=True)
        (parent / "top.exe").touch()
        (child / "deep.exe").touch()
        return parent, child

    def test_parent_recursive_scan_absorbs_child_source_and_keeps_settings(self) -> None:
        parent, child = self._make_nested_tree()
        self._scan(child, recursive=False)
        self._update("deep", aliases="dp", show_in_list=False)

        result = self._scan(parent, recursive=True)

        self.assertEqual(result["absorbed"], [str(child.resolve())])
        registry = self.store.load()
        self.assertEqual([(s.path, s.recursive) for s in registry.sources], [(str(parent.resolve()), True)])
        names = [app.name for app in registry.apps]
        self.assertEqual(names.count("deep"), 1)
        deep = next(app for app in registry.apps if app.name == "deep")
        self.assertEqual(deep.aliases, ["dp"])
        self.assertFalse(deep.show_in_list)
        self.assertEqual(owner_of(registry, deep).path, str(parent.resolve()))

    def test_child_scan_under_recursive_parent_is_absorbed_by_parent(self) -> None:
        parent, child = self._make_nested_tree()
        self._scan(parent, recursive=True)
        (child / "later.exe").touch()

        result = self._scan(child, recursive=False)

        self.assertEqual(result["covered_by"], str(parent.resolve()))
        registry = self.store.load()
        self.assertEqual(len(registry.sources), 1)
        self.assertEqual(registry.sources[0].path, str(parent.resolve()))
        self.assertIn("later", {app.name for app in registry.apps})
        self.assertEqual([app.name for app in registry.apps].count("deep"), 1)

    def test_non_recursive_parent_does_not_absorb_child(self) -> None:
        parent, child = self._make_nested_tree()
        self._scan(child, recursive=False)

        result = self._scan(parent, recursive=False)

        self.assertEqual(result["absorbed"], [])
        registry = self.store.load()
        self.assertEqual(len(registry.sources), 2)

    def test_toggling_recursive_on_absorbs_and_off_keeps_parent_only(self) -> None:
        parent, child = self._make_nested_tree()
        self._scan(child, recursive=False)
        self._scan(parent, recursive=False)

        self._scan(parent, recursive=True)
        self.assertEqual(
            [(s.path, s.recursive) for s in self.store.load().sources],
            [(str(parent.resolve()), True)],
        )

        self._scan(parent, recursive=False)
        registry = self.store.load()
        self.assertEqual([(s.path, s.recursive) for s in registry.sources], [(str(parent.resolve()), False)])
        self.assertEqual({app.name for app in registry.apps} & {"top", "deep"}, {"top"})

    def test_renames_application_and_saves(self) -> None:
        result = self._update("alpha", new_name="Alpha Pro")

        self.assertTrue(result["ok"])
        self.assertEqual(result["app"]["name"], "Alpha Pro")
        self.assertIn("Alpha Pro", self._saved_apps())
        self.assertNotIn("Alpha", self._saved_apps())

    def test_changes_path_to_existing_file(self) -> None:
        new_exe = self.root / "alpha2.exe"
        new_exe.touch()

        result = self._update("Alpha", path=new_exe)

        self.assertTrue(result["ok"])
        self.assertEqual(self._saved_apps()["Alpha"], str(new_exe.resolve()))

    def test_rejects_unknown_application(self) -> None:
        result = self._update("Gamma", new_name="Delta")

        self.assertFalse(result["ok"])
        self.assertEqual(set(self._saved_apps()), {"Alpha", "Beta"})

    def test_rejects_path_already_used_by_another_application(self) -> None:
        result = self._update("Alpha", path=self.beta_exe)

        self.assertFalse(result["ok"])
        self.assertEqual(self._saved_apps()["Alpha"], str(self.alpha_exe))

    def test_rejects_missing_executable(self) -> None:
        result = self._update("Alpha", path=self.root / "missing.exe")

        self.assertFalse(result["ok"])
        self.assertEqual(self._saved_apps()["Alpha"], str(self.alpha_exe))

    def test_rejects_update_without_changes(self) -> None:
        result = self._update("Alpha")

        self.assertFalse(result["ok"])

    def test_rejects_empty_new_name(self) -> None:
        result = self._update("Alpha", new_name="   ")

        self.assertFalse(result["ok"])
        self.assertIn("Alpha", self._saved_apps())


        self.assertIn("Alpha", self._saved_apps())


class DataDirectoryTests(unittest.TestCase):
    def test_uses_source_data_directory_for_legacy_data(self) -> None:
        expected = Path(cli.__file__).resolve().parents[2] / "data"

        with patch.object(cli.sys, "frozen", False, create=True):
            self.assertEqual(cli.legacy_data_directory(), expected)

    def test_uses_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"LOCALAPPDATA": temp_dir}):
                self.assertEqual(
                    cli.data_directory(),
                    Path(temp_dir) / "app-launcher",
                )

    def test_migrates_legacy_files_without_overwriting_new_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy = root / "old-data"
            legacy.mkdir()
            (legacy / "apps.json").write_text(
                '{"apps": ["old"]}',
                encoding="utf-8",
            )
            (legacy / "config.json").write_text(
                '{"excluded_directories": []}',
                encoding="utf-8",
            )

            local_app_data = root / "local"
            new_data = local_app_data / "app-launcher"
            new_data.mkdir(parents=True)
            (new_data / "apps.json").write_text(
                '{"apps": ["new"]}',
                encoding="utf-8",
            )

            with (
                patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}),
                patch.object(cli, "legacy_data_directory", return_value=legacy),
            ):
                cli.migrate_legacy_data()

            self.assertEqual(
                (new_data / "apps.json").read_text(encoding="utf-8"),
                '{"apps": ["new"]}',
            )
            self.assertEqual(
                (new_data / "config.json").read_text(encoding="utf-8"),
                '{"excluded_directories": []}',
            )
            self.assertTrue((legacy / "apps.json").exists())


if __name__ == "__main__":
    unittest.main()