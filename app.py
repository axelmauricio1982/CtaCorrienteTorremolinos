from __future__ import annotations

import argparse
import csv
import html
import io
import mimetypes
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta
from email.parser import BytesParser
from email.policy import default as email_default
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from torremolinos.db import connect, init_db


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = BASE_DIR / "data" / "torremolinos.sqlite3"
APP_NAME = "Residencial Torremolinos"
CURRENT_USER = "ADM"
PAGE_SIZE = 10
ATTACHMENT_DIR = BASE_DIR / "data" / "attachments"
ALLOWED_ATTACHMENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "application/pdf",
}
ALLOWED_ATTACHMENT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}

MONTHS = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}

TABLE_SORT_SCRIPT = """
<script>
(function () {
  function cellValue(cell) {
    var text = (cell ? cell.textContent : '').trim();
    var dateMatch = text.match(/^(\\d{2})\\/(\\d{2})\\/(\\d{4})$/);
    if (dateMatch) {
      return { type: 'number', value: Date.UTC(Number(dateMatch[3]), Number(dateMatch[2]) - 1, Number(dateMatch[1])) };
    }
    var numeric = text.replace(/[^\\d.-]/g, '');
    if (numeric && /^-?\\d+(?:\\.\\d+)?$/.test(numeric)) {
      return { type: 'number', value: Number(numeric) };
    }
    return { type: 'text', value: text.toLocaleLowerCase('es') };
  }

  document.querySelectorAll('.table-wrap table').forEach(function (table) {
    var headers = table.querySelectorAll('thead th');
    var body = table.tBodies[0];
    if (!body) return;

    headers.forEach(function (header, columnIndex) {
      header.classList.add('sortable-header');
      header.setAttribute('role', 'button');
      header.setAttribute('tabindex', '0');
      header.setAttribute('title', 'Ordenar ASC/DESC');

      function sortRows() {
        var direction = header.dataset.sortDirection === 'asc' ? 'desc' : 'asc';
        headers.forEach(function (other) {
          delete other.dataset.sortDirection;
          other.removeAttribute('aria-sort');
        });
        header.dataset.sortDirection = direction;
        header.setAttribute('aria-sort', direction === 'asc' ? 'ascending' : 'descending');

        Array.from(body.rows).sort(function (left, right) {
          var a = cellValue(left.cells[columnIndex]);
          var b = cellValue(right.cells[columnIndex]);
          var result;
          if (a.type === 'number' && b.type === 'number') {
            result = a.value - b.value;
          } else {
            result = a.value.localeCompare(b.value, 'es', { numeric: true, sensitivity: 'base' });
          }
          return direction === 'asc' ? result : -result;
        }).forEach(function (row) {
          body.appendChild(row);
        });
      }

      header.addEventListener('click', sortRows);
      header.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          sortRows();
        }
      });
    });
  });
})();
</script>
"""


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def esc_text(value: object) -> str:
  escaped = esc(value)
  return re.sub(r"(?<!Res)\.(?=\s|$)", ".<br>", escaped)


def parse_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    return int(value)


def parse_money(value: str | None) -> int:
    if value is None or value.strip() == "":
        raise ValueError("El monto es obligatorio cuando no existe una vigencia aplicable.")
    cleaned = value.strip().replace("Q", "").replace(",", "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("El monto no tiene un formato valido.") from exc
    if amount < 0:
        raise ValueError("El monto no puede ser negativo.")
    cents = (amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def format_money(cents: int | None) -> str:
    cents = cents or 0
    return f"Q {Decimal(cents) / Decimal(100):,.2f}"


def format_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return value
    return f"{parsed.day:02d}/{parsed.month:02d}/{parsed.year}"


def period_label(month: int | None, year: int | None) -> str:
    if month and year:
        return f"{MONTHS.get(month, month)} {year}"
    if year:
        return str(year)
    return ""


def receipt_pdf_filename(receipt) -> str:
    month = MONTHS[receipt["receipt_month"] or receipt["period_month"] or int(receipt["issued_date"][5:7])]
    year = receipt["period_year"] or int(receipt["issued_date"][:4])
    month_year = f"{month}{year}"
    if receipt["direction"] == "INGRESO" and receipt["frequency"] == "MENSUAL":
        house_number = receipt["house_number"]
        house_suffix = f"_CasaNo_{house_number}" if house_number else ""
        base_name = f"{receipt['receipt_no']}{house_suffix}_{month_year}"
    else:
        concept = unicodedata.normalize("NFKD", receipt["concept_name"] or "")
        concept = "".join(char for char in concept if not unicodedata.combining(char))
        concept = re.sub(r"[^a-zA-Z0-9]+", "_", concept).strip("_").lower()
        base_name = f"{concept or 'servicio'}_pagado_{month_year}"
    return f"{base_name}.pdf"


def receipt_concept_text(movement) -> str:
    concept_name = str(movement["concept_name"] or "").strip()
    normalized_name = concept_name.casefold()
    annual_concepts = {
        "vacaciones": "Pago de vacaciones.",
        "bono 14": "Pago de Bono 14.",
        "aguinaldo": "Pago de Aguinaldo.",
    }
    if movement["frequency"] == "ANUAL":
      return annual_concepts.get(
        normalized_name,
        f"Pago anual de {concept_name}.",
      )

    if movement["direction"] == "INGRESO":
      property_notes = str(movement["property_notes"] or "").strip()
      return property_notes or "Pago de mantenimiento y seguridad."

    description = str(movement["description"] or "").strip()
    return description or concept_name


def amount_to_words(cents: int) -> str:
    quetzales = cents // 100
    centavos = cents % 100
    words = number_to_words(quetzales)
    suffix = "quetzal" if quetzales == 1 else "quetzales"
    return f"{words.capitalize()} {suffix} con {centavos:02d}/100"


def number_to_words(number: int) -> str:
    if number == 0:
        return "cero"
    if number < 0:
        return "menos " + number_to_words(abs(number))
    if number < 1000:
        return words_under_1000(number)
    if number < 1_000_000:
        thousands = number // 1000
        rest = number % 1000
        prefix = "mil" if thousands == 1 else f"{number_to_words(thousands)} mil"
        return prefix if rest == 0 else f"{prefix} {number_to_words(rest)}"
    if number < 1_000_000_000:
        millions = number // 1_000_000
        rest = number % 1_000_000
        prefix = "un millon" if millions == 1 else f"{number_to_words(millions)} millones"
        return prefix if rest == 0 else f"{prefix} {number_to_words(rest)}"
    return str(number)


def words_under_1000(number: int) -> str:
    units = {
        0: "",
        1: "uno",
        2: "dos",
        3: "tres",
        4: "cuatro",
        5: "cinco",
        6: "seis",
        7: "siete",
        8: "ocho",
        9: "nueve",
        10: "diez",
        11: "once",
        12: "doce",
        13: "trece",
        14: "catorce",
        15: "quince",
        16: "dieciseis",
        17: "diecisiete",
        18: "dieciocho",
        19: "diecinueve",
        20: "veinte",
        21: "veintiuno",
        22: "veintidos",
        23: "veintitres",
        24: "veinticuatro",
        25: "veinticinco",
        26: "veintiseis",
        27: "veintisiete",
        28: "veintiocho",
        29: "veintinueve",
    }
    tens = {
        30: "treinta",
        40: "cuarenta",
        50: "cincuenta",
        60: "sesenta",
        70: "setenta",
        80: "ochenta",
        90: "noventa",
    }
    hundreds = {
        100: "cien",
        200: "doscientos",
        300: "trescientos",
        400: "cuatrocientos",
        500: "quinientos",
        600: "seiscientos",
        700: "setecientos",
        800: "ochocientos",
        900: "novecientos",
    }
    if number < 30:
        return units[number]
    if number < 100:
        ten = number // 10 * 10
        unit = number % 10
        return tens[ten] if unit == 0 else f"{tens[ten]} y {units[unit]}"
    if number in hundreds:
        return hundreds[number]
    hundred = number // 100 * 100
    rest = number % 100
    prefix = "ciento" if hundred == 100 else hundreds[hundred]
    return f"{prefix} {words_under_1000(rest)}"


def page(title: str, body: str, active: str = "/") -> str:
    nav_items = [
        ("/", "Inicio"),
        ("/properties", "Propiedades"),
        ("/employees", "Empleados"),
        ("/concepts", "Conceptos"),
        ("/movements", "Movimientos"),
        ("/accounts", "Cuenta corriente"),
        ("/reports", "Reportes"),
        ("/cash-settings", "Saldo inicial"),
        ("/cashflow", "Flujo de caja"),
        ("/receipts", "Recibos"),
    ]
    nav = "".join(
        f'<a class="{"active" if href == active else ""}" href="{href}">{label}</a>'
        for href, label in nav_items
    )
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} - {APP_NAME}</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body>
  <header class="topbar">
    <div>
      <p class="eyebrow">Administracion</p>
      <h1>{APP_NAME}</h1>
    </div>
    <nav>{nav}</nav>
  </header>
  <main class="shell">{body}</main>
  {TABLE_SORT_SCRIPT}
</body>
</html>"""


def notice(query: dict[str, list[str]]) -> str:
    if "ok" not in query:
        return ""
    return '<div class="notice">Operacion registrada correctamente.</div>'


def selected_attr(value: object, current: object) -> str:
    return " selected" if str(value) == str(current) else ""


def add_movement_log(conn, movement_id: int, action: str, details: str, created_by: str = CURRENT_USER) -> None:
    conn.execute(
        """
        INSERT INTO movement_logs (movement_id, action, details, created_by)
        VALUES (?, ?, ?, ?)
        """,
        (movement_id, action, details, created_by),
    )


def save_movement_attachment(conn, movement_id: int, uploaded_file, created_by: str = CURRENT_USER):
    if uploaded_file is None or not getattr(uploaded_file, "filename", None):
        return None

    filename = Path(getattr(uploaded_file, "filename", "document")).name
    if not filename:
        raise ValueError("El archivo adjunto no tiene nombre valido.")

    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise ValueError("Formato no permitido. Usa JPG, JPEG, PNG, WEBP o PDF.")

    content_type = getattr(uploaded_file, "type", "") or mimetypes.guess_type(filename)[0] or ""
    if content_type and content_type.lower() not in {value.lower() for value in ALLOWED_ATTACHMENT_TYPES}:
        raise ValueError("El tipo de archivo no es valido para evidencia documental.")

    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{movement_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}{suffix}"
    local_path = ATTACHMENT_DIR / stored_name

    content = uploaded_file.file.read()
    if not content:
        raise ValueError("El archivo adjunto no tiene contenido.")
    local_path.write_bytes(content)

    cursor = conn.execute(
        """
        INSERT INTO movement_attachments (
            movement_id,
            original_name,
            stored_name,
            content_type,
            file_size,
            local_path,
            created_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            movement_id,
            filename,
            stored_name,
            content_type,
            len(content),
            str(local_path),
            created_by,
        ),
    )
    add_movement_log(conn, movement_id, "ATTACHMENT_ADDED", f"Adjunto '{filename}' guardado como evidencia.", created_by)
    return cursor.lastrowid


