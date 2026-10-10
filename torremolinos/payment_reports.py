"""Estado mensual de cuotas: separado de las fechas de caja y de los saldos."""
from datetime import date
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape

MONTH_NAMES = ('Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre')


def payment_matrix(conn, year, cutoff, property_id=None):
    if not 2000 <= year <= 2100:
        raise ValueError('El año debe estar entre 2000 y 2100.')
    cutoff_date = date.fromisoformat(cutoff)
    cutoff_period = cutoff_date.strftime('%Y-%m')
    start = conn.execute('SELECT start_period FROM payment_tracking_settings WHERE id=1').fetchone()['start_period']
    properties = conn.execute('''
        SELECT p.id, p.house_number, p.owner_name,
               COALESCE(b.start_period, ?) AS start_period, b.notes
        FROM properties p LEFT JOIN property_payment_baselines b ON b.property_id=p.id
        WHERE p.active=1 AND p.is_deleted=0 AND (? IS NULL OR p.id=?)
        ORDER BY p.house_number
    ''', (start, property_id, property_id)).fetchall()
    payments = conn.execute('''
        SELECT m.id, m.property_id, m.movement_date, r.receipt_no,
               COALESCE(mp.year, m.period_year, CAST(substr(m.movement_date,1,4) AS INTEGER)) AS year,
               COALESCE(mp.month, r.receipt_month, m.period_month) AS month
        FROM movements m JOIN concepts c ON c.id=m.concept_id
        LEFT JOIN receipts r ON r.movement_id=m.id AND r.is_deleted=0 AND r.active=1
        LEFT JOIN movement_periods mp ON mp.movement_id=m.id
        WHERE m.active=1 AND m.is_deleted=0 AND m.direction='INGRESO'
          AND m.amount_cents>0 AND c.name='Cuota ordinaria residencial'
          AND m.movement_date<=? AND m.property_id IS NOT NULL
    ''', (cutoff,)).fetchall()
    paid = {}
    unassigned = set()
    for payment in payments:
        if property_id is not None and payment['property_id'] != property_id:
            continue
        if payment['month'] is None:
            unassigned.add(payment['id'])
            continue
        key = (payment['property_id'], f"{payment['year']:04d}-{payment['month']:02d}")
        paid.setdefault(key, []).append(dict(payment))
    rows = []
    for prop in properties:
        cells = []
        for month in range(1, 13):
            period = f'{year:04d}-{month:02d}'
            matches = paid.get((prop['id'], period), [])
            status = 'paid' if matches else 'outside' if period < prop['start_period'] else 'future' if period > cutoff_period else 'pending'
            cells.append({'month': month, 'period': period, 'status': status, 'payments': matches})
        pending = []
        yy, mm = map(int, prop['start_period'].split('-'))
        while f'{yy:04d}-{mm:02d}' <= cutoff_period:
            period = f'{yy:04d}-{mm:02d}'
            if (prop['id'], period) not in paid:
                pending.append(period)
            yy, mm = (yy + 1, 1) if mm == 12 else (yy, mm + 1)
        rows.append({**dict(prop), 'cells': cells, 'pending': pending,
                     'year_pending': sum(cell['status']=='pending' for cell in cells)})
    return {'year': year, 'cutoff': cutoff, 'start': start, 'rows': rows, 'unassigned': len(unassigned)}


STATUS_LABELS = {'paid': 'Pagado', 'pending': 'Pendiente', 'future': 'Por vencer', 'outside': 'Sin historial'}


def matrix_export_rows(matrix):
    rows = [['Casa', 'Propietario', *MONTH_NAMES, 'Pendientes del año', 'Pendientes acumulados al corte']]
    for row in matrix['rows']:
        rows.append([row['house_number'], row['owner_name'],
                     *[STATUS_LABELS[cell['status']] for cell in row['cells']],
                     row['year_pending'], len(row['pending'])])
    return rows


def matrix_xlsx(matrix):
    rows = [['Cuotas por casa', matrix['year']], ['Fecha de corte', matrix['cutoff']],
            ['Inicio de registro', matrix['start']],
            ['Pagado: cuota con pago registrado; no es una conciliación de importes.'],
            *matrix_export_rows(matrix)]
    for row in matrix['rows']:
        if row['notes']:
            rows.append([f"Antecedente casa {row['house_number']}", row['notes']])
    def column(number):
        result = ''
        while number:
            number, rest = divmod(number - 1, 26)
            result = chr(65 + rest) + result
        return result
    xml_rows = []
    for index, row in enumerate(rows, 1):
        cells = []
        for col, value in enumerate(row, 1):
            ref = f'{column(col)}{index}'
            if isinstance(value, int):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>')
        xml_rows.append(f'<row r="{index}">{"".join(cells)}</row>')
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>''')
        archive.writestr('_rels/.rels', '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
        archive.writestr('xl/workbook.xml', '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Cuotas por casa" sheetId="1" r:id="rId1"/></sheets></workbook>''')
        archive.writestr('xl/_rels/workbook.xml.rels', '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''')
        archive.writestr('xl/worksheets/sheet1.xml', f'''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane xSplit="2" ySplit="5" topLeftCell="C6" activePane="bottomRight" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="8" customWidth="1"/><col min="2" max="2" width="35" customWidth="1"/><col min="3" max="16" width="16" customWidth="1"/></cols><sheetData>{''.join(xml_rows)}</sheetData><autoFilter ref="A5:P{5+len(matrix['rows'])}"/></worksheet>''')
    return output.getvalue()


def matrix_pdf(matrix):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    output = BytesIO()
    styles = getSampleStyleSheet()
    small = styles['BodyText'].clone('matrix-small')
    small.fontSize, small.leading = 7, 9
    table_rows = [[Paragraph(escape(str(value)), small) for value in row] for row in matrix_export_rows(matrix)]
    table = Table(table_rows, colWidths=[32, 133] + [62]*12 + [85, 125], repeatRows=1)
    commands = [('BACKGROUND', (0,0), (-1,0), colors.HexColor('#eef3f1')), ('GRID', (0,0), (-1,-1), .3, colors.HexColor('#d9e2de')), ('VALIGN', (0,0), (-1,-1), 'TOP')]
    for index, row in enumerate(matrix['rows'], 1):
        for month, cell in enumerate(row['cells'], 2):
            color = {'paid':'#e3f3e9','pending':'#fbe4e4','future':'#f5f5f5','outside':'#f5f5f5'}[cell['status']]
            commands.append(('BACKGROUND',(month,index),(month,index),colors.HexColor(color)))
    table.setStyle(TableStyle(commands))
    story = [Paragraph(f"Cuotas por casa — {matrix['year']}", styles['Title']),
             Paragraph(f"Corte: {matrix['cutoff']}. Inicio del registro: {matrix['start']}. Pagado: cuota con pago registrado, no conciliación de importes. Los pendientes incluyen el mes del corte.", styles['BodyText']), Spacer(1,12), table]
    for row in matrix['rows']:
        if row['notes']:
            story.extend([Spacer(1,10), Paragraph(escape(f"Casa {row['house_number']}: {row['notes']}"), styles['BodyText'])])
    SimpleDocTemplate(output, pagesize=landscape(A3), leftMargin=25, rightMargin=25).build(story)
    return output.getvalue()
