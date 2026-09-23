from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    house_number INTEGER NOT NULL UNIQUE,
    owner_name TEXT NOT NULL,
    phone_number TEXT NOT NULL DEFAULT '',
    whatsapp_enabled INTEGER NOT NULL DEFAULT 0 CHECK (whatsapp_enabled IN (0, 1)),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(created_by) <= 5),
    updated_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(updated_by) <= 5)
);

CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT '',
    start_date TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(created_by) <= 5),
    updated_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(updated_by) <= 5)
);

CREATE TABLE IF NOT EXISTS concepts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    direction TEXT NOT NULL CHECK (direction IN ('INGRESO', 'EGRESO')),
    amount_mode TEXT NOT NULL DEFAULT 'VARIABLE' CHECK (amount_mode IN ('FIJO', 'VARIABLE', 'CALCULADO')),
    frequency TEXT NOT NULL DEFAULT 'EVENTUAL' CHECK (frequency IN ('MENSUAL', 'ANUAL', 'EVENTUAL')),
    suggested_month_start INTEGER CHECK (suggested_month_start BETWEEN 1 AND 12),
    suggested_month_end INTEGER CHECK (suggested_month_end BETWEEN 1 AND 12),
    requires_receipt INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(created_by) <= 5),
    updated_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(updated_by) <= 5)
);

CREATE TABLE IF NOT EXISTS concept_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id INTEGER NOT NULL,
    employee_id INTEGER,
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(created_by) <= 5),
    updated_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(updated_by) <= 5),
    FOREIGN KEY (concept_id) REFERENCES concepts(id),
    FOREIGN KEY (employee_id) REFERENCES employees(id),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE INDEX IF NOT EXISTS idx_rates_lookup
ON concept_rates(concept_id, employee_id, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movement_date TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('INGRESO', 'EGRESO')),
    concept_id INTEGER NOT NULL,
    property_id INTEGER,
    employee_id INTEGER,
    counterparty TEXT NOT NULL DEFAULT '',
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
    period_month INTEGER CHECK (period_month BETWEEN 1 AND 12),
    period_year INTEGER CHECK (period_year BETWEEN 2000 AND 2100),
    payment_method TEXT NOT NULL DEFAULT '',
    reference TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(created_by) <= 5),
    updated_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(updated_by) <= 5),
    FOREIGN KEY (concept_id) REFERENCES concepts(id),
    FOREIGN KEY (property_id) REFERENCES properties(id),
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);

CREATE INDEX IF NOT EXISTS idx_movements_date ON movements(movement_date, id);
CREATE INDEX IF NOT EXISTS idx_movements_property ON movements(property_id);
CREATE INDEX IF NOT EXISTS idx_movements_employee ON movements(employee_id);

CREATE TABLE IF NOT EXISTS movement_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movement_id INTEGER NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    content_type TEXT NOT NULL DEFAULT '',
    file_size INTEGER NOT NULL DEFAULT 0 CHECK (file_size >= 0),
    local_path TEXT NOT NULL DEFAULT '',
    remote_url TEXT NOT NULL DEFAULT '',
    remote_provider TEXT NOT NULL DEFAULT '',
    remote_item_id TEXT NOT NULL DEFAULT '',
    remote_synced_at TEXT NOT NULL DEFAULT '',
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(created_by) <= 5),
    FOREIGN KEY (movement_id) REFERENCES movements(id),
    CHECK (length(original_name) > 0),
    CHECK (length(stored_name) > 0)
);

CREATE INDEX IF NOT EXISTS idx_movement_attachments_movement
ON movement_attachments(movement_id, uploaded_at);

CREATE TABLE IF NOT EXISTS movement_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movement_id INTEGER NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('CREATED', 'UPDATED', 'DELETED', 'ATTACHMENT_ADDED', 'COMMENTED', 'SYNCED')),
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(created_by) <= 5),
    FOREIGN KEY (movement_id) REFERENCES movements(id)
);

CREATE INDEX IF NOT EXISTS idx_movement_logs_movement
ON movement_logs(movement_id, created_at DESC);

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movement_id INTEGER NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    receipt_no TEXT NOT NULL UNIQUE,
    place TEXT NOT NULL DEFAULT 'Guatemala',
    issued_date TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('INGRESO', 'EGRESO')),
    receipt_month INTEGER CHECK (receipt_month BETWEEN 1 AND 12),
    payer_name TEXT NOT NULL,
    receiver_name TEXT NOT NULL,
    amount_words TEXT NOT NULL,
    concept_text TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(created_by) <= 5),
    updated_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(updated_by) <= 5),
    FOREIGN KEY (movement_id) REFERENCES movements(id)
);

