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
- Descargar recibos PDF con sus evidencias anexas
- Exportar información en CSV
- Guardar evidencias localmente y sincronizarlas opcionalmente con OneDrive Personal

## Requisitos

- Python 3.10 o superior
- No requiere dependencias externas adicionales para esta versión inicial

Para descargar recibos PDF con evidencias, instala las dependencias del proyecto:

```bash
python3 -m pip install -r requirements.txt
```

## Ejecutar el proyecto

```bash
python3 app.py
```

Luego abre esta dirección en el navegador:

```text
http://127.0.0.1:8000
```

## Ejecutable para Windows

Para generar una versión portátil que no requiera una instalación separada de Python:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

El resultado queda en `dist\Torremolinos.exe`. Al abrirlo, inicia el servidor y
abre automáticamente la aplicación en el navegador. La base de datos y los
comprobantes se conservan en `dist\data`, fuera del ejecutable, para que no se
pierdan al actualizarlo.

Al recompilar, el constructor conserva cualquier base que ya exista dentro de
`dist\data` y agrega las evidencias disponibles en el proyecto.

No muevas solamente `Torremolinos.exe` después de comenzar a usarlo: mueve toda
la carpeta `dist` para conservar también la base y las evidencias.

## Linux y macOS

Para iniciar directamente con Python en Linux o macOS:

```bash
bash ./iniciar_torremolinos.sh
```

Para generar un ejecutable autónomo nativo del sistema actual:

```bash
bash ./build_unix.sh
```

El resultado queda en `dist/Torremolinos`. PyInstaller no genera binarios
multiplataforma: el ejecutable de Linux debe construirse en Linux y el de macOS
debe construirse en macOS. En ambos casos la base y las evidencias permanecen
en `dist/data` y utilizan el mismo flujo Push/Pull que Windows.

## OneDrive Personal

La aplicación conserva cada comprobante en `data/attachments/` y puede cargarlo directamente a OneDrive Personal mediante Microsoft Graph. La aplicación registrada usa:

```text
Client ID: 783c3d89-46d0-4280-b8b9-0fdfcd88aab1
Permiso: Files.ReadWrite.AppFolder
```

Este permiso limita el acceso a la carpeta privada de `CtaCorrienteTorremolinos`. La contraseña nunca se entrega a la aplicación: el acceso se autoriza con el flujo de código de dispositivo de Microsoft. El token se guarda únicamente en `.onedrive-token-cache.json`, con permisos locales restringidos, y ese archivo está excluido de Git.

Después de instalar las dependencias e iniciar el servidor, abre **Inicio > Configurar OneDrive > Conectar OneDrive Personal**. Microsoft mostrará un código y solicitará el consentimiento la primera vez.

Como compatibilidad adicional, si existe un cliente de OneDrive instalado, la aplicación también puede copiar el archivo a la carpeta sincronizada:

```text
/Users/axll/OneDrive/Torremolinos/Evidencias
```

La ruta predeterminada es `OneDrive/Torremolinos/Evidencias`. Para usar otra ubicación, configura `ONEDRIVE_LOCAL_FOLDER` antes de iniciar la aplicación.

macOS/Linux:

```bash
export ONEDRIVE_LOCAL_FOLDER="$HOME/OneDrive"
python3 app.py
```

Windows PowerShell:

```powershell
$env:ONEDRIVE_LOCAL_FOLDER = "$HOME\OneDrive"
python app.py
```

Si no hay conexión ni carpeta local disponible, el comprobante permanece guardado localmente y queda marcado como pendiente. En el siguiente **Push de datos**, la aplicación reintenta primero la carga directa a OneDrive y solamente después respalda la base y las evidencias en GitHub.

## Sincronización de datos con GitHub

Los botones de sincronización utilizan la rama independiente `data-sync` para mantener los datos separados del código fuente:

- **Push de datos:** vuelve a intentar la carga directa a OneDrive de las evidencias pendientes y publica en GitHub solamente `data/torremolinos.sqlite3` y `data/attachments/`.
- **Pull de datos:** restaura `data/torremolinos.sqlite3` y descarga las evidencias respaldadas que falten o hayan cambiado. No modifica el código fuente ni elimina evidencias locales adicionales.

La rama `data-sync` siempre usa esas rutas canónicas, tanto al ejecutar desde
Python como desde el `.exe`. Las rutas locales guardadas en Windows, Linux o
macOS se normalizan automáticamente al directorio de datos de la instalación actual.

Cuando se utiliza Microsoft Graph, la aplicación guarda el identificador remoto y la fecha de sincronización únicamente después de que OneDrive confirma el tamaño completo del archivo. Cuando se utiliza el cliente local de OneDrive, la aplicación considera sincronizada la evidencia al verificar que la carpeta configurada contiene un archivo con el mismo nombre y tamaño; OneDrive se encarga de replicar después esa carpeta entre los equipos.

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