class UploadedFile:
    def __init__(self, filename: str, content_type: str, data: bytes):
        self.filename = filename
        self.type = content_type
        self.file = io.BytesIO(data)


def parse_multipart_form_data(raw: bytes, content_type: str) -> dict[str, object]:
    match = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type, re.IGNORECASE)
    if not match:
        raise ValueError("No se pudo identificar el boundary del formulario multipart.")
    boundary = (match.group(1) or match.group(2)).strip()
    boundary_bytes = b"--" + boundary.encode("utf-8")
    parts = raw.split(boundary_bytes)
    result: dict[str, object] = {}

    for part in parts[1:-1]:
        part = part.lstrip(b"\r\n")
        if not part:
            continue
        if part.startswith(b"--"):
            continue
        if b"\r\n\r\n" not in part:
            continue
        header_block, value = part.split(b"\r\n\r\n", 1)
        headers = BytesParser(policy=email_default).parsebytes(header_block + b"\r\n")
        disposition = headers.get("Content-Disposition", "")
        name_match = re.search(r'name="([^"]+)"', disposition)
        if not name_match:
            continue
        name = name_match.group(1)
        filename = ""
        file_match = re.search(r'filename="([^"]*)"', disposition)
        if file_match:
            filename = file_match.group(1)
        value = value.rstrip(b"\r\n")
        if filename:
            result[name] = UploadedFile(
                filename=filename,
                content_type=headers.get("Content-Type", "application/octet-stream"),
                data=value,
            )
        else:
            result[name] = value.decode("utf-8", errors="replace")
    return result


def checked_attr(condition: object) -> str:
    return " checked" if bool(condition) else ""


def active_options(current: int | str | None) -> str:
    return (
        f'<option value="1"{selected_attr(1, current)}>Activo</option>'
        f'<option value="0"{selected_attr(0, current)}>Inactivo</option>'
    )


def money_input(cents: int | None) -> str:
    cents = cents or 0
    return f"{Decimal(cents) / Decimal(100):.2f}"


def parse_page(query: dict[str, list[str]], key: str = "page") -> int:
    try:
        return max(1, int(query.get(key, ["1"])[0]))
    except (TypeError, ValueError):
        return 1


def pagination(path: str, page: int, total: int, key: str = "page") -> str:
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if total_pages == 1:
        return ""
    previous_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)
    previous_disabled = " disabled" if page <= 1 else ""
    next_disabled = " disabled" if page >= total_pages else ""
    previous_href = f"{path}?{urlencode({key: previous_page})}"
    next_href = f"{path}?{urlencode({key: next_page})}"
    return f"""
    <div class="pagination">
      <a class="button small{previous_disabled}" href="{previous_href}">Anterior</a>
      <span>Pagina {page} de {total_pages}</span>
      <a class="button small{next_disabled}" href="{next_href}">Siguiente</a>
    </div>
    """


def status_badge(active: int, is_deleted: int = 0) -> str:
    if is_deleted:
        return '<span class="badge deleted">Eliminado</span>'
    if active:
        return '<span class="badge active-status">Activo</span>'
    return '<span class="badge inactive-status">Inactivo</span>'


def error_page(message: str, status: int = 400) -> tuple[str, int]:
    content = f"""
    <section class="panel narrow">
      <h2>No se pudo completar</h2>
      <p>{esc(message)}</p>
      <p><a class="button" href="javascript:history.back()">Volver</a></p>
    </section>
    """
    return page("Error", content), status


def row_value(row, key: str, default: str = ""):
    return row[key] if key in row.keys() else default


def current_rate(conn, concept_id: int, employee_id: int | None, as_of: str):
    params = [concept_id, as_of, as_of]
    employee_filter = "employee_id IS NULL"
    if employee_id:
        employee_filter = "(employee_id = ? OR employee_id IS NULL)"
        params = [concept_id, employee_id, as_of, as_of]
    return conn.execute(
        f"""
        SELECT *
        FROM concept_rates
        WHERE concept_id = ?
          AND {employee_filter}
          AND valid_from <= ?
          AND (valid_to IS NULL OR valid_to >= ?)
          AND active = 1
          AND is_deleted = 0
        ORDER BY employee_id IS NULL, valid_from DESC
        LIMIT 1
        """,
        params,
    ).fetchone()


def close_previous_rate(conn, concept_id: int, employee_id: int | None, valid_from: str) -> None:
    if employee_id:
        conn.execute(
            """
            UPDATE concept_rates
            SET valid_to = date(?, '-1 day'),
                updated_at = CURRENT_TIMESTAMP,
                updated_by = ?
            WHERE concept_id = ?
              AND employee_id = ?
              AND valid_to IS NULL
              AND valid_from < ?
              AND is_deleted = 0
            """,
            (valid_from, CURRENT_USER, concept_id, employee_id, valid_from),
        )
    else:
        conn.execute(
            """
            UPDATE concept_rates
            SET valid_to = date(?, '-1 day'),
                updated_at = CURRENT_TIMESTAMP,
                updated_by = ?
            WHERE concept_id = ?
              AND employee_id IS NULL
              AND valid_to IS NULL
              AND valid_from < ?
              AND is_deleted = 0
            """,
            (valid_from, CURRENT_USER, concept_id, valid_from),
        )


def get_cash_settings(conn):
    row = conn.execute("SELECT * FROM cash_settings WHERE id = 1").fetchone()
    if row:
        return row
    conn.execute(
        """
        INSERT INTO cash_settings (id, opening_balance_cents, opening_balance_date, notes)
        VALUES (1, 0, ?, 'Saldo inicial de ahorros disponible.')
        """,
        (date.today().isoformat(),),
    )
    return conn.execute("SELECT * FROM cash_settings WHERE id = 1").fetchone()


def net_movements(conn, start: str | None = None, end: str | None = None) -> int:
    filters = ["is_deleted = 0"]
    params: list[str] = []
    if start:
        filters.append("movement_date >= ?")
        params.append(start)
    if end:
        filters.append("movement_date <= ?")
        params.append(end)
    where = " AND ".join(filters)
    return conn.execute(
        f"""
        SELECT COALESCE(SUM(CASE WHEN direction = 'INGRESO' THEN amount_cents ELSE -amount_cents END), 0)
        FROM movements
        WHERE {where}
        """,
        params,
    ).fetchone()[0]


def cash_balance(conn, as_of: str | None = None) -> int:
    settings = get_cash_settings(conn)
    opening_date = settings["opening_balance_date"]
    if as_of and as_of < opening_date:
        return 0
    return settings["opening_balance_cents"] + net_movements(
        conn,
        start=opening_date,
        end=as_of,
    )


def create_receipt(conn, movement_id: int) -> int:
    movement = conn.execute(
        f"""
        SELECT
            m.*,
            c.name AS concept_name,
            c.frequency AS frequency,
            p.owner_name,
            p.house_number,
            p.notes AS property_notes,
            e.name AS employee_name
        FROM movements m
        JOIN concepts c ON c.id = m.concept_id
        LEFT JOIN properties p ON p.id = m.property_id
        LEFT JOIN employees e ON e.id = m.employee_id
        WHERE m.id = ?
        """,
        (movement_id,),
    ).fetchone()
    if not movement:
        raise ValueError("Movimiento no encontrado.")

    year = int(movement["movement_date"][:4])
    next_sequence = conn.execute(
        "SELECT COALESCE(MAX(sequence), 0) + 1 FROM receipts WHERE year = ?",
        (year,),
    ).fetchone()[0]
    receipt_no = f"R-{year}-{next_sequence:04d}"
    receipt_month = movement["period_month"] or int(movement["movement_date"][5:7])
    concept_text = receipt_concept_text(movement)

    if movement["direction"] == "INGRESO":
        payer_name = movement["owner_name"] or movement["counterparty"] or "Pendiente"
        if movement["house_number"]:
            payer_name = f"Casa {movement['house_number']} - {payer_name}"
        receiver_name = "Administracion Residencial Torremolinos"
    else:
        payer_name = "Administracion Residencial Torremolinos"
        receiver_name = movement["employee_name"] or movement["counterparty"] or "Pendiente"

    cursor = conn.execute(
        """
        INSERT INTO receipts (
            movement_id,
            year,
            sequence,
            receipt_no,
            issued_date,
            direction,
            receipt_month,
            payer_name,
            receiver_name,
            amount_words,
            concept_text,
            updated_at,
            created_by,
            updated_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
        """,
        (
            movement_id,
            year,
            next_sequence,
            receipt_no,
            movement["movement_date"],
            movement["direction"],
            receipt_month,
            payer_name,
            receiver_name,
            amount_to_words(movement["amount_cents"]),
            concept_text,
            CURRENT_USER,
            CURRENT_USER,
        ),
    )
    return int(cursor.lastrowid)


def render_dashboard(conn, query) -> str:
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    today_iso = today.isoformat()
    settings = get_cash_settings(conn)
    props = conn.execute("SELECT COUNT(*) FROM properties WHERE active = 1 AND is_deleted = 0").fetchone()[0]
    employees = conn.execute("SELECT COUNT(*) FROM employees WHERE active = 1 AND is_deleted = 0").fetchone()[0]
    income_month = conn.execute(
        """
        SELECT COALESCE(SUM(amount_cents), 0)
        FROM movements
        WHERE direction = 'INGRESO'
          AND movement_date BETWEEN ? AND ?
          AND is_deleted = 0
        """,
        (month_start, today_iso),
    ).fetchone()[0]
    expense_month = conn.execute(
        """
        SELECT COALESCE(SUM(amount_cents), 0)
        FROM movements
        WHERE direction = 'EGRESO'
          AND movement_date BETWEEN ? AND ?
          AND is_deleted = 0
        """,
        (month_start, today_iso),
    ).fetchone()[0]
    balance = cash_balance(conn)
    last_movements = conn.execute(
        """
        SELECT m.*, c.name AS concept_name, r.id AS receipt_id, r.receipt_no
        FROM movements m
        JOIN concepts c ON c.id = m.concept_id
        LEFT JOIN receipts r ON r.movement_id = m.id
        WHERE m.is_deleted = 0
        ORDER BY m.movement_date DESC, m.id DESC
        LIMIT 8
        """
    ).fetchall()

    rows = "".join(movement_row(row, include_balance=False) for row in last_movements)
    if not rows:
        rows = '<tr><td colspan="7" class="muted">Aun no hay movimientos registrados.</td></tr>'

    return page(
        "Inicio",
        f"""
        {notice(query)}
        <section class="summary-grid">
          <article class="metric">
            <span>Saldo actual</span>
            <strong class="{"positive" if balance >= 0 else "negative"}">{format_money(balance)}</strong>
          </article>
          <article class="metric">
            <span>Ahorro inicial</span>
            <strong>{format_money(settings['opening_balance_cents'])}</strong>
          </article>
          <article class="metric">
            <span>Ingresos del mes</span>
            <strong class="positive">{format_money(income_month)}</strong>
          </article>
          <article class="metric">
            <span>Egresos del mes</span>
            <strong class="negative">{format_money(expense_month)}</strong>
          </article>
          <article class="metric">
            <span>Propiedades / empleados</span>
            <strong>{props} / {employees}</strong>
          </article>
        </section>

        <section class="toolbar">
          <a class="button primary" href="/movements">Registrar movimiento</a>
          <a class="button" href="/cashflow">Ver flujo de caja</a>
          <a class="button" href="/cash-settings">Configurar saldo inicial</a>
          <a class="button" href="/concepts">Administrar vigencias</a>
        </section>

        <section class="panel">
          <div class="section-head">
            <h2>Ultimos movimientos</h2>
            <a href="/movements">Ver todos</a>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Tipo</th>
                  <th>Concepto</th>
                  <th>Ingreso</th>
                  <th>Egreso</th>
                  <th>Referencia</th>
                  <th>Recibo</th>
                </tr>
              </thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
        </section>
        """,
        "/",
    )


