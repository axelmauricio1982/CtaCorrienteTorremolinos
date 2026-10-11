param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Name = "Torremolinos"
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

$obsoleteExecutables = @(
    (Join-Path $projectRoot "dist\Torremolinos-actualizado.exe"),
    (Join-Path $projectRoot "dist\Torremolinos-sync-corregido.exe")
)
foreach ($obsoleteExecutable in $obsoleteExecutables) {
    if (Test-Path -LiteralPath $obsoleteExecutable) {
        Remove-Item -LiteralPath $obsoleteExecutable -Force
    }
}

Write-Host ""
Write-Host "Ejecutable creado en: dist\$Name.exe"
Write-Host "Base unica del proyecto: data\torremolinos.sqlite3"
