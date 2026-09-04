# Residencial Torremolinos

Sistema local para gestionar ingresos, egresos, conceptos de pago, vigencias, flujo de caja y recibos del residencial.

## Requisitos

- Python 3.10 o superior
- No requiere instalar librerias externas para la primera version

## Ejecutar

```bash
python3 app.py
```

Luego abrir:

```text
http://127.0.0.1:8000
```

En Windows normalmente se puede usar:

```bash
python app.py
```

## Datos

La base de datos se crea automaticamente en:

```text
data/torremolinos.sqlite3
```

Ese archivo es el que se debe respaldar. Contiene propiedades, empleados, conceptos, vigencias, movimientos y recibos.

## Alcance inicial

- Catalogo de propiedades
- CRUD de propiedades
- CRUD de empleados con fecha de inicio laboral
- CRUD de conceptos de ingreso/egreso
- CRUD de vigencias de montos fijos
- Listados de catalogos con paginacion y pantallas separadas de edicion
- Borrado logico mediante `active` e `is_deleted`
- Auditoria basica con `created_at`, `updated_at`, `created_by` y `updated_by`
- Saldo inicial de ahorros para arrancar el flujo de caja con dinero disponible previo
- Registro de movimientos de caja
- Flujo de caja con saldo acumulado
- Recibos imprimibles para conceptos que requieren recibo
- Exportacion CSV del flujo de caja

## Modelo de datos

La base SQLite usa tablas relacionales con llaves primarias (`PRIMARY KEY`), llaves foraneas (`FOREIGN KEY`) y restricciones `CHECK` para tipos, estados, montos y rangos de fechas/periodos. La aplicacion habilita `PRAGMA foreign_keys = ON` en cada conexion.

Los catalogos usan borrado logico para proteger el historico: al eliminar un registro se marca como inactivo y eliminado, pero no se borra fisicamente de las tablas operativas.
