import io
import tempfile
import unittest
from pathlib import Path

import pymupdf
import app
from torremolinos.db import connect, init_db
from torremolinos.periods import next_periods, parse_periods, movement_months


class PeriodTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.sqlite3'
        init_db(self.path)
        self.conn = connect(self.path)
        self.addCleanup(self.conn.close)
        self.handler = object.__new__(app.TorremolinosHandler)
        self.concept = self.conn.execute("SELECT id FROM concepts WHERE direction='INGRESO' AND frequency='MENSUAL' ORDER BY id LIMIT 1").fetchone()['id']

    def add(self, months, **overrides):
        data = dict(concept_id=str(self.concept), property_id='14', movement_date='2026-10-10', period_months=months, period_year='2026', amount='1423.34')
        data.update(overrides)
        receipt_id = self.handler.add_movement(self.conn, data)
        movement = self.conn.execute('SELECT m.* FROM movements m JOIN receipts r ON r.movement_id=m.id WHERE r.id=?', (receipt_id,)).fetchone()
        return receipt_id, movement

    def test_multiple_months_single_total_and_receipt_in_html_pdf(self):
        rid, movement = self.add(['9', '10', '9'])
        self.assertEqual(movement['amount_cents'], 142334)
        self.assertEqual(movement_months(self.conn, movement), [9, 10])
        self.assertEqual(self.conn.execute('SELECT count(*) FROM receipts').fetchone()[0], 1)
        self.assertIn('Meses de Septiembre, Octubre Año 2026', app.render_receipt(self.conn, rid))
        content, filename = app.build_receipt_pdf(self.conn, rid)
        with pymupdf.open(stream=content, filetype='pdf') as pdf:
            self.assertIn('Meses de Septiembre, Octubre Año 2026', ''.join(p.get_text() for p in pdf))
        self.assertIn('septiembre-octubre2026', filename.lower())
        self.assertEqual(next_periods(self.conn)['14:' + str(self.concept)], {'year': 2026, 'month': 11})

    def test_blank_amount_multiplies_rate_but_explicit_total_does_not(self):
        _, movement = self.add(['9', '10'], amount='')
        rate = app.current_rate(self.conn, self.concept, None, '2026-10-10')
        self.assertEqual(movement['amount_cents'], rate['amount_cents'] * 2)

    def test_suggestion_handles_year_boundary_and_deleted_payments(self):
        _, old = self.add(['8'])
        rid, newest = self.add(['12'])
        self.assertEqual(next_periods(self.conn)['14:' + str(self.concept)], {'year': 2027, 'month': 1})
        self.handler.delete_movement(self.conn, {'id': str(newest['id'])})
        self.assertEqual(next_periods(self.conn)['14:' + str(self.concept)], {'year': 2026, 'month': 9})
        self.assertNotIn('1:' + str(self.concept), next_periods(self.conn))

    def test_legacy_corrected_receipt_and_new_correction(self):
        rid, movement = self.add(['10'])
        self.conn.execute('DELETE FROM movement_periods')
        self.conn.execute('UPDATE receipts SET receipt_month=9 WHERE id=?', (rid,))
        self.assertEqual(next_periods(self.conn)['14:' + str(self.concept)]['month'], 10)
        self.handler.update_receipt(self.conn, {'receipt_id': str(rid), 'receipt_month': '8'})
        changed = self.conn.execute('SELECT * FROM movements WHERE id=?', (movement['id'],)).fetchone()
        self.assertEqual(changed['period_month'], 8)
        self.assertEqual(movement_months(self.conn, changed), [8])
        self.assertEqual(next_periods(self.conn)['14:' + str(self.concept)]['month'], 9)

    def test_edit_replaces_periods_without_duplicate_receipt(self):
        rid, movement = self.add(['9', '10'])
        with self.assertRaises(ValueError):
            self.handler.update_receipt(self.conn, {'receipt_id': str(rid), 'receipt_month': '8'})
        result = self.handler.update_movement(self.conn, dict(id=str(movement['id']), concept_id=str(self.concept), property_id='14', movement_date='2026-10-10', amount='711.67', period_months=['8'], period_year='2026'))
        self.assertEqual(result, rid)
        self.assertEqual(movement_months(self.conn, movement), [8])
        self.assertIn('Mes de Agosto Año 2026', app.render_receipt(self.conn, rid))

    def test_validation_and_repeated_form_fields(self):
        for months in [['0'], ['13'], ['x']]:
            with self.assertRaises(ValueError):
                parse_periods({'period_months': months, 'period_year': '2026'})
        raw = b'--test\r\nContent-Disposition: form-data; name="period_months"\r\n\r\n9\r\n--test\r\nContent-Disposition: form-data; name="period_months"\r\n\r\n10\r\n--test--\r\n'
        self.assertEqual(app.parse_multipart_form_data(raw, 'multipart/form-data; boundary=test')['period_months'], ['9', '10'])
        encoded = b'period_months=9&period_months=10'
        self.handler.headers = {'Content-Length': str(len(encoded)), 'Content-Type': 'application/x-www-form-urlencoded'}
        self.handler.rfile = io.BytesIO(encoded)
        self.assertEqual(self.handler.read_form()['period_months'], ['9', '10'])

    def test_schema_initialization_preserves_existing_periods(self):
        _, movement = self.add(['9', '10'])
        self.conn.commit()
        init_db(self.path)
        self.assertEqual(movement_months(self.conn, movement), [9, 10])
        self.assertIn('name="period_month"', app.render_movements(self.conn, {}))
        self.assertNotIn('name="period_months" multiple', app.render_movements(self.conn, {}))
        self.assertIn('<option value="1" selected>Ingreso - Cuota ordinaria residencial</option>', app.render_movements(self.conn, {}))
        self.assertNotIn('None\n', app.notice({}))
