from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    house_number INTEGER NOT NULL UNIQUE,
    owner_name TEXT NOT NULL,
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

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movement_id INTEGER NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    receipt_no TEXT NOT NULL UNIQUE,
    place TEXT NOT NULL DEFAULT 'Guatemala',
    issued_date TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('INGRESO', 'EGRESO')),
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
    (1, "Axel Hernandez"),
    (2, "Jissette Mordillo"),
    (3, "Lesbia Aleman"),
    (4, "Edgar Rolando y Gaby Garcia Galindo"),
    (5, "Christian Flores"),
    (6, "Mariano Funes"),
    (7, "Lucy de Gudiel"),
    (8, "Estelita Garcia"),
    (9, "Edgar Hernandez"),
    (10, "Laboratorio Vida"),
    (11, "Jessica Sierra \"Lote\""),
    (12, "Jessica Sierra"),
    (13, "Jorge Mario Gomez"),
    (14, "Victoria Galvez"),
    (15, "Otto Cuevas"),
]


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
]


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
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


def migrate_schema(conn: sqlite3.Connection) -> None:
    add_column_if_missing(conn, "employees", "start_date", "TEXT NOT NULL DEFAULT ''")

    for table in (
        "properties",
        "employees",
        "concepts",
        "concept_rates",
        "movements",
        "receipts",
        "cash_settings",
    ):
        add_column_if_missing(conn, table, "active", "INTEGER NOT NULL DEFAULT 1")
        add_column_if_missing(conn, table, "is_deleted", "INTEGER NOT NULL DEFAULT 0")
        add_column_if_missing(conn, table, "updated_at", "TEXT NOT NULL DEFAULT ''")
        add_column_if_missing(conn, table, "created_by", "TEXT NOT NULL DEFAULT 'ADM'")
        add_column_if_missing(conn, table, "updated_by", "TEXT NOT NULL DEFAULT 'ADM'")
        conn.execute(
            f"""
            UPDATE {table}
            SET
                updated_at = COALESCE(NULLIF(updated_at, ''), created_at, CURRENT_TIMESTAMP),
                created_by = COALESCE(NULLIF(created_by, ''), 'ADM'),
                updated_by = COALESCE(NULLIF(updated_by, ''), 'ADM')
            """
        )


def add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def seed_properties(conn: sqlite3.Connection) -> None:
    existing = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]
    if existing:
        return
    conn.executemany(
        """
        INSERT INTO properties (house_number, owner_name)
        VALUES (?, ?)
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
    existing = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()[0]
    if existing:
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
        CONCEPTS,
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
