import io
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree

import pymupdf
import app
from torremolinos.db import connect, init_db
from torremolinos.payment_reports import payment_matrix, matrix_pdf, matrix_xlsx


class PaymentReportsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'db.sqlite3'
        init_db(self.path)
        self.conn = connect(self.path)
        self.addCleanup(self.conn.close)
        self.handler = object.__new__(app.TorremolinosHandler)
        self.concept = self.conn.execute("SELECT id FROM concepts WHERE name='Cuota ordinaria residencial'").fetchone()[0]

    def pay(self, house=14, month='9', year='2026', received='2026-10-09', concept=None):
        return self.handler.add_movement(self.conn, dict(property_id=str(house), concept_id=str(concept or self.concept), movement_date=received, period_month=month, period_year=year, amount='610'))

    def row(self, house=14, cutoff='2026-10-10', year=2026):
        return next(row for row in payment_matrix(self.conn, year, cutoff)['rows'] if row['house_number']==house)

    def test_late_payment_applies_to_september_not_october(self):
        self.pay()
        row = self.row()
        self.assertEqual(row['cells'][8]['status'], 'paid')
        self.assertEqual(row['cells'][9]['status'], 'pending')
        self.assertEqual(row['pending'], ['2026-10'])
        self.assertEqual(self.row(cutoff='2026-09-30')['cells'][8]['status'], 'pending')
        detail = app.report_detail_rows(self.conn, '2026-10-01', '2026-10-31')
        self.assertIn('Septiembre 2026', detail)
        self.assertIn('09/10/2026', detail)

    def test_initial_arrears_and_unknown_history_future_months(self):
        row = self.row(3)
        self.assertEqual(row['pending'], [f'2026-{month:02d}' for month in range(5,11)])
        self.assertEqual(row['cells'][3]['status'], 'outside')
        self.assertEqual(row['cells'][10]['status'], 'future')
        self.assertEqual(len(self.row(3, '2026-09-30')['pending']), 5)
        self.assertEqual(self.row(6)['pending'], ['2026-09', '2026-10'])
        self.assertEqual(self.row(6)['cells'][7]['status'], 'outside')
        self.pay(3, '5')
        self.assertEqual(len(self.row(3)['pending']), 5)

    def test_parking_deleted_zero_payments_do_not_cover_quota(self):
        other = self.conn.execute("INSERT INTO concepts (name,direction,frequency) VALUES ('Parqueo prueba','INGRESO','MENSUAL')").lastrowid
        self.pay(concept=other)
        self.assertEqual(self.row()['cells'][8]['status'], 'pending')
        rid = self.pay()
        movement_id = self.conn.execute('SELECT movement_id FROM receipts WHERE id=?',(rid,)).fetchone()[0]
        self.handler.delete_movement(self.conn, {'id':str(movement_id)})
        self.assertEqual(self.row()['cells'][8]['status'], 'pending')
        self.pay()
        self.conn.execute('UPDATE movements SET amount_cents=0 WHERE is_deleted=0')
        self.assertEqual(self.row()['cells'][8]['status'], 'pending')

    def test_receipt_correction_and_multiple_month_compatibility(self):
        rid=self.pay(month='10')
        self.handler.update_receipt(self.conn, {'receipt_id':str(rid),'receipt_month':'9'})
        self.assertEqual(self.row()['cells'][8]['status'], 'paid')
        self.assertEqual(self.row()['cells'][9]['status'], 'pending')
        self.conn.execute('DELETE FROM movement_periods')
        self.conn.execute('UPDATE movements SET period_month=10')
        self.assertEqual(self.row()['cells'][8]['status'], 'paid')
        self.handler.add_movement(self.conn, dict(property_id='1',concept_id=str(self.concept),movement_date='2026-10-10',period_months=['9','10'],period_year='2026',amount='1220'))
        self.assertEqual(self.row(1)['pending'], [])

    def test_exports_and_financial_pdf_include_period(self):
        self.pay()
        data = payment_matrix(self.conn,2026,'2026-10-10')
        with ZipFile(io.BytesIO(matrix_xlsx(data))) as archive:
            for name in archive.namelist():
                ElementTree.fromstring(archive.read(name))
            xml=archive.read('xl/worksheets/sheet1.xml').decode()
            self.assertIn('Septiembre', xml)
            self.assertIn('Pendiente', xml)
        with pymupdf.open(stream=matrix_pdf(data),filetype='pdf') as pdf:
            text=''.join(page.get_text() for page in pdf)
            self.assertIn('Pendiente',text)
            self.assertIn('Septiembre',text)
        content,_=app.build_report_pdf(self.conn,'2026-10-01','2026-10-31')
        with pymupdf.open(stream=content,filetype='pdf') as pdf:
            text=''.join(page.get_text() for page in pdf)
            self.assertIn('Mes pagado',text)
            self.assertIn('Septiembre 2026',text)

    def test_year_boundary_property_filter_and_idempotent_initialization(self):
        self.pay(month='12',received='2026-12-10')
        data=payment_matrix(self.conn,2027,'2027-01-10',14)
        self.assertEqual(len(data['rows']),1)
        self.assertEqual(data['rows'][0]['year_pending'],1)
        self.assertEqual(len(data['rows'][0]['pending']),4)  # September-November and January.
        self.conn.execute("UPDATE property_payment_baselines SET start_period='2026-04' WHERE property_id=3")
        self.conn.commit()
        init_db(self.path)
        self.assertEqual(self.row(3)['start_period'],'2026-04')

    def test_unassigned_payment_not_guessed_from_transaction_date(self):
        self.conn.execute("INSERT INTO movements (movement_date,direction,concept_id,property_id,amount_cents) VALUES ('2026-10-09','INGRESO',?,14,61000)",(self.concept,))
        data=payment_matrix(self.conn,2026,'2026-10-10')
        self.assertEqual(data['unassigned'],1)
        self.assertEqual(self.row()['cells'][9]['status'],'pending')