CREATE TABLE IF NOT EXISTS cash_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    opening_balance_cents INTEGER NOT NULL DEFAULT 0 CHECK (opening_balance_cents >= 0),
    opening_balance_date TEXT NOT NULL DEFAULT '2026-01-01',
    notes TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(created_by) <= 5),
    updated_by TEXT NOT NULL DEFAULT 'ADM' CHECK (length(updated_by) <= 5)
);
"""


PROPERTIES = [
    (1, "Axel Hernandez", "5223-2471", 1),
    (2, "Jissette Mordillo", "", 0),
    (3, "Lesbia Aleman", "", 0),
    (4, "Edgar Rolando y Gaby Garcia Galindo", "", 0),
    (5, "Christian Flores", "5205-1136", 0),
    (6, "Mariano Funes", "4211-3574", 0),
    (7, "Lucy de Gudiel", "5202-5954", 0),
    (8, "Estelita Garcia", "5841-0466", 0),
    (9, "Edgar Hernandez", "4150-9075", 0),
    (10, "Laboratorio Vida", "3211-5099", 0),
    (11, "Jessica Sierra \"Lote\"", "5962-7770", 0),
    (12, "Jessica Sierra", "5514-1744", 0),
    (13, "Jorge Mario Gomez", "5858-2517", 0),
    (14, "Victoria Galvez", "4568-2041", 0),
    (15, "Otto Cuevas", "5203-5100", 0),
]

PROPERTY_PHONE_NUMBERS = {house: phone for house, _, phone, _ in PROPERTIES if phone}


CONCEPTS = [
    {
        "name": "Cuota ordinaria residencial",
        "direction": "INGRESO",
        "amount_mode": "FIJO",
        "frequency": "MENSUAL",
        "suggested_month_start": None,
        "suggested_month_end": None,
        "requires_receipt": 1,
        "notes": "Pago mensual de mantenimiento y seguridad.",
    },
    {
        "name": "Salario mensual",
        "direction": "EGRESO",
        "amount_mode": "FIJO",
        "frequency": "MENSUAL",
        "suggested_month_start": None,
        "suggested_month_end": None,
        "requires_receipt": 1,
        "notes": "Pago mensual a empleados del residencial.",
    },
    {
        "name": "Vacaciones",
        "direction": "EGRESO",
        "amount_mode": "CALCULADO",
        "frequency": "ANUAL",
        "suggested_month_start": 2,
        "suggested_month_end": 3,
        "requires_receipt": 1,
        "notes": "Pago anual sugerido entre febrero y marzo.",
    },
    {
        "name": "Bono 14",
        "direction": "EGRESO",
        "amount_mode": "CALCULADO",
        "frequency": "ANUAL",
        "suggested_month_start": 6,
        "suggested_month_end": 7,
        "requires_receipt": 1,
        "notes": "Pago anual sugerido entre junio y julio.",
    },
    {
        "name": "Aguinaldo",
        "direction": "EGRESO",
        "amount_mode": "CALCULADO",
        "frequency": "ANUAL",
        "suggested_month_start": 12,
        "suggested_month_end": 12,
        "requires_receipt": 1,
        "notes": "Pago anual de diciembre.",
    },
    {
        "name": "Agua",
        "direction": "EGRESO",
        "amount_mode": "VARIABLE",
        "frequency": "MENSUAL",
        "suggested_month_start": None,
        "suggested_month_end": None,
        "requires_receipt": 0,
        "notes": "Servicio con factura externa.",
    },
    {
        "name": "Electricidad",
        "direction": "EGRESO",
        "amount_mode": "VARIABLE",
        "frequency": "MENSUAL",
        "suggested_month_start": None,
        "suggested_month_end": None,
        "requires_receipt": 0,
        "notes": "Servicio con factura externa.",
    },
    {
        "name": "Insumos para trabajadores",
        "direction": "EGRESO",
        "amount_mode": "VARIABLE",
        "frequency": "EVENTUAL",
        "suggested_month_start": None,
        "suggested_month_end": None,
        "requires_receipt": 0,
        "notes": "Compras de herramientas, materiales o suministros.",
    },
    {
        "name": "Corte de grama",
        "direction": "EGRESO",
        "amount_mode": "VARIABLE",
        "frequency": "EVENTUAL",
        "suggested_month_start": None,
        "suggested_month_end": None,
        "requires_receipt": 1,
        "notes": "Pago a persona o proveedor por corte de grama.",
    },
    {
        "name": "Pintura areas comunes",
        "direction": "EGRESO",
        "amount_mode": "VARIABLE",
        "frequency": "EVENTUAL",
        "suggested_month_start": None,
        "suggested_month_end": None,
        "requires_receipt": 0,
        "notes": "Gastos de pintura o mantenimiento de areas comunes.",
    },
    {
        "name": "Salario quincenal",
        "direction": "EGRESO",
        "amount_mode": "FIJO",
        "frequency": "EVENTUAL",
        "suggested_month_start": None,
        "suggested_month_end": None,
        "requires_receipt": 1,
        "notes": "Trabajo de portería",
    },
]


class ClosingConnection(sqlite3.Connection):
    """SQLite connection that also closes when its context manager exits."""

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with connect(path) as conn:
        conn.executescript(SCHEMA)
        migrate_schema(conn)
        seed_properties(conn)
        seed_employees(conn)
        seed_concepts(conn)
        seed_initial_rates(conn)
        seed_cash_settings(conn)
        conn.execute("PRAGMA optimize")


def migrate_schema(conn: sqlite3.Connection) -> None:
    existing_tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    add_column_if_missing(conn, "employees", "start_date", "TEXT NOT NULL DEFAULT ''")

    phone_column_added = add_column_if_missing(
        conn, "properties", "phone_number", "TEXT NOT NULL DEFAULT ''"
    )
    whatsapp_column_added = add_column_if_missing(
        conn, "properties", "whatsapp_enabled", "INTEGER NOT NULL DEFAULT 0"
    )

    for table in (
        "properties",
        "employees",
        "concepts",
        "concept_rates",
        "movements",
        "receipts",
        "cash_settings",
    ):
        if table not in existing_tables:
            continue

        add_column_if_missing(conn, table, "active", "INTEGER NOT NULL DEFAULT 1")
        add_column_if_missing(conn, table, "is_deleted", "INTEGER NOT NULL DEFAULT 0")
        add_column_if_missing(conn, table, "updated_at", "TEXT NOT NULL DEFAULT ''")
        add_column_if_missing(conn, table, "created_by", "TEXT NOT NULL DEFAULT 'ADM'")
        add_column_if_missing(conn, table, "updated_by", "TEXT NOT NULL DEFAULT 'ADM'")
        if table == "receipts":
            add_column_if_missing(conn, table, "receipt_month", "INTEGER")
        conn.execute(
            f"""
            UPDATE {table}
            SET
                updated_at = COALESCE(NULLIF(updated_at, ''), created_at, CURRENT_TIMESTAMP),
                created_by = COALESCE(NULLIF(created_by, ''), 'ADM'),
                updated_by = COALESCE(NULLIF(updated_by, ''), 'ADM')
            """
        )

    if phone_column_added:
        conn.executemany(
            """
            UPDATE properties
            SET phone_number = ?, updated_at = CURRENT_TIMESTAMP
            WHERE house_number = ?
            """,
            [(phone, house) for house, phone in PROPERTY_PHONE_NUMBERS.items()],
        )
    if whatsapp_column_added:
        conn.execute(
            """
            UPDATE properties
            SET whatsapp_enabled = 1, updated_at = CURRENT_TIMESTAMP
            WHERE house_number = 1
            """
        )

    for table in ("movement_attachments", "movement_logs"):
        if table not in existing_tables:
            continue
        if "created_by" not in {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }:
            add_column_if_missing(conn, table, "created_by", "TEXT NOT NULL DEFAULT 'ADM'")

    if "movement_attachments" in existing_tables:
        add_column_if_missing(
            conn, "movement_attachments", "remote_provider", "TEXT NOT NULL DEFAULT ''"
        )
        add_column_if_missing(
            conn, "movement_attachments", "remote_item_id", "TEXT NOT NULL DEFAULT ''"
        )
        add_column_if_missing(
            conn, "movement_attachments", "remote_synced_at", "TEXT NOT NULL DEFAULT ''"
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_movement_attachments_remote_sync
            ON movement_attachments(remote_provider, remote_synced_at)
            """
        )