def render_properties(conn, query) -> str:
    page_no = parse_page(query)
    offset = (page_no - 1) * PAGE_SIZE
    total = conn.execute(
        "SELECT COUNT(*) FROM properties WHERE is_deleted = 0"
    ).fetchone()[0]
    properties = conn.execute(
        """
        SELECT *
        FROM properties
        WHERE is_deleted = 0
        ORDER BY house_number
        LIMIT ? OFFSET ?
        """,
        (PAGE_SIZE, offset),
    ).fetchall()
    rows = "".join(
        f"""
        <tr>
          <td>Casa {row['house_number']}</td>
          <td>{esc(row['owner_name'])}</td>
          <td>{status_badge(row['active'], row['is_deleted'])}</td>
          <td>{esc_text(row['notes'])}</td>
          <td>{format_date(row['updated_at'][:10]) if row['updated_at'] else ''}</td>
          <td>
            <div class="actions">
              <a class="button small" href="/properties/edit?id={row['id']}">Editar</a>
              <form method="post" action="/properties/delete">
                <input type="hidden" name="id" value="{row['id']}">
                <button class="button small danger" type="submit" onclick="return confirm('Eliminar logicamente esta propiedad?')">Eliminar</button>
              </form>
            </div>
          </td>
        </tr>
        """
        for row in properties
    )
    if not rows:
        rows = '<tr><td colspan="6" class="muted">No hay propiedades registradas.</td></tr>'
    return page(
        "Propiedades",
        f"""
        {notice(query)}
        <section class="panel">
          <div class="section-head">
            <h2>Propiedades</h2>
            <a class="button primary" href="/properties/new">Nueva propiedad</a>
          </div>
          <div class="table-wrap">
            <table class="properties-table">
              <thead><tr><th>Casa</th><th>Responsable</th><th>Estado</th><th>Notas</th><th>Actualizado</th><th>Acciones</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
          {pagination('/properties', page_no, total)}
        </section>
        """,
        "/properties",
    )


def render_property_form(conn, property_id: int | None = None) -> str:
    row = None
    if property_id:
        row = conn.execute(
            "SELECT * FROM properties WHERE id = ? AND is_deleted = 0",
            (property_id,),
        ).fetchone()
        if not row:
            body, _ = error_page("Propiedad no encontrada.", 404)
            return body
    action = "/properties/update" if row else "/properties"
    title = "Editar propiedad" if row else "Nueva propiedad"
    hidden = f'<input type="hidden" name="id" value="{row["id"]}">' if row else ""
    active_field = (
        f"""
        <label>Estado
          <select name="active">{active_options(row['active'] if row else 1)}</select>
        </label>
        """
        if row
        else ""
    )
    return page(
        title,
        f"""
        <section class="panel narrow">
          <div class="section-head">
            <h2>{title}</h2>
            <a href="/properties">Volver</a>
          </div>
          <form class="form-panel" method="post" action="{action}">
            {hidden}
            <label>Numero de casa <input name="house_number" type="number" min="1" value="{esc(row['house_number'] if row else '')}" required></label>
            <label>Responsable <input name="owner_name" value="{esc(row['owner_name'] if row else '')}" required></label>
            {active_field}
            <label>Notas <textarea name="notes" rows="4">{esc(row['notes'] if row else '')}</textarea></label>
            <div class="actions">
              <button class="button primary" type="submit">Guardar</button>
              <a class="button" href="/properties">Cancelar</a>
            </div>
          </form>
        </section>
        """,
        "/properties",
    )


def render_employees(conn, query) -> str:
    page_no = parse_page(query)
    offset = (page_no - 1) * PAGE_SIZE
    total = conn.execute(
        "SELECT COUNT(*) FROM employees WHERE is_deleted = 0"
    ).fetchone()[0]
    employees = conn.execute(
        """
        SELECT *
        FROM employees
        WHERE is_deleted = 0
        ORDER BY active DESC, name
        LIMIT ? OFFSET ?
        """,
        (PAGE_SIZE, offset),
    ).fetchall()
    rows = "".join(
        f"""
        <tr>
          <td>{esc(row['name'])}</td>
          <td>{esc(row['role'])}</td>
          <td>{format_date(row['start_date'])}</td>
          <td>{status_badge(row['active'], row['is_deleted'])}</td>
          <td>{esc_text(row['notes'])}</td>
          <td>{format_date(row['updated_at'][:10]) if row['updated_at'] else ''}</td>
          <td>
            <div class="actions">
              <a class="button small" href="/employees/edit?id={row['id']}">Editar</a>
              <form method="post" action="/employees/delete">
                <input type="hidden" name="id" value="{row['id']}">
                <button class="button small danger" type="submit" onclick="return confirm('Eliminar logicamente este empleado?')">Eliminar</button>
              </form>
            </div>
          </td>
        </tr>
        """
        for row in employees
    )
    if not rows:
        rows = '<tr><td colspan="7" class="muted">No hay empleados registrados.</td></tr>'
    return page(
        "Empleados",
        f"""
        {notice(query)}
        <section class="panel">
          <div class="section-head">
            <h2>Empleados</h2>
            <a class="button primary" href="/employees/new">Nuevo empleado</a>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Nombre</th><th>Funcion</th><th>Fecha inicio</th><th>Estado</th><th>Notas</th><th>Actualizado</th><th>Acciones</th></tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
          {pagination('/employees', page_no, total)}
        </section>
        """,
        "/employees",
    )


def render_employee_form(conn, employee_id: int | None = None) -> str:
    row = None
    if employee_id:
        row = conn.execute(
            "SELECT * FROM employees WHERE id = ? AND is_deleted = 0",
            (employee_id,),
        ).fetchone()
        if not row:
            body, _ = error_page("Empleado no encontrado.", 404)
            return body
    action = "/employees/update" if row else "/employees"
    title = "Editar empleado" if row else "Nuevo empleado"
    hidden = f'<input type="hidden" name="id" value="{row["id"]}">' if row else ""
    active_field = (
        f"""
        <label>Estado
          <select name="active">{active_options(row['active'] if row else 1)}</select>
        </label>
        """
        if row
        else ""
    )
    return page(
        title,
        f"""
        <section class="panel narrow">
          <div class="section-head">
            <h2>{title}</h2>
            <a href="/employees">Volver</a>
          </div>
          <form class="form-panel" method="post" action="{action}">
            {hidden}
            <label>Nombre <input name="name" value="{esc(row['name'] if row else '')}" required></label>
            <label>Funcion <input name="role" value="{esc(row['role'] if row else '')}"></label>
            <label>Fecha de inicio <input name="start_date" type="date" value="{esc(row['start_date'] if row else '')}"></label>
            {active_field}
            <label>Notas <textarea name="notes" rows="4">{esc(row['notes'] if row else '')}</textarea></label>
            <div class="actions">
              <button class="button primary" type="submit">Guardar</button>
              <a class="button" href="/employees">Cancelar</a>
            </div>
          </form>
        </section>
        """,
        "/employees",
    )


def select_options(rows, selected: int | None = None, blank: str | None = None, label_fn=None) -> str:
    options = ""
    if blank is not None:
        options += f'<option value="">{esc(blank)}</option>'
    for row in rows:
        label = label_fn(row) if label_fn else row["name"]
        is_selected = " selected" if selected is not None and int(row["id"]) == selected else ""
        options += f'<option value="{row["id"]}"{is_selected}>{esc(label)}</option>'
    return options


def month_options(blank: str = "Sin mes sugerido", selected: int | None = None) -> str:
    options = f'<option value=""{" selected" if selected is None else ""}>{blank}</option>'
    for number, name in MONTHS.items():
        options += f'<option value="{number}"{selected_attr(number, selected)}>{name.capitalize()}</option>'
    return options


