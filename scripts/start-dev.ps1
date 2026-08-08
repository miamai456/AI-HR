$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$preferredPython = "E:\conda_envs\aihr\python.exe"
$localPython = Join-Path $root ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $preferredPython) { $preferredPython } else { $localPython }
$logs = Join-Path $root "logs"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found. Expected: $preferredPython or $localPython"
}

function Get-PortOwner {
    param([int]$Port)

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Confirm-AihrProcess {
    param(
        [int]$ProcessId,
        [string]$ExpectedCommand,
        [int]$Port
    )

    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId"
    if (-not $process -or $process.CommandLine -notmatch [regex]::Escape($ExpectedCommand)) {
        throw "Port $Port is already used by another process (PID $ProcessId)."
    }
    return Get-Process -Id $ProcessId
}

function Wait-ForListener {
    param(
        [System.Diagnostics.Process]$Process,
        [int]$Port,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) {
            throw "Process $($Process.Id) exited before port $Port became ready. Check logs."
        }
        $owner = Get-PortOwner -Port $Port
        if ($owner -eq $Process.Id) { return }
        Start-Sleep -Milliseconds 250
    }
    throw "Timed out waiting for process $($Process.Id) to listen on port $Port."
}

function Start-OrReuseAihrProcess {
    param(
        [string]$Name,
        [int]$Port,
        [string]$ExpectedCommand,
        [string[]]$Arguments,
        [string]$OutputLog,
        [string]$ErrorLog
    )

    $owner = Get-PortOwner -Port $Port
    if ($owner) {
        $existing = Confirm-AihrProcess -ProcessId $owner -ExpectedCommand $ExpectedCommand -Port $Port
        Write-Host "Reusing $Name PID: $($existing.Id)"
        return $existing
    }

    $process = Start-Process $python `
        -ArgumentList $Arguments `
        -WindowStyle Hidden `
        -RedirectStandardOutput $OutputLog `
        -RedirectStandardError $ErrorLog `
        -PassThru
    Wait-ForListener -Process $process -Port $Port
    Write-Host "Started $Name PID: $($process.Id)"
    return $process
}

New-Item -ItemType Directory -Force -Path $logs | Out-Null
$env:AIHR_CONFIG_FILE = "config/config.ini"
$env:AIHR_API_URL = "http://127.0.0.1:8000/api/v1"

$api = Start-OrReuseAihrProcess `
    -Name "API" `
    -Port 8000 `
    -ExpectedCommand "uvicorn aihr.api.main:app" `
    -Arguments @("-m", "uvicorn", "aihr.api.main:app", "--port", "8000") `
    -OutputLog (Join-Path $logs "api.out.log") `
    -ErrorLog (Join-Path $logs "api.err.log")

$dashboard = Start-OrReuseAihrProcess `
    -Name "Dashboard" `
    -Port 8501 `
    -ExpectedCommand "streamlit run app/Home.py" `
    -Arguments @("-m", "streamlit", "run", "app/Home.py", "--server.port", "8501") `
    -OutputLog (Join-Path $logs "dashboard.out.log") `
    -ErrorLog (Join-Path $logs "dashboard.err.log")

Set-Content -Path (Join-Path $logs "api.pid") -Value $api.Id
Set-Content -Path (Join-Path $logs "dashboard.pid") -Value $dashboard.Id

Write-Output "Dashboard: http://localhost:8501"
Write-Output "API docs: http://localhost:8000/docs"
