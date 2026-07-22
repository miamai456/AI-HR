$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"
$logs = Join-Path $root "logs"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment not found. Run: python -m venv .venv"
}

New-Item -ItemType Directory -Force -Path $logs | Out-Null

$api = Start-Process $python `
    -ArgumentList "-m", "uvicorn", "aihr.api.main:app", "--port", "8000" `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "api.out.log") `
    -RedirectStandardError (Join-Path $logs "api.err.log") `
    -PassThru

$dashboard = Start-Process $python `
    -ArgumentList "-m", "streamlit", "run", "app/Home.py", "--server.port", "8501" `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logs "dashboard.out.log") `
    -RedirectStandardError (Join-Path $logs "dashboard.err.log") `
    -PassThru

Set-Content -Path (Join-Path $logs "api.pid") -Value $api.Id
Set-Content -Path (Join-Path $logs "dashboard.pid") -Value $dashboard.Id

Write-Output "API PID: $($api.Id)"
Write-Output "Dashboard PID: $($dashboard.Id)"
Write-Output "Dashboard: http://localhost:8501"
Write-Output "API docs: http://localhost:8000/docs"
