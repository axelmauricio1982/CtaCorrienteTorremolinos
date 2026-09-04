# CtaCorrienteTorremolinos

Sistema de gestión para un residencial, pensado para controlar ingresos, egresos, conceptos de cobro, vigencias, flujo de caja y recibos.

## Descripción

Esta aplicación permite llevar la contabilidad operativa del residencial de forma local, con una base de datos SQLite y una interfaz web simple desarrollada en Python.

Incluye funcionalidades para:

- Registrar propiedades
- Administrar empleados
- Definir conceptos de ingreso y egreso
- Configurar vigencias y montos fijos
- Controlar movimientos de caja
- Visualizar flujo de caja con saldo acumulado
- Generar recibos imprimibles
- Exportar información en CSV

## Requisitos

- Python 3.10 o superior
- No requiere dependencias externas adicionales para esta versión inicial

## Ejecutar el proyecto

```bash
python3 app.py
```

Luego abre esta dirección en el navegador:

```text
http://127.0.0.1:8000
```

En Windows puedes usar:

```bash
python app.py
```

## Estructura del proyecto

```text
.
├── app.py
├── README.md
├── .gitignore
├── data/
│   └── torremolinos.sqlite3
├── static/
│   └── styles.css
└── torremolinos/
    ├── __init__.py
    └── db.py
```

## Base de datos

La base de datos se crea automáticamente en:

```text
data/torremolinos.sqlite3
```

Ese archivo debe respaldarse periódicamente porque almacena propiedades, empleados, conceptos, vigencias, movimientos, recibos y el saldo del flujo de caja.

## Alcance inicial

- Catálogo de propiedades
- CRUD de propiedades
- CRUD de empleados con fecha de inicio laboral
- CRUD de conceptos de ingreso y egreso
- CRUD de vigencias de montos fijos
- Listados con paginación
- Eliminado lógico con campos `active` e `is_deleted`
- Auditoría básica con `created_at`, `updated_at`, `created_by` y `updated_by`
- Saldo inicial de ahorros para iniciar flujo de caja
- Registro de movimientos de caja
- Flujo de caja con saldo acumulado
- Recibos imprimibles
- Exportación CSV del flujo de caja

## Modelo de datos

La base SQLite utiliza tablas relacionales con claves primarias, claves foráneas y restricciones para validar tipos, estados, montos y rangos de fechas. La aplicación activa `PRAGMA foreign_keys = ON` en cada conexión.

Los catálogos usan borrado lógico para proteger el historial: en vez de eliminar físicamente el registro, se marca como inactivo y eliminado.

## Estado del proyecto

Es una versión funcional local, lista para continuar con mejoras y ampliaciones según las necesidades del residencial.
