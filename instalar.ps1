# Instala TikTok Pulse en Windows (PowerShell):  .\instalar.ps1
# Si Windows bloquea el script:  powershell -ExecutionPolicy Bypass -File .\instalar.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "== TikTok Pulse · instalación =="

$py = $null
foreach ($cand in @("py -3", "python")) {
    try {
        $ok = & cmd /c "$cand -c `"import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)`"" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $cand; break }
    } catch {}
}
if (-not $py) {
    Write-Host "❌ Necesitas Python 3.10 o superior. Instálalo desde https://www.python.org/downloads/ (marca 'Add python.exe to PATH') y vuelve a correr este script."
    exit 1
}
Write-Host "✅ Usando $(cmd /c "$py --version")"

if (-not (Test-Path ".venv")) {
    Write-Host "→ Creando entorno virtual .venv"
    cmd /c "$py -m venv .venv"
}
Write-Host "→ Instalando dependencias (1–2 minutos)"
& .\.venv\Scripts\python.exe -m pip install -q --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt

if (-not (Test-Path ".env")) {
    Copy-Item .env.example .env
    Write-Host ""
    Write-Host "⚠️  Se creó el archivo .env. Ábrelo con el Bloc de notas y llena tus llaves:"
    Write-Host "    APIFY_TOKEN y OPENAI_API_KEY (o las variables AZURE_OPENAI_*)."
    Write-Host "    Mientras tanto puedes probar con modo_prueba: true (sin costo)."
}

Write-Host ""
Write-Host "== Diagnóstico =="
$env:PYTHONIOENCODING = "utf-8"
& .\.venv\Scripts\python.exe run.py doctor
Write-Host ""
Write-Host "Siguiente paso: .\iniciar.ps1  (abre el Swagger en el navegador)"
