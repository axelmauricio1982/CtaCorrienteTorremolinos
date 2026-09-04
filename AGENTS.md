# AGENTS.md

## Proyecto

CtaCorrienteTorremolinos

Sistema de administración para un residencial, orientado al control financiero y operativo del condominio. El proyecto ya cuenta con una base funcional en Python con servidor HTTP local, SQLite y una interfaz web básica.

## Objetivo del proyecto

Construir una solución multiplataforma para:

- registrar ingresos y egresos del residencial
- manejar la cuenta corriente por propiedad/contribuyente
- justificar egresos con evidencia documental
- permitir filtros por rango de fechas o mes calendario
- generar reportes financieros por período y por casa
- exportar reportes a Excel (.xlsx) y PDF
- operar en Windows, Linux y macOS

## Stack actual

- Python 3.10+
- SQLite
- Servidor HTTP nativo de Python
- HTML/CSS/JavaScript ligero
- Sin dependencias externas obligatorias para la versión base

## Estado actual del repositorio

El proyecto ya existe y está funcional en su versión base. Actualmente incluye:

- propiedades
- empleados
- conceptos
- vigencias de montos
- movimientos
- flujo de caja
- recibos automáticos
- base de datos SQLite
- interfaz web básica

## Reglas de desarrollo

### 1. No partir de cero

No reescribir la aplicación desde cero. Debemos hacer incrementos sobre la estructura actual existente en:

- app.py
- torremolinos/db.py
- static/styles.css
- data/torremolinos.sqlite3

### 2. Mantener compatibilidad multiplataforma

Todo cambio debe funcionar en:

- Windows
- Linux
- macOS

Evitar dependencias que solo funcionen en un sistema operativo concreto.

### 3. Priorizar funcionalidad real sobre estética

La prioridad funcional es:

1. ingreso por casa/contribuyente
2. egresos con evidencia documental
3. reportes por mes y rango de fechas
4. cuenta corriente por casa
5. exportación a Excel/PDF
6. mejor UX visual

### 4. Mantener base de datos normalizada

La base debe seguir principios de normalización efectiva:

- separar entidades
- evitar duplicación innecesaria
- usar relaciones por claves foráneas
- mantener historial/auditoría
- separar movimientos de documentos y de bitácora

### 5. La evidencia es obligatoria para egresos

Todo egreso debe estar asociado a un comprobante documental.

Tipos admitidos:

- JPG
- JPEG
- PNG
- WEBP
- PDF

Se debe guardar:

- nombre del archivo
- tipo
- tamaño
- fecha de carga
- ruta local temporal
- referencia a almacenamiento remoto si aplica

### 6. Filtros y reportes requeridos

Debe existir soporte para:

- filtro por mes calendario
- filtro por rango de fechas
- filtro por propiedad/casa
- filtro por contribuyente
- filtro por concepto
- filtro por tipo de movimiento

Reportes necesarios:

- saldo inicial del período
- ingresos del período
- egresos del período
- saldo final
- cuenta corriente por propiedad/casa
- historial de movimientos
- reportes mensuales comparativos

### 7. Exportación requerida

Los reportes deben exportarse a formatos compatibles con ofimática común:

- .xlsx
- PDF

### 8. Sistema personal sin aprobación

No es necesario implementar un flujo de aprobación. El usuario principal es la persona que administra el sistema.

Sin embargo, sí debe existir trazabilidad con historial de cambios y bitácora simple.

## Arquitectura recomendada

### Modelo de datos

Se recomienda ampliar la estructura actual con estas entidades:

- properties
- people_or_owners
- concepts
- movements
- movement_attachments
- movement_logs
- cash_settings
- account_statements

### Lógica funcional

- Cada movimiento financiero debe tener una dirección: INGRESO o EGRESO.
- Cada movimiento puede estar ligado a una propiedad/casa.
- Cada egreso puede tener uno o varios documentos de soporte.
- Cada movimiento debe quedar registrado en el historial.
- Cada reporte debe calcularse a partir de la base de datos, no de valores manuales.

## Recomendaciones de implementación

### Uso de archivos adjuntos

Para la evidencia, la estrategia recomendada es:

1. guardar el archivo temporalmente en la máquina local
2. permitir revisión previa
3. si hay conexión, sincronizar a OneDrive/Google Drive
4. mantener referencia a la ubicación remota

Esto evita bloquear la operación si no hay internet.

### Base de datos

Preferir SQLite con tablas separadas para:

- datos maestros
- movimientos financieros
- documentos relacionados
- auditoría/historial

Esto mantiene el sistema limpio y escalable.

## Convenciones

- Nombre del proyecto: CtaCorrienteTorremolinos
- Rama principal: main
- Repositorio: GitHub
- Idioma principal de la interfaz: español
- Formato de fechas: ISO 8601 (yyyy-mm-dd) en base de datos
- Moneda: Q / Quetzales

## Observaciones de negocio

El sistema debe estar pensado para un residencial donde:

- cada casa o contribuyente tiene liquidez/estado financiero
- se requieren cobros y pagos del condominio
- se necesita evidencia justificativa de cada egreso
- se desea consultar la cuenta corriente por casa en un periodo

## Tareas prioritarias sugeridas

1. Definir modelo de movimientos con cuenta corriente por propiedad
2. Añadir soporte para egresos con comprobantes
3. Añadir tabla de evidencias y bitácora
4. Implementar filtros por fecha y mes calendario
5. Crear reportes de saldo inicial, ingresos, egresos y saldo final
6. Exportar reportes a Excel y PDF
7. Mejorar la interfaz de usuario
8. Añadir sincronización opcional a OneDrive/Google Drive

## Notas para la IA que continúe el trabajo

- No asumir que todo está mal; la base ya funciona.
- Priorizar cambios incrementales sobre refactors grandes.
- Mantener la compatibilidad con el flujo actual del proyecto.
- Cuando agregues tablas nuevas, conserva la lógica de auditoría ya usada.
- Si se cambian modelos, actualizar también la inicialización de SQLite.
- Mantener la app sencilla, clara y utilizable en la práctica.

## Archivos clave a revisar antes de hacer cambios

- app.py
- torremolinos/db.py
- static/styles.css
- README.md

## Instrucción final

Continúa el trabajo desde la estructura actual, preservando la funcionalidad vigente, y agrega paulatinamente los módulos de egresos con evidencia, reportes financieros, filtros por fecha y cuenta corriente por contribuyente/casa.
