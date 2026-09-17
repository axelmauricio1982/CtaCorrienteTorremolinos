import tempfile
import unittest
from pathlib import Path

import fitz

import app
from torremolinos.db import connect, init_db


class ReceiptPdfTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "receipt.sqlite3"
        init_db(self.database)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_printable_and_downloadable_receipts_share_content_and_watermark(self):
        with connect(self.database) as conn:
            concept = conn.execute(
                """
                SELECT id FROM concepts
                WHERE direction = 'INGRESO' AND frequency = 'MENSUAL'
                ORDER BY id LIMIT 1
                """
            ).fetchone()
            property_row = conn.execute(
                "SELECT id FROM properties ORDER BY id LIMIT 1"
            ).fetchone()
            movement_id = conn.execute(
                """
                INSERT INTO movements (
                    movement_date, direction, concept_id, property_id,
                    counterparty, amount_cents, period_month, period_year,
                    payment_method, reference, description
                ) VALUES (?, 'INGRESO', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-09-16",
                    concept["id"],
                    property_row["id"],
                    "Contribuyente de prueba",
                    42500,
                    9,
                    2026,
                    "Transferencia",
                    "PRUEBA-001",
                    "Cuota de mantenimiento",
                ),
            ).lastrowid
            receipt_id = app.create_receipt(conn, int(movement_id))

        with connect(self.database) as conn:
            printable = app.render_receipt(conn, receipt_id)
            pdf_bytes, filename = app.build_receipt_pdf(conn, receipt_id)

        self.assertIn('class="receipt-watermark"', printable)
        self.assertIn("CANCELADO", printable)
        self.assertIn("PAGO REALIZADO", printable)
        self.assertTrue(filename.endswith(".pdf"))

        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            self.assertEqual(document.page_count, 1)
            text = document[0].get_text()
        finally:
            document.close()

        for expected in (
            "RESIDENCIAL TORREMOLINOS",
            "Recibo de ingreso",
            "CANCELADO",
            "PAGO REALIZADO",
            "Casa 1 - Axel Hernandez",
            "Q 425.00",
            "PRUEBA-001",
        ):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
