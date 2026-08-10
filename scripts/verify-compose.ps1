param(
    [switch]$KeepRunning,
    [int]$TimeoutSeconds = 180,
    [string]$DockerDataRoot = $env:AIHR_DOCKER_DATA_ROOT
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $DockerDataRoot) {
    throw "Set AIHR_DOCKER_DATA_ROOT to the verified Docker Desktop data directory on E:."
}
$resolvedDockerDataRoot = [System.IO.Path]::GetFullPath($DockerDataRoot)
if (
    -not $resolvedDockerDataRoot.StartsWith(
        "E:\",
        [System.StringComparison]::OrdinalIgnoreCase
    )
) {
    throw "Docker Desktop data must be located on E: before Compose integration runs."
}

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
            $postgres = docker compose exec -T postgres `
                pg_isready -U aihr -d aihr
            $prometheus = Invoke-RestMethod `
                -Uri "http://localhost:9090/api/v1/targets" `
                -TimeoutSec 5
            $grafana = Invoke-RestMethod `
                -Uri "http://localhost:3000/api/health" `
                -TimeoutSec 5
            $runningServices = docker compose ps --status running --services
            $apiTarget = $prometheus.data.activeTargets | Where-Object {
                $_.labels.job -eq "aihr-api"
            }
            if (
                $ready.status -eq "ready" -and
                $dashboard.StatusCode -eq 200 -and
                $postgres -match "accepting connections" -and
                $grafana.database -eq "ok" -and
                $apiTarget.health -eq "up" -and
                $runningServices -contains "worker"
            ) {
                Write-Output "Compose integration passed: database, API, dashboard, worker, Prometheus, and Grafana are ready."
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
