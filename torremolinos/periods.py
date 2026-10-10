"""Períodos cubiertos por un movimiento, sin duplicar su importe."""
from datetime import date


def parse_periods(data):
    raw = data.get('period_months', data.get('period_month', ''))
    values = raw if isinstance(raw, list) else [raw]
    try:
        months = sorted({int(value) for value in values if value not in ('', None)})
        year = int(data.get('period_year') or date.today().year)
    except (TypeError, ValueError):
        raise ValueError('Seleccione meses y año válidos.')
    if any(month < 1 or month > 12 for month in months) or not 2000 <= year <= 2100:
        raise ValueError('Seleccione meses y año válidos (2000 a 2100).')
    return months, year


def movement_months(conn, movement):
    rows = conn.execute('SELECT month FROM movement_periods WHERE movement_id = ? ORDER BY month', (movement['id'],)).fetchall()
    if rows:
        return [row['month'] for row in rows]
    receipt = conn.execute('SELECT receipt_month FROM receipts WHERE movement_id=? AND active=1 AND is_deleted=0', (movement['id'],)).fetchone()
    month = (receipt['receipt_month'] if receipt else None) or movement['period_month']
    return [month] if month else []


def save_periods(conn, movement_id, months, year):
    conn.execute('DELETE FROM movement_periods WHERE movement_id = ?', (movement_id,))
    conn.executemany('INSERT INTO movement_periods (movement_id, year, month) VALUES (?, ?, ?)', [(movement_id, year, month) for month in months])


def next_periods(conn):
    # Legacy receipt corrections take precedence over the original single month.
    rows = conn.execute('''
        SELECT m.property_id, m.concept_id,
               COALESCE(mp.year, m.period_year, CAST(substr(m.movement_date,1,4) AS INTEGER)) AS year,
               COALESCE(mp.month, r.receipt_month, m.period_month) AS month
        FROM movements m JOIN concepts c ON c.id=m.concept_id
        LEFT JOIN movement_periods mp ON mp.movement_id=m.id
        LEFT JOIN receipts r ON r.movement_id=m.id AND r.is_deleted=0 AND r.active=1
        WHERE m.active=1 AND m.is_deleted=0 AND m.direction='INGRESO'
          AND m.property_id IS NOT NULL AND c.frequency='MENSUAL'
    ''').fetchall()
    latest = {}
    for row in rows:
        if not row['month']:
            continue
        key = f"{row['property_id']}:{row['concept_id']}"
        latest[key] = max(latest.get(key, (0, 0)), (row['year'], row['month']))
    return {key: {'year': year + (month == 12), 'month': month % 12 + 1}
            for key, (year, month) in latest.items()}
