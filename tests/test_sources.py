import tempfile
import unittest
from pathlib import Path

from app_launcher.discovery import scan_directory
from app_launcher.errors import AppLauncherError
from app_launcher.models import App, AppRegistry, SourceFolder
from app_launcher.registry import RegistryStore


class RegistryRoundTripTests(unittest.TestCase):
    def test_sources_and_visibility_survive_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RegistryStore(Path(tmp) / "apps.json")
            registry = AppRegistry(
                apps=[App(
                    name="tool",
                    path=str(Path(tmp) / "tool.exe"),
                    source="scanned",
                    source_path=tmp,
                    show_in_list=False,
                )],
                sources=[SourceFolder(path=tmp, recursive=True)],
            )
            store.save(registry)
            self.assertEqual(store.load(), registry)

    def test_broken_registry_is_reported_and_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "apps.json"
            file.write_text("{broken", encoding="utf-8")
            store = RegistryStore(file)
            with self.assertRaises(AppLauncherError):
                store.load()
            self.assertEqual(file.read_text(encoding="utf-8"), "{broken")


class ApplyScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.store = RegistryStore(self.root / "data" / "apps.json")
        self.apps_dir = self.root / "apps"
        (self.apps_dir / "sub").mkdir(parents=True)
        (self.apps_dir / "top.exe").write_bytes(b"MZ")
        (self.apps_dir / "sub" / "deep.exe").write_bytes(b"MZ")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def scan(self, registry: AppRegistry, directory: Path, recursive: bool) -> dict:
        found = scan_directory(directory, recursive=recursive, excluded_directories=set())
        for app in found:
            app.source_path = str(directory)
        return self.store.apply_scan(registry, directory, recursive, found)

    @staticmethod
    def names(registry: AppRegistry) -> set[str]:
        return {app.name for app in registry.apps}

    def test_turning_recursive_off_removes_deeper_apps(self) -> None:
        registry = AppRegistry()
        self.scan(registry, self.apps_dir, True)
        self.assertEqual(self.names(registry), {"top", "deep"})

        self.scan(registry, self.apps_dir, False)
        self.assertEqual(self.names(registry), {"top"})
        self.assertEqual(registry.sources, [SourceFolder(str(self.apps_dir), False)])

    def test_parent_recursive_scan_absorbs_child_source_and_keeps_aliases(self) -> None:
        registry = AppRegistry()
        sub = self.apps_dir / "sub"
        self.scan(registry, sub, False)
        deep = self.store.find(registry, str(sub / "deep.exe"))
        deep.aliases = ["dp"]

        result = self.scan(registry, self.apps_dir, True)

        self.assertEqual(result["absorbed"], [str(sub)])
        self.assertEqual(registry.sources, [SourceFolder(str(self.apps_dir), True)])
        apps = [app for app in registry.apps if app.name == "deep"]
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0].aliases, ["dp"])
        self.assertEqual(apps[0].source_path, str(self.apps_dir))

    def test_child_folder_is_covered_by_recursive_parent(self) -> None:
        registry = AppRegistry()
        self.scan(registry, self.apps_dir, True)
        covering = self.store.find_covering_source(registry, self.apps_dir / "sub")
        self.assertEqual(covering, SourceFolder(str(self.apps_dir), True))

    def test_remove_source_deletes_only_its_apps(self) -> None:
        registry = AppRegistry(apps=[App(name="memo", path=r"C:\Windows\System32\notepad.exe")])
        self.scan(registry, self.apps_dir, True)

        self.assertTrue(self.store.remove_source(registry, self.apps_dir))

        self.assertEqual(self.names(registry), {"memo"})
        self.assertEqual(registry.sources, [])

    def test_scan_does_not_claim_manually_registered_app(self) -> None:
        manual = App(name="custom", path=str(self.apps_dir / "top.exe"), source="manual")
        registry = AppRegistry(apps=[manual])
        self.scan(registry, self.apps_dir, False)

        self.assertIsNone(manual.source_path)
        self.assertEqual(manual.source, "manual")
        self.store.remove_source(registry, self.apps_dir)
        self.assertEqual(self.names(registry), {"custom"})


if __name__ == "__main__":
    unittest.main()
