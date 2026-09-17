param(
    [switch]$SkipInstall,
    [string]$Name = "Torremolinos"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

if (-not $IsWindows -and $PSVersionTable.PSEdition -eq "Core") {
    throw "Este script genera el ejecutable de Windows y debe ejecutarse en Windows."
}

if (-not $SkipInstall) {
    python -m pip install -r requirements.txt -r requirements-build.txt
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudieron instalar las dependencias de compilacion."
    }
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name $Name `
    --add-data "static;static" `
    --hidden-import fitz `
    --hidden-import pymupdf `
    --collect-all reportlab `
    --collect-all msal `
    app.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller no pudo generar el ejecutable."
}

$dataDirectory = Join-Path $projectRoot "dist\data"
$attachmentsDirectory = Join-Path $dataDirectory "attachments"
New-Item -ItemType Directory -Force -Path $attachmentsDirectory | Out-Null

$database = Join-Path $projectRoot "data\torremolinos.sqlite3"
$packagedDatabase = Join-Path $dataDirectory "torremolinos.sqlite3"
if ((Test-Path -LiteralPath $database) -and -not (Test-Path -LiteralPath $packagedDatabase)) {
    Copy-Item -LiteralPath $database -Destination $packagedDatabase
}

$sourceAttachments = Join-Path $projectRoot "data\attachments"
if (Test-Path -LiteralPath $sourceAttachments) {
    Copy-Item -Path (Join-Path $sourceAttachments "*") -Destination $attachmentsDirectory -Recurse -Force
}

Write-Host ""
Write-Host "Ejecutable creado en: dist\$Name.exe"
Write-Host "Los datos persistentes se guardan en: dist\data"
