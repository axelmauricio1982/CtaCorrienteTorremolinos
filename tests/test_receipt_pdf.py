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

    def test_salary_receipt_filename_identifies_fortnight_and_employee(self):
        base_receipt = {
            "receipt_month": 9,
            "period_month": 9,
            "period_year": 2026,
            "issued_date": "2026-09-16",
            "direction": "EGRESO",
            "frequency": "MENSUAL",
            "house_number": None,
            "receipt_no": "R-2026-0012",
            "concept_name": "Salario quincenal",
            "concept_text": "",
            "reference": "",
        }

        first_fortnight = {
            **base_receipt,
            "receiver_name": "Edwin López",
            "description": "Pago de portería. Primera quincena de septiembre 2026",
        }
        second_fortnight = {
            **base_receipt,
            "receiver_name": "Juan de la Cruz",
            "description": "Pago de portería. Segunda quincena de septiembre 2026",
        }

        self.assertEqual(
            app.receipt_pdf_filename(first_fortnight),
            "1erQuincenaSeptiembre2026_EdwinLópez.pdf",
        )
        self.assertEqual(
            app.receipt_pdf_filename(second_fortnight),
            "2daQuincenaSeptiembre2026_JuanDeLaCruz.pdf",
        )


if __name__ == "__main__":
    unittest.main()