def render_concepts(conn, query) -> str:
    concept_page = parse_page(query, "concept_page")
    rate_page = parse_page(query, "rate_page")
    concept_offset = (concept_page - 1) * PAGE_SIZE
    rate_offset = (rate_page - 1) * PAGE_SIZE
    concept_total = conn.execute(
        "SELECT COUNT(*) FROM concepts WHERE is_deleted = 0"
    ).fetchone()[0]
    rate_total = conn.execute(
        "SELECT COUNT(*) FROM concept_rates WHERE is_deleted = 0"
    ).fetchone()[0]
    concepts = conn.execute(
        """
        SELECT *
        FROM concepts
        WHERE is_deleted = 0
        ORDER BY direction, name
        LIMIT ? OFFSET ?
        """,
        (PAGE_SIZE, concept_offset),
    ).fetchall()
    rates = conn.execute(
        """
        SELECT cr.*, c.name AS concept_name, e.name AS employee_name
        FROM concept_rates cr
        JOIN concepts c ON c.id = cr.concept_id
        LEFT JOIN employees e ON e.id = cr.employee_id
        WHERE cr.is_deleted = 0
        ORDER BY c.name, e.name, cr.valid_from DESC
        LIMIT ? OFFSET ?
        """
        ,
        (PAGE_SIZE, rate_offset),
    ).fetchall()
    concept_rows = "".join(
        f"""
        <tr>
          <td>{esc(row['name'])}</td>
          <td><span class="badge {row['direction'].lower()}">{row['direction'].title()}</span></td>
          <td>{row['amount_mode'].title()}</td>
          <td>{row['frequency'].title()}</td>
          <td>{month_range(row['suggested_month_start'], row['suggested_month_end'])}</td>
          <td>{'Si' if row['requires_receipt'] else 'No'}</td>
          <td>{status_badge(row['active'], row['is_deleted'])}</td>
          <td>{format_date(row['updated_at'][:10]) if row['updated_at'] else ''}</td>
          <td>
            <div class="actions">
              <a class="button small" href="/concepts/edit?id={row['id']}">Editar</a>
              <form method="post" action="/concepts/delete">
                <input type="hidden" name="id" value="{row['id']}">
                <button class="button small danger" type="submit" onclick="return confirm('Eliminar logicamente este concepto?')">Eliminar</button>
              </form>
            </div>
          </td>
        </tr>
        """
        for row in concepts
    )
    if not concept_rows:
        concept_rows = '<tr><td colspan="9" class="muted">No hay conceptos registrados.</td></tr>'
    rate_rows = "".join(
        f"""
        <tr>
          <td>{esc(row['concept_name'])}</td>
          <td>{esc(row['employee_name'] or 'General')}</td>
          <td>{format_money(row['amount_cents'])}</td>
          <td>{format_date(row['valid_from'])}</td>
          <td>{format_date(row['valid_to']) or 'Indefinida'}</td>
          <td>{status_badge(row['active'], row['is_deleted'])}</td>
          <td>{format_date(row['updated_at'][:10]) if row['updated_at'] else ''}</td>
          <td>
            <div class="actions">
              <a class="button small" href="/concept-rates/edit?id={row['id']}">Editar</a>
              <form method="post" action="/concept-rates/delete">
                <input type="hidden" name="id" value="{row['id']}">
                <button class="button small danger" type="submit" onclick="return confirm('Eliminar logicamente esta vigencia?')">Eliminar</button>
              </form>
            </div>
          </td>
        </tr>
        """
        for row in rates
    )
    if not rate_rows:
        rate_rows = '<tr><td colspan="8" class="muted">No hay vigencias registradas.</td></tr>'

    return page(
        "Conceptos",
        f"""
        {notice(query)}
        <section class="panel">
          <div class="section-head">
            <h2>Conceptos de pago</h2>
            <a class="button primary" href="/concepts/new">Nuevo concepto</a>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Concepto</th><th>Tipo</th><th>Monto</th><th>Frecuencia</th><th>Mes sugerido</th><th>Recibo</th><th>Estado</th><th>Actualizado</th><th>Acciones</th>
                </tr>
              </thead>
              <tbody>{concept_rows}</tbody>
            </table>
          </div>
          {pagination('/concepts', concept_page, concept_total, 'concept_page')}
        </section>

        <section class="panel">
          <div class="section-head">
            <h2>Vigencias de montos</h2>
            <a class="button primary" href="/concept-rates/new">Nueva vigencia</a>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Concepto</th><th>Empleado</th><th>Monto</th><th>Desde</th><th>Hasta</th><th>Estado</th><th>Actualizado</th><th>Acciones</th></tr></thead>
              <tbody>{rate_rows}</tbody>
            </table>
          </div>
          {pagination('/concepts', rate_page, rate_total, 'rate_page')}
        </section>
        """,
        "/concepts",
    )


def render_concept_form(conn, concept_id: int | None = None) -> str:
    row = None
    if concept_id:
        row = conn.execute(
            "SELECT * FROM concepts WHERE id = ? AND is_deleted = 0",
            (concept_id,),
        ).fetchone()
        if not row:
            body, _ = error_page("Concepto no encontrado.", 404)
            return body
    action = "/concepts/update" if row else "/concepts"
    title = "Editar concepto" if row else "Nuevo concepto"
    hidden = f'<input type="hidden" name="id" value="{row["id"]}">' if row else ""
    active_field = (
        f"""
        <label>Estado
          <select name="active">{active_options(row['active'] if row else 1)}</select>
        </label>
        """
        if row
        else ""
    )
    return page(
        title,
        f"""
        <section class="panel narrow">
          <div class="section-head">
            <h2>{title}</h2>
            <a href="/concepts">Volver</a>
          </div>
          <form class="form-panel" method="post" action="{action}">
            {hidden}
            <label>Nombre <input name="name" value="{esc(row['name'] if row else '')}" required></label>
            <label>Tipo
              <select name="direction">
                <option value="INGRESO"{selected_attr('INGRESO', row['direction'] if row else 'INGRESO')}>Ingreso</option>
                <option value="EGRESO"{selected_attr('EGRESO', row['direction'] if row else '')}>Egreso</option>
              </select>
            </label>
            <label>Modo de monto
              <select name="amount_mode">
                <option value="VARIABLE"{selected_attr('VARIABLE', row['amount_mode'] if row else 'VARIABLE')}>Variable</option>
                <option value="FIJO"{selected_attr('FIJO', row['amount_mode'] if row else '')}>Fijo con vigencia</option>
                <option value="CALCULADO"{selected_attr('CALCULADO', row['amount_mode'] if row else '')}>Calculado</option>
              </select>
            </label>
            <label>Frecuencia
              <select name="frequency">
                <option value="EVENTUAL"{selected_attr('EVENTUAL', row['frequency'] if row else 'EVENTUAL')}>Eventual</option>
                <option value="MENSUAL"{selected_attr('MENSUAL', row['frequency'] if row else '')}>Mensual</option>
                <option value="ANUAL"{selected_attr('ANUAL', row['frequency'] if row else '')}>Anual</option>
              </select>
            </label>
            <div class="two-cols">
              <label>Desde mes <select name="suggested_month_start">{month_options('Sin inicio', row['suggested_month_start'] if row else None)}</select></label>
              <label>Hasta mes <select name="suggested_month_end">{month_options('Sin fin', row['suggested_month_end'] if row else None)}</select></label>
            </div>
            <label class="check"><input name="requires_receipt" type="checkbox" value="1"{checked_attr(row['requires_receipt'] if row else 0)}> Requiere recibo</label>
            {active_field}
            <label>Notas <textarea name="notes" rows="4">{esc(row['notes'] if row else '')}</textarea></label>
            <div class="actions">
              <button class="button primary" type="submit">Guardar</button>
              <a class="button" href="/concepts">Cancelar</a>
            </div>
          </form>
        </section>
        """,
        "/concepts",
    )


def render_rate_form(conn, rate_id: int | None = None) -> str:
    row = None
    if rate_id:
        row = conn.execute(
            "SELECT * FROM concept_rates WHERE id = ? AND is_deleted = 0",
            (rate_id,),
        ).fetchone()
        if not row:
            body, _ = error_page("Vigencia no encontrada.", 404)
            return body
    concepts = conn.execute(
        "SELECT * FROM concepts WHERE is_deleted = 0 ORDER BY direction, name"
    ).fetchall()
    employees = conn.execute(
        "SELECT * FROM employees WHERE is_deleted = 0 ORDER BY active DESC, name"
    ).fetchall()
    action = "/concept-rates/update" if row else "/concept-rates"
    title = "Editar vigencia" if row else "Nueva vigencia"
    hidden = f'<input type="hidden" name="id" value="{row["id"]}">' if row else ""
    active_field = (
        f"""
        <label>Estado
          <select name="active">{active_options(row['active'] if row else 1)}</select>
        </label>
        """
        if row
        else ""
    )
    return page(
        title,
        f"""
        <section class="panel narrow">
          <div class="section-head">
            <h2>{title}</h2>
            <a href="/concepts">Volver</a>
          </div>
          <form class="form-panel" method="post" action="{action}">
            {hidden}
            <label>Concepto
              <select name="concept_id" required>
                {select_options(concepts, row['concept_id'] if row else None)}
              </select>
            </label>
            <label>Empleado
              <select name="employee_id">
                {select_options(employees, row['employee_id'] if row else None, blank='General / no aplica')}
              </select>
            </label>
            <label>Monto <input name="amount" inputmode="decimal" value="{money_input(row['amount_cents']) if row else ''}" placeholder="630.20" required></label>
            <label>Vigente desde <input name="valid_from" type="date" value="{esc(row['valid_from'] if row else date.today().isoformat())}" required></label>
            <label>Vigente hasta <input name="valid_to" type="date" value="{esc(row['valid_to'] if row else '')}"></label>
            {active_field}
            <label>Notas <textarea name="notes" rows="4">{esc(row['notes'] if row else '')}</textarea></label>
            <div class="actions">
              <button class="button primary" type="submit">Guardar</button>
              <a class="button" href="/concepts">Cancelar</a>
            </div>
          </form>
        </section>
        """,
        "/concepts",
    )


def month_range(start: int | None, end: int | None) -> str:
    if not start and not end:
        return "-"
    if start and end and start != end:
        return f"{MONTHS[start].capitalize()} - {MONTHS[end].capitalize()}"
    month = start or end
    return MONTHS[month].capitalize()


def calendar_month_options(selected: str = "") -> str:
    current = date.today().replace(day=1)
    options = []
    for offset in range(0, 7):
        month_start = add_months(current, -offset)
        value = month_start.strftime("%Y-%m")
        label = f"{MONTHS[month_start.month].capitalize()} {month_start.year}"
        options.append(f'<option value="{value}"{selected_attr(value, selected)}>{label}</option>')
    return "".join(options)


def period_from_query(query, default_start: str, default_end: str):
    selected_month = query.get("month", [""])[0]
    if selected_month:
        try:
            month_start = datetime.strptime(selected_month, "%Y-%m").date().replace(day=1)
            next_month = add_months(month_start, 1)
            month_end = next_month - timedelta(days=1)
            if month_start <= date.today().replace(day=1) and month_start >= add_months(date.today().replace(day=1), -6):
                return month_start.isoformat(), month_end.isoformat(), selected_month
        except ValueError:
            pass
    return (
        query.get("from", [default_start])[0],
        query.get("to", [default_end])[0],
        "",
    )


