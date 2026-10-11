import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import app


class SharedDatabaseTests(unittest.TestCase):
    def test_windows_and_macos_portables_use_repository_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for platform, relative in [("win32", "dist/Torremolinos.exe"), ("darwin", "dist/Torremolinos.app/Contents/MacOS/Torremolinos")]:
                with self.subTest(platform=platform), patch.object(app, "IS_FROZEN", True), patch.object(app.sys, "platform", platform), patch.object(app.sys, "executable", str(root / relative)), patch.object(app, "_git_toplevel", return_value=root) as git_root:
                    self.assertEqual(app.application_base_dir(), root)
                    git_root.assert_called_once_with(root / "dist")

    def test_source_uses_same_database_as_sync(self):
        self.assertEqual(app.DEFAULT_DB, app.BASE_DIR / app.DATA_SYNC_DB_PATH)
        self.assertEqual(app.TorremolinosHandler.db_path, app.DEFAULT_DB)
        self.assertEqual(app.DATA_SYNC_BRANCH, "data-sync")

    def test_push_stores_canonical_database_and_removes_legacy_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "data/torremolinos.sqlite3"
            with patch.object(app, "DEFAULT_DB", database), patch.object(app, "ATTACHMENT_DIR", root / "data/attachments"), patch.object(app, "fetch_data_sync_branch", return_value=None), patch.object(app, "git_run", return_value=SimpleNamespace(stdout="abc")) as git:
                self.assertTrue(app.push_application_data())
            commands = [call.args[0] for call in git.call_args_list]
            self.assertIn(["hash-object", "-w", str(database.resolve())], commands)
            self.assertIn(["update-index", "--add", "--cacheinfo", "100644,abc,data/torremolinos.sqlite3"], commands)
            self.assertTrue(any("dist/data/torremolinos.sqlite3" in command and "rm" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
