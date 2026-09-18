import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from torremolinos.db import connect, init_db


class WhatsAppTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "whatsapp.sqlite3"
        init_db(self.database)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_seed_assigns_phones_by_house_and_only_enables_test_house(self):
        with connect(self.database) as conn:
            contacts = {
                row["house_number"]: (row["phone_number"], row["whatsapp_enabled"])
                for row in conn.execute(
                    "SELECT house_number, phone_number, whatsapp_enabled FROM properties"
                )
            }

        expected_phones = {
            1: "5223-2471",
            2: "",
            3: "",
            4: "",
            5: "5205-1136",
            6: "4211-3574",
            7: "5202-5954",
            8: "5841-0466",
            9: "4150-9075",
            10: "3211-5099",
            11: "5962-7770",
            12: "5514-1744",
            13: "5858-2517",
            14: "4568-2041",
            15: "5203-5100",
        }
        self.assertEqual(
            {house: phone for house, (phone, _) in contacts.items()}, expected_phones
        )
        self.assertEqual(
            [house for house, (_, enabled) in contacts.items() if enabled], [1]
        )

    def test_receipt_prepares_whatsapp_only_when_property_is_enabled(self):
        with connect(self.database) as conn:
            concept_id = conn.execute(
                "SELECT id FROM concepts WHERE direction = 'INGRESO' ORDER BY id LIMIT 1"
            ).fetchone()["id"]
            property_id = conn.execute(
                "SELECT id FROM properties WHERE house_number = 1"
            ).fetchone()["id"]
            movement_id = conn.execute(
                """
                INSERT INTO movements (
                    movement_date, direction, concept_id, property_id,
                    counterparty, amount_cents, period_month, period_year
                ) VALUES ('2026-09-17', 'INGRESO', ?, ?, 'Familia de prueba', 42500, 9, 2026)
                """,
                (concept_id, property_id),
            ).lastrowid
            receipt_id = app.create_receipt(conn, int(movement_id))
            enabled_page = app.render_receipt(conn, receipt_id)
            handler = object.__new__(app.TorremolinosHandler)
            with patch("app.open_url_in_firefox") as open_firefox:
                handler.open_receipt_whatsapp(conn, {"receipt_id": str(receipt_id)})
                opened_url = open_firefox.call_args.args[0]
            conn.execute(
                "UPDATE properties SET whatsapp_enabled = 0 WHERE id = ?", (property_id,)
            )
            disabled_page = app.render_receipt(conn, receipt_id)

        self.assertIn("Descargar PDF y abrir WhatsApp en Firefox", enabled_page)
        self.assertIn("prepareWhatsApp(this,", enabled_page)
        self.assertIn("fetch('/receipt/whatsapp'", enabled_page)
        self.assertIn("web.whatsapp.com/send?phone=50252232471", opened_url)
        self.assertNotIn("Descargar PDF y abrir WhatsApp en Firefox", disabled_page)

    def test_normalizes_supported_guatemalan_phone_formats(self):
        self.assertEqual(app.normalize_phone_number("5841 - 0466"), "5841-0466")
        self.assertEqual(app.normalize_phone_number("+502 5223 2471"), "5223-2471")
        with self.assertRaisesRegex(ValueError, "8 digitos"):
            app.normalize_phone_number("123")
        self.assertEqual(
            app.whatsapp_url("5223-2471", "Mensaje de prueba"),
            "https://web.whatsapp.com/send?phone=50252232471&text=Mensaje%20de%20prueba",
        )

    def test_migrates_existing_properties_without_overwriting_names(self):
        legacy_database = Path(self.temporary_directory.name) / "legacy.sqlite3"
        with sqlite3.connect(legacy_database) as conn:
            conn.executescript(
                """
                CREATE TABLE properties (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    house_number INTEGER NOT NULL UNIQUE,
                    owner_name TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO properties (house_number, owner_name)
                VALUES (1, 'Nombre actual'), (5, 'Otro nombre actual');
                """
            )

        init_db(legacy_database)

        with connect(legacy_database) as conn:
            rows = conn.execute(
                """
                SELECT house_number, owner_name, phone_number, whatsapp_enabled
                FROM properties ORDER BY house_number
                """
            ).fetchall()

        self.assertEqual(
            [tuple(row) for row in rows],
            [
                (1, "Nombre actual", "5223-2471", 1),
                (5, "Otro nombre actual", "5205-1136", 0),
            ],
        )


if __name__ == "__main__":
    unittest.main()
