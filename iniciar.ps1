# Arranca TikTok Pulse y abre el Swagger en Windows:  .\iniciar.ps1   (Ctrl+C para detener)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    Write-Host "❌ Falta la instalación. Corre primero: .\instalar.ps1"
    exit 1
}

$port = if ($env:PORT) { $env:PORT } else { "8000" }
$url = "http://localhost:$port/docs"
Write-Host "== TikTok Pulse en $url  (Ctrl+C para detener) =="
$env:PYTHONIOENCODING = "utf-8"

Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 3; Start-Process $u } -ArgumentList $url | Out-Null
& .\.venv\Scripts\python.exe -m uvicorn tiktok_agent.api:app --port $port
