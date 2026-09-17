import sqlite3
import subprocess
import tempfile
import unittest
import shutil
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import app
from torremolinos.db import connect, init_db


def run_git(repository: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


class DataSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "repository"
        self.remote = self.root / "remote.git"
        self.database = self.repository / "data" / "torremolinos.sqlite3"
        self.attachments = self.repository / "data" / "attachments"
        self.onedrive = self.root / "OneDrive"
        self.repository.mkdir()
        self.attachments.mkdir(parents=True)
        self.onedrive.mkdir()
        init_db(self.database)
        (self.repository / "app.py").write_text("version = 1\n", encoding="utf-8")
        (self.attachments / "evidencia.pdf").write_bytes(b"evidencia")

        run_git(self.repository, "init", "-b", "main")
        run_git(self.repository, "config", "user.name", "Test")
        run_git(self.repository, "config", "user.email", "test@example.com")
        run_git(self.repository, "add", "app.py")
        run_git(self.repository, "commit", "-m", "Initial code")
        subprocess.run(
            ["git", "init", "--bare", str(self.remote)],
            check=True,
            capture_output=True,
            text=True,
        )
        run_git(self.repository, "remote", "add", "origin", str(self.remote))
        run_git(self.repository, "push", "-u", "origin", "main")

        self.globals_patch = patch.multiple(
            app,
            BASE_DIR=self.repository,
            DEFAULT_DB=self.database,
            ATTACHMENT_DIR=self.attachments,
            ONEDRIVE_LOCAL_FOLDER=self.onedrive,
            ONEDRIVE_EVIDENCE_DIR=self.onedrive / "Torremolinos" / "Evidencias",
            ONEDRIVE_TOKEN_CACHE=self.root / ".onedrive-token-cache.json",
            SYNC_STATE_FILE=self.repository / ".torremolinos-sync.json",
        )
        self.globals_patch.start()

    def tearDown(self):
        self.globals_patch.stop()
        self.temporary_directory.cleanup()

    def test_push_and_pull_use_canonical_paths_across_installations(self):
        source_before = (self.repository / "app.py").read_text(encoding="utf-8")
        main_before = run_git(self.repository, "rev-parse", "main").stdout.strip()

        self.assertTrue(app.push_application_data())

        packaged_root = self.repository / "dist"
        packaged_database = packaged_root / "data" / "torremolinos.sqlite3"
        packaged_attachments = packaged_root / "data" / "attachments"
        packaged_attachments.mkdir(parents=True)
        shutil.copy2(self.database, packaged_database)
        (packaged_attachments / "portatil.pdf").write_bytes(b"evidencia portable")
        with connect(packaged_database) as conn:
            conn.execute(
                "INSERT INTO properties (house_number, owner_name) VALUES (?, ?)",
                (777, "Cambio desde ejecutable"),
            )

        app.BASE_DIR = packaged_root
        app.DEFAULT_DB = packaged_database
        app.ATTACHMENT_DIR = packaged_attachments
        app.SYNC_STATE_FILE = packaged_root / ".torremolinos-sync.json"
        self.assertTrue(app.push_application_data())

        backed_up_paths = run_git(
            self.repository,
            "ls-tree",
            "-r",
            "--name-only",
            "origin/data-sync",
        ).stdout.splitlines()
        self.assertEqual(
            backed_up_paths,
            ["data/attachments/portatil.pdf", "data/torremolinos.sqlite3"],
        )
        self.assertFalse(any(path.startswith("dist/") for path in backed_up_paths))
        self.assertEqual(run_git(self.repository, "rev-parse", "main").stdout.strip(), main_before)

        mac_root = self.repository / "mac-install"
        mac_database = mac_root / "data" / "torremolinos.sqlite3"
        mac_attachments = mac_root / "data" / "attachments"
        init_db(mac_database)
        mac_attachments.mkdir(parents=True, exist_ok=True)
        (mac_attachments / "solo-local.pdf").write_bytes(b"no eliminar")
        app.BASE_DIR = mac_root
        app.DEFAULT_DB = mac_database
        app.ATTACHMENT_DIR = mac_attachments
        app.SYNC_STATE_FILE = mac_root / ".torremolinos-sync.json"

        (self.repository / "app.py").write_text("version = 2\n", encoding="utf-8")
        restored_attachments = app.pull_application_database()

        with connect(mac_database) as conn:
            restored = conn.execute(
                "SELECT COUNT(*) FROM properties WHERE house_number = 777"
            ).fetchone()[0]
        self.assertEqual(restored, 1)
        self.assertEqual(restored_attachments, 1)
        self.assertEqual(
            (mac_attachments / "portatil.pdf").read_bytes(),
            b"evidencia portable",
        )
        self.assertEqual(
            (mac_attachments / "solo-local.pdf").read_bytes(),
            b"no eliminar",
        )
        self.assertEqual((self.repository / "app.py").read_text(encoding="utf-8"), "version = 2\n")
        self.assertNotEqual((self.repository / "app.py").read_text(encoding="utf-8"), source_before)

    def test_pending_evidence_is_copied_to_onedrive(self):
        local_evidence = self.attachments / "pendiente.pdf"
        local_evidence.write_bytes(b"documento pendiente")
        with connect(self.database) as conn:
            concept_id = conn.execute("SELECT id FROM concepts LIMIT 1").fetchone()[0]
            movement_id = conn.execute(
                """
                INSERT INTO movements (movement_date, direction, concept_id, amount_cents)
                VALUES ('2026-09-10', 'INGRESO', ?, 100)
                """,
                (concept_id,),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO movement_attachments (
                    movement_id, original_name, stored_name, content_type,
                    file_size, local_path, remote_url
                ) VALUES (?, 'pendiente.pdf', 'pendiente.pdf', 'application/pdf', ?, ?, '')
                """,
                (movement_id, local_evidence.stat().st_size, "/Users/otro/OneDrive/pendiente.pdf"),
            )

        result = app.sync_pending_evidence_to_onedrive()

        self.assertEqual(result, {"cloud_synced": 0, "local_copied": 1, "pending": 1})
        destination = self.onedrive / "Torremolinos" / "Evidencias" / "pendiente.pdf"
        self.assertEqual(destination.read_bytes(), b"documento pendiente")
        with closing(sqlite3.connect(self.database)) as conn:
            remote_url, remote_provider = conn.execute(
                "SELECT remote_url, remote_provider FROM movement_attachments WHERE stored_name = 'pendiente.pdf'"
            ).fetchone()
        self.assertEqual(remote_url, str(destination))
        self.assertEqual(remote_provider, "onedrive_local")

        second_result = app.sync_pending_evidence_to_onedrive()
        self.assertEqual(second_result, {"cloud_synced": 0, "local_copied": 0, "pending": 1})
        with connect(self.database) as conn:
            stored_path = conn.execute(
                "SELECT local_path FROM movement_attachments WHERE stored_name = 'pendiente.pdf'"
            ).fetchone()[0]
            sync_logs = conn.execute(
                "SELECT COUNT(*) FROM movement_logs WHERE movement_id = ? AND action = 'SYNCED'",
                (movement_id,),
            ).fetchone()[0]
        self.assertEqual(stored_path, "data/attachments/pendiente.pdf")
        self.assertEqual(sync_logs, 1)

    def test_graph_upload_is_recorded_only_after_onedrive_confirmation(self):
        local_evidence = self.attachments / "confirmada.pdf"
        local_evidence.write_bytes(b"evidencia confirmada")
        with connect(self.database) as conn:
            concept_id = conn.execute("SELECT id FROM concepts LIMIT 1").fetchone()[0]
            movement_id = conn.execute(
                """
                INSERT INTO movements (movement_date, direction, concept_id, amount_cents)
                VALUES ('2026-09-10', 'EGRESO', ?, 100)
                """,
                (concept_id,),
            ).lastrowid
            attachment_id = conn.execute(
                """
                INSERT INTO movement_attachments (
                    movement_id, original_name, stored_name, content_type,
                    file_size, local_path
                ) VALUES (?, 'confirmada.pdf', 'confirmada.pdf', 'application/pdf', ?, ?)
                """,
                (movement_id, local_evidence.stat().st_size, r"C:\Users\otro\OneDrive\confirmada.pdf"),
            ).lastrowid

            confirmation = {
                "id": "onedrive-item-1",
                "web_url": "https://onedrive.live.com/item-1",
                "size": local_evidence.stat().st_size,
                "synced_at": "2026-09-11T12:00:00+00:00",
            }
            with patch.object(app, "upload_file_to_onedrive", return_value=confirmation) as upload:
                app.sync_attachment_to_onedrive_graph(conn, int(attachment_id))
                self.assertEqual(upload.call_args.args[1], local_evidence)

            stored = conn.execute(
                """
                SELECT remote_provider, remote_item_id, remote_synced_at, remote_url
                FROM movement_attachments WHERE id = ?
                """,
                (attachment_id,),
            ).fetchone()

        self.assertEqual(stored["remote_provider"], "onedrive_graph")
        self.assertEqual(stored["remote_item_id"], "onedrive-item-1")
        self.assertEqual(stored["remote_synced_at"], "2026-09-11T12:00:00+00:00")
        self.assertEqual(stored["remote_url"], "https://onedrive.live.com/item-1")


if __name__ == "__main__":
    unittest.main()