def render_movements(conn, query) -> str:
    concepts = conn.execute(
        "SELECT * FROM concepts WHERE active = 1 AND is_deleted = 0 ORDER BY direction, name"
    ).fetchall()
    properties = conn.execute(
        "SELECT * FROM properties WHERE active = 1 AND is_deleted = 0 ORDER BY house_number"
    ).fetchall()
    employees = conn.execute(
        "SELECT * FROM employees WHERE active = 1 AND is_deleted = 0 ORDER BY name"
    ).fetchall()
    today = date.today()
    start, end, selected_month = period_from_query(query, "", "")
    movement_filter = ""
    movement_params = []
    if selected_month:
        movement_filter = "AND m.movement_date BETWEEN ? AND ?"
        movement_params = [start, end]
    movements = conn.execute(
      f"""
        SELECT
            m.*,
            c.name AS concept_name,
            r.id AS receipt_id,
            r.receipt_no,
            p.house_number,
            p.owner_name,
            e.name AS employee_name
        FROM movements m
        JOIN concepts c ON c.id = m.concept_id
        LEFT JOIN receipts r ON r.movement_id = m.id
        LEFT JOIN properties p ON p.id = m.property_id
        LEFT JOIN employees e ON e.id = m.employee_id
        WHERE m.is_deleted = 0
          {movement_filter}
        ORDER BY m.movement_date DESC, m.id DESC
        LIMIT 60
        """,
        movement_params,
    ).fetchall()
    rows = "".join(movement_row(row, include_balance=False, detail=True) for row in movements)
    if not rows:
        rows = '<tr><td colspan="8" class="muted">Aun no hay movimientos registrados.</td></tr>'
    year = date.today().year

    return page(
        "Movimientos",
        f"""
        {notice(query)}
        <section class="split">
          <form class="panel form-panel" method="post" action="/movements" enctype="multipart/form-data">
            <h2>Registrar movimiento</h2>
            <label>Fecha <input name="movement_date" type="date" value="{date.today().isoformat()}" required></label>
            <label>Concepto
              <select name="concept_id" required>
                {select_options(concepts, label_fn=lambda row: f"{row['direction'].title()} - {row['name']}")}
              </select>
            </label>
            <div class="two-cols">
              <label>Propiedad
                <select name="property_id">
                  {select_options(properties, blank='No aplica', label_fn=lambda row: f"Casa {row['house_number']} - {row['owner_name']}")}
                </select>
              </label>
              <label>Empleado
                <select name="employee_id">
                  {select_options(employees, blank='No aplica')}
                </select>
              </label>
            </div>
            <label>Persona / proveedor externo <input name="counterparty" placeholder="Ej. Empresa electrica"></label>
            <label>Monto <input name="amount" inputmode="decimal" placeholder="En blanco usa vigencia fija si existe"></label>
            <div class="two-cols">
              <label>Periodo mes
                <select name="period_month">{month_options('Sin periodo')}</select>
              </label>
              <label>Periodo anio <input name="period_year" type="number" min="2000" max="2100" value="{year}"></label>
            </div>
            <div class="two-cols">
              <label>Metodo de pago <input name="payment_method" placeholder="Efectivo, transferencia"></label>
              <label>Referencia <input name="reference" placeholder="Factura, boleta, cheque"></label>
            </div>
            <label>Descripcion <textarea name="description" rows="3" placeholder="Detalle que aparecera en el flujo y, si aplica, en el recibo"></textarea></label>
            <label>Comprobante / evidencia (opcional)
              <input type="file" name="attachment" accept=".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf">
            </label>
            <button class="button primary" type="submit">Guardar movimiento</button>
          </form>

          <aside class="panel help-panel">
            <h2>Reglas actuales</h2>
            <p>El tipo del movimiento lo define el concepto seleccionado. Si el concepto requiere recibo, el sistema genera uno automaticamente.</p>
            <p>Los pagos de agua y electricidad quedan en flujo de caja, pero no generan recibo interno por defecto.</p>
            <p>Si el monto se deja vacio, se intenta usar la vigencia activa del concepto y empleado seleccionado.</p>
          </aside>
        </section>

        <section class="panel">
          <div class="section-head"><h2>Movimientos recientes</h2></div>
          <form class="filters" method="get" action="/movements">
            <label>Mes calendario
              <select name="month">
                <option value="">Todos los meses</option>
                {calendar_month_options(selected_month)}
              </select>
            </label>
            <button class="button" type="submit">Filtrar</button>
          </form>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Fecha</th><th>Tipo</th><th>Concepto</th><th>Contraparte</th><th>Ingreso</th><th>Egreso</th><th>Referencia</th><th>Recibo</th>
                </tr>
              </thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
        </section>
        """,
        "/movements",
    )


def movement_row(row, include_balance: bool, running_balance: int | None = None, detail: bool = False) -> str:
    income = format_money(row["amount_cents"]) if row["direction"] == "INGRESO" else "-"
    expense = format_money(row["amount_cents"]) if row["direction"] == "EGRESO" else "-"
    receipt = (
        f'<a href="/receipt/{row["receipt_id"]}">{esc(row["receipt_no"])}</a>'
        if row["receipt_id"]
        else '<span class="muted">No aplica</span>'
    )
    direction = f'<span class="badge {row["direction"].lower()}">{row["direction"].title()}</span>'
    if detail:
        counterparty = row["counterparty"] or row_value(row, "employee_name") or (
            f"Casa {row['house_number']} - {row['owner_name']}" if row_value(row, "house_number") else ""
        )
        return f"""
        <tr>
          <td>{format_date(row['movement_date'])}</td>
          <td>{direction}</td>
          <td>{esc(row['concept_name'])}</td>
          <td>{esc(counterparty)}</td>
          <td>{income}</td>
          <td>{expense}</td>
          <td>{esc(row['reference'])}</td>
          <td>{receipt}</td>
        </tr>
        """
    balance_cell = f"<td>{format_money(running_balance)}</td>" if include_balance else ""
    return f"""
    <tr>
      <td>{format_date(row['movement_date'])}</td>
      <td>{direction}</td>
      <td>{esc(row['concept_name'])}</td>
      <td>{income}</td>
      <td>{expense}</td>
      <td>{esc(row['reference'])}</td>
      <td>{receipt}</td>
      {balance_cell}
    </tr>
    """


def property_account_totals(conn, property_id: int | None = None, start: str | None = None, end: str | None = None):
    properties = conn.execute(
        """
        SELECT id, house_number, owner_name
        FROM properties
        WHERE active = 1 AND is_deleted = 0
        ORDER BY house_number
        """
    ).fetchall()

    result_rows = []
    for prop in properties:
        pid = prop["id"]
        if property_id and pid != property_id:
            continue

        initial_balance = conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN direction = 'INGRESO' THEN amount_cents ELSE -amount_cents END), 0)
            FROM movements
            WHERE property_id = ?
              AND is_deleted = 0
              AND movement_date < ?
            """,
            (pid, start or "2000-01-01"),
        ).fetchone()[0]

        income_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount_cents), 0)
            FROM movements
            WHERE property_id = ?
              AND is_deleted = 0
              AND direction = 'INGRESO'
              AND movement_date BETWEEN ? AND ?
            """,
            (pid, start or "2000-01-01", end or date.today().isoformat()),
        ).fetchone()[0]

        expense_total = conn.execute(
            """
            SELECT COALESCE(SUM(amount_cents), 0)
            FROM movements
            WHERE property_id = ?
              AND is_deleted = 0
              AND direction = 'EGRESO'
              AND movement_date BETWEEN ? AND ?
            """,
            (pid, start or "2000-01-01", end or date.today().isoformat()),
        ).fetchone()[0]

        final_balance = initial_balance + income_total - expense_total
        result_rows.append(
            {
                "property_id": pid,
                "house_number": prop["house_number"],
                "owner_name": prop["owner_name"],
                "initial_balance": initial_balance,
                "income_total": income_total,
                "expense_total": expense_total,
                "final_balance": final_balance,
            }
        )

    return result_rows


def render_account_statement(conn, query) -> str:
    today = date.today()
    selected_property = parse_int(query.get("property_id", [""])[0])
    start, end, selected_month = period_from_query(
        query,
        today.replace(day=1).isoformat(),
        today.isoformat(),
    )
    properties = conn.execute(
        "SELECT id, house_number, owner_name FROM properties WHERE active = 1 AND is_deleted = 0 ORDER BY house_number"
    ).fetchall()
    rows = property_account_totals(conn, selected_property, start, end)

    table_rows = "".join(
        f"""
        <tr>
          <td>{esc(row['house_number'])}</td>
          <td>{esc(row['owner_name'])}</td>
          <td>{format_money(row['initial_balance'])}</td>
          <td>{format_money(row['income_total'])}</td>
          <td>{format_money(row['expense_total'])}</td>
          <td class="{'positive' if row['final_balance'] >= 0 else 'negative'}">{format_money(row['final_balance'])}</td>
        </tr>
        """
        for row in rows
    )

    if not table_rows:
        table_rows = '<tr><td colspan="6" class="muted">No hay datos para este periodo.</td></tr>'

    return page(
        "Cuenta corriente",
        f"""
        <section class="panel">
          <div class="section-head">
            <h2>Cuenta corriente por casa/contribuyente</h2>
          </div>
          <form class="filters" method="get" action="/accounts">
            <label>Casa
              <select name="property_id">
                <option value="">Todas</option>
                {''.join(f'<option value="{row["id"]}"{selected_attr(row["id"], selected_property)}>Casa {row["house_number"]} - {row["owner_name"]}</option>' for row in properties)}
              </select>
            </label>
            <label>Mes calendario
              <select name="month">
                <option value="">Rango personalizado</option>
                {calendar_month_options(selected_month)}
              </select>
            </label>
            <label>Desde <input type="date" name="from" value="{esc(start)}"></label>
            <label>Hasta <input type="date" name="to" value="{esc(end)}"></label>
            <button class="button primary" type="submit">Filtrar</button>
          </form>

          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Casa</th>
                  <th>Propietario</th>
                  <th>Saldo inicial</th>
                  <th>Ingresos</th>
                  <th>Egresos</th>
                  <th>Saldo final</th>
                </tr>
              </thead>
              <tbody>{table_rows}</tbody>
            </table>
          </div>
        </section>
        """,
        "/accounts",
    )


def add_months(base: date, months: int) -> date:
    year = base.year + (base.month - 1 + months) // 12
    month = (base.month - 1 + months) % 12 + 1
    day = min(base.day, 28)
    return date(year, month, day)


