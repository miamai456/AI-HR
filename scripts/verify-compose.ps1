param(
    [switch]$KeepRunning,
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

docker info | Out-Null
docker compose config --quiet
docker compose up --build -d

try {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = "Services have not reported ready yet."
    while ((Get-Date) -lt $deadline) {
        try {
            $ready = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/ready" -TimeoutSec 5
            $dashboard = Invoke-WebRequest `
                -Uri "http://localhost:8501/_stcore/health" `
                -UseBasicParsing `
                -TimeoutSec 5
            $mysql = docker compose exec -T mysql `
                mysqladmin ping -h localhost -uaihr -pCHANGE_ME
            if (
                $ready.status -eq "ready" -and
                $dashboard.StatusCode -eq 200 -and
                $mysql -match "mysqld is alive"
            ) {
                Write-Output "Compose integration passed: database, API, and dashboard are ready."
                exit 0
            }
        }
        catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }
    throw "Compose integration timed out: $lastError"
}
finally {
    if (-not $KeepRunning) {
        docker compose down
    }
}