def add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> bool:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        return True
    return False


def seed_properties(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
    if existing:
        return
    conn.executemany(
        """
        INSERT INTO properties (house_number, owner_name, phone_number, whatsapp_enabled)
        VALUES (?, ?, ?, ?)
        """,
        PROPERTIES,
    )


def seed_employees(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    if existing:
        return
    conn.executemany(
        """
        INSERT INTO employees (name, role, start_date, notes)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("Jardinero", "Jardineria", "", "Nombre pendiente de confirmar."),
            ("Mantenimiento", "Mantenimiento", "", "Nombre pendiente de confirmar."),
        ],
    )


def seed_concepts(conn: sqlite3.Connection) -> None:
    existing_names = {
        row["name"] for row in conn.execute("SELECT name FROM concepts").fetchall()
    }
    missing = [concept for concept in CONCEPTS if concept["name"] not in existing_names]
    if not missing:
        return
    conn.executemany(
        """
        INSERT INTO concepts (
            name,
            direction,
            amount_mode,
            frequency,
            suggested_month_start,
            suggested_month_end,
            requires_receipt,
            notes
        )
        VALUES (
            :name,
            :direction,
            :amount_mode,
            :frequency,
            :suggested_month_start,
            :suggested_month_end,
            :requires_receipt,
            :notes
        )
        """,
        missing,
    )


def seed_initial_rates(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) FROM concept_rates").fetchone()[0]
    if existing:
        return

    cuota = conn.execute(
        "SELECT id FROM concepts WHERE name = ?",
        ("Cuota ordinaria residencial",),
    ).fetchone()
    if cuota:
        conn.execute(
            """
            INSERT INTO concept_rates (concept_id, amount_cents, valid_from, notes)
            VALUES (?, ?, ?, ?)
            """,
            (cuota["id"], 63020, "2026-01-01", "Monto observado en recibo de ejemplo."),
        )


def seed_cash_settings(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) FROM cash_settings").fetchone()[0]
    if existing:
        return
    conn.execute(
        """
        INSERT INTO cash_settings (id, opening_balance_cents, opening_balance_date, notes)
        VALUES (1, 0, '2026-01-01', 'Saldo inicial de ahorros disponible.')
        """
    )