def period_summary(conn, start: str, end: str, property_id: int | None = None) -> dict[str, int]:
    prev_day = (datetime.strptime(start, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
    if property_id:
        opening = conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN direction = 'INGRESO' THEN amount_cents ELSE -amount_cents END), 0)
            FROM movements
            WHERE property_id = ?
              AND is_deleted = 0
              AND movement_date < ?
            """,
            (property_id, start),
        ).fetchone()[0]
    else:
        opening = cash_balance(conn, prev_day)

    params = [start, end]
    filters = "AND movement_date BETWEEN ? AND ?"
    if property_id:
        filters += " AND property_id = ?"
        params.append(property_id)

    income = conn.execute(
        f"""
        SELECT COALESCE(SUM(amount_cents), 0)
        FROM movements
        WHERE is_deleted = 0
          AND direction = 'INGRESO'
          {filters}
        """,
        params,
    ).fetchone()[0]

    expense = conn.execute(
        f"""
        SELECT COALESCE(SUM(amount_cents), 0)
        FROM movements
        WHERE is_deleted = 0
          AND direction = 'EGRESO'
          {filters}
        """,
        params,
    ).fetchone()[0]

    final = opening + income - expense
    return {
        "opening": opening,
        "income": income,
        "expense": expense,
        "final": final,
    }


def render_reports(conn, query) -> str:
    today = date.today()
    property_id = parse_int(query.get("property_id", [""])[0])
    start, end, selected_month = period_from_query(
        query,
        today.replace(day=1).isoformat(),
        today.isoformat(),
    )
    properties = conn.execute(
        "SELECT id, house_number, owner_name FROM properties WHERE active = 1 AND is_deleted = 0 ORDER BY house_number"
    ).fetchall()

    summary = period_summary(conn, start, end, property_id)
    month_cursor = date.today().replace(day=1)
    comparison = []
    for offset in range(5, -1, -1):
        month_start = add_months(month_cursor, -offset)
        month_end = add_months(month_start.replace(day=1), 1)
        month_end = date(month_end.year, month_end.month, 1) - timedelta(days=1)
        current = period_summary(conn, month_start.isoformat(), month_end.isoformat(), property_id)
        comparison.append({
            "label": month_start.strftime("%b %Y").replace(".", ""),
            "start": month_start.isoformat(),
            "end": month_end.isoformat(),
            "income": current["income"],
            "expense": current["expense"],
            "final": current["final"],
        })

    comparison_rows = "".join(
        f"""
        <tr>
          <td>{esc(item['label'])}</td>
          <td>{format_money(item['income'])}</td>
          <td>{format_money(item['expense'])}</td>
          <td>{format_money(item['final'])}</td>
        </tr>
        """
        for item in comparison
    )

    return page(
        "Reportes",
        f"""
        <section class="panel">
          <div class="section-head">
            <h2>Reportes financieros</h2>
          </div>
          <form class="filters" method="get" action="/reports">
            <label>Casa
              <select name="property_id">
                <option value="">Todas</option>
                {''.join(f'<option value="{row["id"]}"{selected_attr(row["id"], property_id)}>Casa {row["house_number"]} - {row["owner_name"]}</option>' for row in properties)}
              </select>
            </label>
            <label>Mes calendario
              <select name="month">
                <option value="">Rango personalizado</option>
                {calendar_month_options(selected_month)}
              </select>
            </label>
            <label>Desde <input type="date" name="from" value="{esc(start)}"></label>
            <label>Hasta <input type="date" name="to" value="{esc(end)}"></label>
            <button class="button primary" type="submit">Filtrar</button>
          </form>

          <section class="summary-grid compact">
            <article class="metric"><span>Saldo inicial</span><strong>{format_money(summary['opening'])}</strong></article>
            <article class="metric"><span>Ingresos</span><strong class="positive">{format_money(summary['income'])}</strong></article>
            <article class="metric"><span>Egresos</span><strong class="negative">{format_money(summary['expense'])}</strong></article>
            <article class="metric"><span>Saldo final</span><strong class="{'positive' if summary['final'] >= 0 else 'negative'}">{format_money(summary['final'])}</strong></article>
          </section>

          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Mes</th>
                  <th>Ingresos</th>
                  <th>Egresos</th>
                  <th>Saldo final</th>
                </tr>
              </thead>
              <tbody>{comparison_rows}</tbody>
            </table>
          </div>
        </section>
        """,
        "/reports",
    )


def render_cashflow(conn, query) -> str:
    today = date.today()
    start, end, selected_month = period_from_query(
        query,
        today.replace(month=1, day=1).isoformat(),
        today.isoformat(),
    )
    settings = get_cash_settings(conn)
    opening_date = settings["opening_balance_date"]
    previous_day = (datetime.strptime(start, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
    balance_before = cash_balance(conn, previous_day)
    movement_start = max(start, opening_date)
    rows = conn.execute(
        """
        SELECT
            m.*,
            c.name AS concept_name,
            r.id AS receipt_id,
            r.receipt_no,
            p.house_number,
            p.owner_name,
            e.name AS employee_name
        FROM movements m
        JOIN concepts c ON c.id = m.concept_id
        LEFT JOIN receipts r ON r.movement_id = m.id
        LEFT JOIN properties p ON p.id = m.property_id
        LEFT JOIN employees e ON e.id = m.employee_id
        WHERE m.movement_date BETWEEN ? AND ?
          AND m.is_deleted = 0
        ORDER BY m.movement_date, m.id
        """,
        (movement_start, end),
    ).fetchall()
    income_total = 0
    expense_total = 0
    running = balance_before
    table_rows = ""
    if start <= opening_date <= end:
        running += settings["opening_balance_cents"]
        table_rows += f"""
        <tr class="opening-row">
          <td>{format_date(opening_date)}</td>
          <td><span class="badge">Saldo</span></td>
          <td>Saldo inicial de ahorros</td>
          <td>Residencial Torremolinos</td>
          <td>-</td>
          <td>-</td>
          <td>{format_money(running)}</td>
          <td>{esc_text(settings['notes'])}</td>
          <td><span class="muted">No aplica</span></td>
        </tr>
        """
    for row in rows:
        if row["direction"] == "INGRESO":
            income_total += row["amount_cents"]
            running += row["amount_cents"]
        else:
            expense_total += row["amount_cents"]
            running -= row["amount_cents"]
        counterparty = row["counterparty"] or row["employee_name"] or (
            f"Casa {row['house_number']} - {row['owner_name']}" if row["house_number"] else ""
        )
        receipt = (
            f'<a href="/receipt/{row["receipt_id"]}">{esc(row["receipt_no"])}</a>'
            if row["receipt_id"]
            else '<span class="muted">No aplica</span>'
        )
        table_rows += f"""
        <tr>
          <td>{format_date(row['movement_date'])}</td>
          <td><span class="badge {row['direction'].lower()}">{row['direction'].title()}</span></td>
          <td>{esc(row['concept_name'])}</td>
          <td>{esc(counterparty)}</td>
          <td>{format_money(row['amount_cents']) if row['direction'] == 'INGRESO' else '-'}</td>
          <td>{format_money(row['amount_cents']) if row['direction'] == 'EGRESO' else '-'}</td>
          <td>{format_money(running)}</td>
          <td>{esc(row['reference'])}</td>
          <td>{receipt}</td>
        </tr>
        """
    if not table_rows:
        table_rows = '<tr><td colspan="9" class="muted">No hay movimientos en este rango.</td></tr>'
    params = urlencode({"from": start, "to": end})
    return page(
        "Flujo de caja",
        f"""
        <section class="panel">
          <div class="section-head">
            <h2>Flujo de caja</h2>
            <a href="/cashflow.csv?{params}">Exportar CSV</a>
          </div>
          <form class="filters" method="get" action="/cashflow">
            <label>Mes calendario
              <select name="month">
                <option value="">Rango personalizado</option>
                {calendar_month_options(selected_month)}
              </select>
            </label>
            <label>Desde <input type="date" name="from" value="{esc(start)}"></label>
            <label>Hasta <input type="date" name="to" value="{esc(end)}"></label>
            <button class="button" type="submit">Filtrar</button>
          </form>
          <section class="summary-grid compact">
            <article class="metric"><span>Saldo anterior</span><strong>{format_money(balance_before)}</strong></article>
            <article class="metric"><span>Ahorro inicial</span><strong>{format_money(settings['opening_balance_cents'])}</strong></article>
            <article class="metric"><span>Ingresos</span><strong class="positive">{format_money(income_total)}</strong></article>
            <article class="metric"><span>Egresos</span><strong class="negative">{format_money(expense_total)}</strong></article>
            <article class="metric"><span>Resultado</span><strong class="{"positive" if income_total - expense_total >= 0 else "negative"}">{format_money(income_total - expense_total)}</strong></article>
            <article class="metric"><span>Disponible final</span><strong class="{"positive" if running >= 0 else "negative"}">{format_money(running)}</strong></article>
          </section>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Fecha</th><th>Tipo</th><th>Concepto</th><th>Contraparte</th><th>Ingreso</th><th>Egreso</th><th>Saldo acumulado</th><th>Referencia</th><th>Recibo</th>
                </tr>
              </thead>
              <tbody>{table_rows}</tbody>
            </table>
          </div>
        </section>
        """,
        "/cashflow",
    )


def cashflow_csv(conn, query) -> str:
    today = date.today()
    start = query.get("from", [today.replace(month=1, day=1).isoformat()])[0]
    end = query.get("to", [today.isoformat()])[0]
    settings = get_cash_settings(conn)
    opening_date = settings["opening_balance_date"]
    previous_day = (datetime.strptime(start, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
    running = cash_balance(conn, previous_day)
    movement_start = max(start, opening_date)
    rows = conn.execute(
        """
        SELECT
            m.*,
            c.name AS concept_name,
            r.receipt_no,
            p.house_number,
            p.owner_name,
            e.name AS employee_name
        FROM movements m
        JOIN concepts c ON c.id = m.concept_id
        LEFT JOIN receipts r ON r.movement_id = m.id
        LEFT JOIN properties p ON p.id = m.property_id
        LEFT JOIN employees e ON e.id = m.employee_id
        WHERE m.movement_date BETWEEN ? AND ?
          AND m.is_deleted = 0
        ORDER BY m.movement_date, m.id
        """,
        (movement_start, end),
    ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Fecha",
            "Tipo",
            "Concepto",
            "Contraparte",
            "Ingreso",
            "Egreso",
            "Saldo acumulado",
            "Referencia",
            "Recibo",
            "Descripcion",
        ]
    )
    if start <= opening_date <= end:
        running += settings["opening_balance_cents"]
        writer.writerow(
            [
                opening_date,
                "SALDO",
                "Saldo inicial de ahorros",
                "Residencial Torremolinos",
                "",
                "",
                running / 100,
                settings["notes"],
                "",
                "Saldo inicial configurado",
            ]
        )
    for row in rows:
        if row["direction"] == "INGRESO":
            income = row["amount_cents"] / 100
            expense = ""
            running += row["amount_cents"]
        else:
            income = ""
            expense = row["amount_cents"] / 100
            running -= row["amount_cents"]
        counterparty = row["counterparty"] or row["employee_name"] or (
            f"Casa {row['house_number']} - {row['owner_name']}" if row["house_number"] else ""
        )
        writer.writerow(
            [
                row["movement_date"],
                row["direction"],
                row["concept_name"],
                counterparty,
                income,
                expense,
                running / 100,
                row["reference"],
                row["receipt_no"] or "",
                row["description"],
            ]
        )
    return output.getvalue()


def render_cash_settings(conn, query) -> str:
    settings = get_cash_settings(conn)
    current_balance = cash_balance(conn)
    return page(
        "Saldo inicial",
        f"""
        {notice(query)}
        <section class="split">
          <form class="panel form-panel" method="post" action="/cash-settings">
            <h2>Saldo inicial de ahorros</h2>
            <label>Monto disponible inicial
              <input name="opening_balance" inputmode="decimal" value="{money_input(settings['opening_balance_cents'])}" required>
            </label>
            <label>Fecha de inicio del control
              <input name="opening_balance_date" type="date" value="{esc(settings['opening_balance_date'])}" required>
            </label>
            <label>Notas
              <textarea name="notes" rows="4">{esc(settings['notes'])}</textarea>
            </label>
            <button class="button primary" type="submit">Guardar saldo inicial</button>
          </form>

          <aside class="panel help-panel">
            <h2>Disponible actual</h2>
            <p class="big-number">{format_money(current_balance)}</p>
            <p>Este saldo se calcula como ahorros iniciales mas ingresos, menos egresos, desde la fecha de inicio configurada.</p>
            <p>El saldo inicial no se trata como ingreso ordinario; es el punto de partida de caja.</p>
          </aside>
        </section>
        """,
        "/cash-settings",
    )


def render_receipts(conn, query) -> str:
    today = date.today()
    start, end, selected_month = period_from_query(query, "", "")
    receipt_filter = ""
    receipt_params = []
    if selected_month:
        receipt_filter = "AND r.issued_date BETWEEN ? AND ?"
        receipt_params = [start, end]
    rows = conn.execute(
        f"""
        SELECT r.*, m.amount_cents, c.name AS concept_name
        FROM receipts r
        JOIN movements m ON m.id = r.movement_id
        JOIN concepts c ON c.id = m.concept_id
        WHERE r.is_deleted = 0
          AND m.is_deleted = 0
          {receipt_filter}
        ORDER BY r.issued_date DESC, r.sequence DESC
        LIMIT 100
        """,
        receipt_params,
    ).fetchall()
    table_rows = "".join(
        f"""
        <tr>
          <td><a href="/receipt/{row['id']}">{esc(row['receipt_no'])}</a></td>
          <td>{format_date(row['issued_date'])}</td>
          <td><span class="badge {row['direction'].lower()}">{row['direction'].title()}</span></td>
          <td>{esc(row['concept_name'])}</td>
          <td>{esc(row['payer_name'])}</td>
          <td>{esc(row['receiver_name'])}</td>
          <td>{format_money(row['amount_cents'])}</td>
        </tr>
        """
        for row in rows
    )
    if not table_rows:
        table_rows = '<tr><td colspan="7" class="muted">Aun no hay recibos generados.</td></tr>'
    return page(
        "Recibos",
        f"""
        <section class="panel">
          <div class="section-head"><h2>Recibos generados</h2></div>
          <form class="filters" method="get" action="/receipts">
            <label>Mes calendario
              <select name="month">
                <option value="">Todos los meses</option>
                {calendar_month_options(selected_month)}
              </select>
            </label>
            <button class="button" type="submit">Filtrar</button>
          </form>
          <div class="table-wrap">
            <table>
              <thead><tr><th>No.</th><th>Fecha</th><th>Tipo</th><th>Concepto</th><th>Recibi de</th><th>Recibido por</th><th>Monto</th></tr></thead>
              <tbody>{table_rows}</tbody>
            </table>
          </div>
        </section>
        """,
        "/receipts",
    )


def render_receipt(conn, receipt_id: int) -> str:
    receipt = conn.execute(
        """
        SELECT
            r.*,
            m.amount_cents,
            m.period_month,
            m.period_year,
            m.payment_method,
            m.reference,
            m.description,
            p.house_number,
            p.notes AS property_notes,
            c.name AS concept_name,
            c.frequency AS frequency
        FROM receipts r
        JOIN movements m ON m.id = r.movement_id
        JOIN concepts c ON c.id = m.concept_id
          LEFT JOIN properties p ON p.id = m.property_id
        WHERE r.id = ?
          AND r.is_deleted = 0
          AND m.is_deleted = 0
        """,
        (receipt_id,),
    ).fetchone()
    if not receipt:
        body, _ = error_page("Recibo no encontrado.", 404)
        return body
    title = "Recibo de ingreso" if receipt["direction"] == "INGRESO" else "Comprobante de egreso"
    counterpart_label = "Recibi de" if receipt["direction"] == "INGRESO" else "Pagado a"
    counterpart_value = receipt["payer_name"] if receipt["direction"] == "INGRESO" else receipt["receiver_name"]
    receipt_month = receipt["receipt_month"] or receipt["period_month"] or int(receipt["issued_date"][5:7])
    receipt_year = receipt["period_year"] or int(receipt["issued_date"][:4])
    period = f"Mes de {MONTHS[receipt_month].title()} Año {receipt_year}"
    concept_text = receipt_concept_text(receipt)
    pdf_filename = receipt_pdf_filename(receipt)
    month_options = "".join(
      f'<option value="{month}"{selected_attr(month, receipt_month)}>{esc(name.title())}</option>'
      for month, name in MONTHS.items()
    )
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(pdf_filename)}</title>
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body class="print-body">
  <main class="receipt-shell">
    <div class="receipt-actions">
      <a class="button" href="/receipts">Volver</a>
      <button class="button primary" onclick="window.print()">Guardar {esc(pdf_filename)}</button>
    </div>
    <form class="receipt-preview-controls" method="post" action="/receipt/update">
      <input type="hidden" name="receipt_id" value="{receipt_id}">
      <label>Mes aplicado al recibo
        <select name="receipt_month" onchange="this.form.submit()">{month_options}</select>
      </label>
      <span class="muted">La vista se actualiza al seleccionar el mes.</span>
    </form>
    <article class="receipt">
      <header>
        <div>
          <p class="eyebrow">Residencial Torremolinos</p>
          <h1>{title}</h1>
        </div>
        <div class="receipt-number">
          <span>No.</span>
          <strong>{esc(receipt['receipt_no'])}</strong>
        </div>
      </header>
      <div class="receipt-status">CANCELADO</div>

      <section class="receipt-grid">
        <label>Lugar <strong>{esc(receipt['place'])}</strong></label>
        <label>Fecha <strong>{format_date(receipt['issued_date'])}</strong></label>
        <label>Monto <strong>{format_money(receipt['amount_cents'])}</strong></label>
      </section>

      <section class="receipt-lines">
        <p><span>{counterpart_label}:</span> {esc(counterpart_value)}</p>
        <p><span>La cantidad de:</span> {esc(receipt['amount_words'])}</p>
        <p><span>Por concepto de:</span> {esc_text(concept_text)}</p>
        <p><span>Periodo:</span> {esc(period)}</p>
        <p><span>Referencia:</span> {esc(receipt['reference'] or 'No aplica')}</p>
      </section>

      <footer>
        <div class="signature">
          <span></span>
          <p>Entrega / paga</p>
        </div>
        <div class="signature">
          <span></span>
          <p>Recibe</p>
        </div>
      </footer>
    </article>
  </main>
</body>
</html>"""


class TorremolinosHandler(BaseHTTPRequestHandler):
    db_path: Path = DEFAULT_DB

    def log_message(self, format, *args):
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/static/styles.css":
                self.send_static("styles.css")
                return
            with connect(self.db_path) as conn:
                if parsed.path == "/":
                    self.send_html(render_dashboard(conn, query))
                elif parsed.path == "/properties":
                    self.send_html(render_properties(conn, query))
                elif parsed.path == "/properties/new":
                    self.send_html(render_property_form(conn))
                elif parsed.path == "/properties/edit":
                    self.send_html(render_property_form(conn, parse_int(query.get("id", [""])[0])))
                elif parsed.path == "/employees":
                    self.send_html(render_employees(conn, query))
                elif parsed.path == "/employees/new":
                    self.send_html(render_employee_form(conn))
                elif parsed.path == "/employees/edit":
                    self.send_html(render_employee_form(conn, parse_int(query.get("id", [""])[0])))
                elif parsed.path == "/concepts":
                    self.send_html(render_concepts(conn, query))
                elif parsed.path == "/concepts/new":
                    self.send_html(render_concept_form(conn))
                elif parsed.path == "/concepts/edit":
                    self.send_html(render_concept_form(conn, parse_int(query.get("id", [""])[0])))
                elif parsed.path == "/concept-rates/new":
                    self.send_html(render_rate_form(conn))
                elif parsed.path == "/concept-rates/edit":
                    self.send_html(render_rate_form(conn, parse_int(query.get("id", [""])[0])))
                elif parsed.path == "/movements":
                    self.send_html(render_movements(conn, query))
                elif parsed.path == "/accounts":
                    self.send_html(render_account_statement(conn, query))
                elif parsed.path == "/reports":
                    self.send_html(render_reports(conn, query))
                elif parsed.path == "/cash-settings":
                    self.send_html(render_cash_settings(conn, query))
                elif parsed.path == "/cashflow":
                    self.send_html(render_cashflow(conn, query))
                elif parsed.path == "/cashflow.csv":
                    self.send_csv(cashflow_csv(conn, query), "flujo_caja.csv")
                elif parsed.path == "/receipts":
                    self.send_html(render_receipts(conn, query))
                elif parsed.path.startswith("/receipt/"):
                    receipt_id = int(parsed.path.rsplit("/", 1)[1])
                    self.send_html(render_receipt(conn, receipt_id))
                else:
                    body, status = error_page("Pagina no encontrada.", 404)
                    self.send_html(body, status)
        except Exception as exc:
            body, status = error_page(str(exc), 500)
            self.send_html(body, status)

    def do_POST(self):
        parsed = urlparse(self.path)
        data = self.read_form()
        try:
            with connect(self.db_path) as conn:
                if parsed.path == "/properties":
                    self.add_property(conn, data)
                    self.redirect("/properties?ok=1")
                elif parsed.path == "/properties/update":
                    self.update_property(conn, data)
                    self.redirect("/properties?ok=1")
                elif parsed.path == "/properties/delete":
                    self.delete_property(conn, data)
                    self.redirect("/properties?ok=1")
                elif parsed.path == "/employees":
                    self.add_employee(conn, data)
                    self.redirect("/employees?ok=1")
                elif parsed.path == "/employees/update":
                    self.update_employee(conn, data)
                    self.redirect("/employees?ok=1")
                elif parsed.path == "/employees/delete":
                    self.delete_employee(conn, data)
                    self.redirect("/employees?ok=1")
                elif parsed.path == "/concepts":
                    self.add_concept(conn, data)
                    self.redirect("/concepts?ok=1")
                elif parsed.path == "/concepts/update":
                    self.update_concept(conn, data)
                    self.redirect("/concepts?ok=1")
                elif parsed.path == "/concepts/delete":
                    self.delete_concept(conn, data)
                    self.redirect("/concepts?ok=1")
                elif parsed.path == "/concept-rates":
                    self.add_rate(conn, data)
                    self.redirect("/concepts?ok=1")
                elif parsed.path == "/concept-rates/update":
                    self.update_rate(conn, data)
                    self.redirect("/concepts?ok=1")
                elif parsed.path == "/concept-rates/delete":
                    self.delete_rate(conn, data)
                    self.redirect("/concepts?ok=1")
                elif parsed.path == "/cash-settings":
                    self.update_cash_settings(conn, data)
                    self.redirect("/cash-settings?ok=1")
                elif parsed.path == "/movements":
                    receipt_id = self.add_movement(conn, data)
                    if receipt_id:
                        self.redirect(f"/receipt/{receipt_id}")
                    else:
                        self.redirect("/movements?ok=1")
                elif parsed.path == "/receipt/update":
                    self.update_receipt(conn, data)
                    receipt_id = parse_int(data.get("receipt_id"))
                    self.redirect(f"/receipt/{receipt_id}")
                else:
                    body, status = error_page("Ruta no encontrada.", 404)
                    self.send_html(body, status)
        except Exception as exc:
            body, status = error_page(str(exc), 400)
            self.send_html(body, status)

    def update_receipt(self, conn, data) -> None:
        receipt_id = parse_int(data.get("receipt_id"))
        receipt_month = parse_int(data.get("receipt_month"))
        if not receipt_id or not receipt_month or not 1 <= receipt_month <= 12:
            raise ValueError("Debe seleccionar un mes valido para el recibo.")
        updated = conn.execute(
            """
            UPDATE receipts
            SET receipt_month = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
            WHERE id = ? AND is_deleted = 0
            """,
            (receipt_month, CURRENT_USER, receipt_id),
        ).rowcount
        if not updated:
            raise ValueError("Recibo no encontrado.")

    def read_form(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        content_type = self.headers.get("Content-Type", "")

        if content_type.startswith("multipart/form-data"):
            return parse_multipart_form_data(raw, content_type)

        decoded = raw.decode("utf-8")
        parsed = parse_qs(decoded, keep_blank_values=True)
        return {key: values[0].strip() for key, values in parsed.items()}

    def add_property(self, conn, data) -> None:
        conn.execute(
            """
            INSERT INTO properties (house_number, owner_name, notes, updated_at, created_by, updated_by)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            """,
            (
                parse_int(data.get("house_number")),
                data.get("owner_name", ""),
                data.get("notes", ""),
                CURRENT_USER,
                CURRENT_USER,
            ),
        )

    def update_property(self, conn, data) -> None:
        conn.execute(
            """
            UPDATE properties
            SET
                house_number = ?,
                owner_name = ?,
                active = ?,
                notes = ?,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = ?
            WHERE id = ?
              AND is_deleted = 0
            """,
            (
                parse_int(data.get("house_number")),
                data.get("owner_name", ""),
                parse_int(data.get("active")) or 0,
                data.get("notes", ""),
                CURRENT_USER,
                parse_int(data.get("id")),
            ),
        )

    def delete_property(self, conn, data) -> None:
        conn.execute(
            """
            UPDATE properties
            SET active = 0,
                is_deleted = 1,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = ?
            WHERE id = ?
            """,
            (CURRENT_USER, parse_int(data.get("id"))),
        )

    def add_employee(self, conn, data) -> None:
        conn.execute(
            """
            INSERT INTO employees (name, role, start_date, notes, updated_at, created_by, updated_by)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            """,
            (
                data.get("name", ""),
                data.get("role", ""),
                data.get("start_date", ""),
                data.get("notes", ""),
                CURRENT_USER,
                CURRENT_USER,
            ),
        )

    def update_employee(self, conn, data) -> None:
        conn.execute(
            """
            UPDATE employees
            SET
                name = ?,
                role = ?,
                start_date = ?,
                active = ?,
                notes = ?,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = ?
            WHERE id = ?
              AND is_deleted = 0
            """,
            (
                data.get("name", ""),
                data.get("role", ""),
                data.get("start_date", ""),
                parse_int(data.get("active")) or 0,
                data.get("notes", ""),
                CURRENT_USER,
                parse_int(data.get("id")),
            ),
        )

    def delete_employee(self, conn, data) -> None:
        conn.execute(
            """
            UPDATE employees
            SET active = 0,
                is_deleted = 1,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = ?
            WHERE id = ?
            """,
            (CURRENT_USER, parse_int(data.get("id"))),
        )

    def add_concept(self, conn, data) -> None:
        conn.execute(
            """
            INSERT INTO concepts (
                name,
                direction,
                amount_mode,
                frequency,
                suggested_month_start,
                suggested_month_end,
                requires_receipt,
                notes,
                updated_at,
                created_by,
                updated_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            """,
            (
                data.get("name", ""),
                data.get("direction", "EGRESO"),
                data.get("amount_mode", "VARIABLE"),
                data.get("frequency", "EVENTUAL"),
                parse_int(data.get("suggested_month_start")),
                parse_int(data.get("suggested_month_end")),
                1 if data.get("requires_receipt") == "1" else 0,
                data.get("notes", ""),
                CURRENT_USER,
                CURRENT_USER,
            ),
        )

    def update_concept(self, conn, data) -> None:
        conn.execute(
            """
            UPDATE concepts
            SET
                name = ?,
                direction = ?,
                amount_mode = ?,
                frequency = ?,
                suggested_month_start = ?,
                suggested_month_end = ?,
                requires_receipt = ?,
                active = ?,
                notes = ?,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = ?
            WHERE id = ?
              AND is_deleted = 0
            """,
            (
                data.get("name", ""),
                data.get("direction", "EGRESO"),
                data.get("amount_mode", "VARIABLE"),
                data.get("frequency", "EVENTUAL"),
                parse_int(data.get("suggested_month_start")),
                parse_int(data.get("suggested_month_end")),
                1 if data.get("requires_receipt") == "1" else 0,
                parse_int(data.get("active")) or 0,
                data.get("notes", ""),
                CURRENT_USER,
                parse_int(data.get("id")),
            ),
        )

    def delete_concept(self, conn, data) -> None:
        concept_id = parse_int(data.get("id"))
        conn.execute(
            """
            UPDATE concepts
            SET active = 0,
                is_deleted = 1,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = ?
            WHERE id = ?
            """,
            (CURRENT_USER, concept_id),
        )
        conn.execute(
            """
            UPDATE concept_rates
            SET active = 0,
                is_deleted = 1,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = ?
            WHERE concept_id = ?
            """,
            (CURRENT_USER, concept_id),
        )

    def add_rate(self, conn, data) -> None:
        concept_id = parse_int(data.get("concept_id"))
        employee_id = parse_int(data.get("employee_id"))
        valid_from = data.get("valid_from") or date.today().isoformat()
        amount_cents = parse_money(data.get("amount"))
        close_previous_rate(conn, concept_id, employee_id, valid_from)
        conn.execute(
            """
            INSERT INTO concept_rates (
                concept_id,
                employee_id,
                amount_cents,
                valid_from,
                notes,
                updated_at,
                created_by,
                updated_by
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            """,
            (
                concept_id,
                employee_id,
                amount_cents,
                valid_from,
                data.get("notes", ""),
                CURRENT_USER,
                CURRENT_USER,
            ),
        )

    def update_rate(self, conn, data) -> None:
        conn.execute(
            """
            UPDATE concept_rates
            SET
                concept_id = ?,
                employee_id = ?,
                amount_cents = ?,
                valid_from = ?,
                valid_to = ?,
                active = ?,
                notes = ?,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = ?
            WHERE id = ?
              AND is_deleted = 0
            """,
            (
                parse_int(data.get("concept_id")),
                parse_int(data.get("employee_id")),
                parse_money(data.get("amount")),
                data.get("valid_from") or date.today().isoformat(),
                data.get("valid_to") or None,
                parse_int(data.get("active")) or 0,
                data.get("notes", ""),
                CURRENT_USER,
                parse_int(data.get("id")),
            ),
        )

    def delete_rate(self, conn, data) -> None:
        conn.execute(
            """
            UPDATE concept_rates
            SET active = 0,
                is_deleted = 1,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = ?
            WHERE id = ?
            """,
            (CURRENT_USER, parse_int(data.get("id"))),
        )

    def update_cash_settings(self, conn, data) -> None:
        conn.execute(
            """
            UPDATE cash_settings
            SET opening_balance_cents = ?,
                opening_balance_date = ?,
                notes = ?,
                updated_at = CURRENT_TIMESTAMP,
                updated_by = ?
            WHERE id = 1
            """,
            (
                parse_money(data.get("opening_balance")),
                data.get("opening_balance_date") or date.today().isoformat(),
                data.get("notes", ""),
                CURRENT_USER,
            ),
        )

    def add_movement(self, conn, data) -> int | None:
        concept_id = parse_int(data.get("concept_id"))
        concept = conn.execute(
            "SELECT * FROM concepts WHERE id = ? AND active = 1 AND is_deleted = 0",
            (concept_id,),
        ).fetchone()
        if not concept:
            raise ValueError("Debe seleccionar un concepto valido.")
        movement_date = data.get("movement_date") or date.today().isoformat()
        property_id = parse_int(data.get("property_id"))
        employee_id = parse_int(data.get("employee_id"))
        amount_raw = data.get("amount")
        if amount_raw:
            amount_cents = parse_money(amount_raw)
        else:
            rate = current_rate(conn, concept_id, employee_id, movement_date)
            if not rate:
              raise ValueError(
                f"El concepto '{concept['name']}' no tiene una vigencia activa para "
                "esa fecha. Seleccione Cuota ordinaria residencial para registrar "
                "el pago mensual o ingrese el monto manualmente para un servicio variable."
              )
            amount_cents = rate["amount_cents"]
        cursor = conn.execute(
            """
            INSERT INTO movements (
                movement_date,
                direction,
                concept_id,
                property_id,
                employee_id,
                counterparty,
                amount_cents,
                period_month,
                period_year,
                payment_method,
                reference,
                description,
                updated_at,
                created_by,
                updated_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
            """,
            (
                movement_date,
                concept["direction"],
                concept_id,
                property_id,
                employee_id,
                data.get("counterparty", ""),
                amount_cents,
                parse_int(data.get("period_month")),
                parse_int(data.get("period_year")),
                data.get("payment_method", ""),
                data.get("reference", ""),
                data.get("description", "") or concept["name"],
                CURRENT_USER,
                CURRENT_USER,
            ),
        )
        movement_id = int(cursor.lastrowid)
        add_movement_log(conn, movement_id, "CREATED", f"Movimiento registrado: {concept['name']}.", CURRENT_USER)

        attachment = data.get("attachment")
        if attachment is not None and hasattr(attachment, "filename"):
            save_movement_attachment(conn, movement_id, attachment, CURRENT_USER)

        if concept["requires_receipt"]:
            return create_receipt(conn, movement_id)
        return None

    def send_static(self, filename: str):
        path = BASE_DIR / "static" / filename
        if not path.exists():
            self.send_response(404)
            self.end_headers()
            return
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/css; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_html(self, content: str, status: int = 200):
        payload = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_csv(self, content: str, filename: str):
        payload = content.encode("utf-8-sig")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, location: str):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sistema local del Residencial Torremolinos")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    init_db(db_path)
    TorremolinosHandler.db_path = db_path

    server = ThreadingHTTPServer((args.host, args.port), TorremolinosHandler)
    print(f"{APP_NAME} listo en http://{args.host}:{args.port}")
    print(f"Base de datos: {db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")


if __name__ == "__main__":
    main()
