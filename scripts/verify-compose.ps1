param(
    [switch]$KeepRunning,
    [int]$TimeoutSeconds = 180,
    [string]$DockerDataRoot = $env:AIHR_DOCKER_DATA_ROOT,
    [int]$ApiPort = 0,
    [int]$DashboardPort = 0,
    [int]$PrometheusPort = 0,
    [int]$GrafanaPort = 0
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Resolve-ServicePort {
    param(
        [int]$ExplicitPort,
        [string]$EnvironmentVariable,
        [int]$DefaultPort
    )
    if ($ExplicitPort -gt 0) {
        return $ExplicitPort
    }
    $environmentValue = [Environment]::GetEnvironmentVariable($EnvironmentVariable)
    if ($environmentValue) {
        return [int]$environmentValue
    }
    return $DefaultPort
}

$ApiPort = Resolve-ServicePort $ApiPort "AIHR_API_HOST_PORT" 8000
$DashboardPort = Resolve-ServicePort $DashboardPort "AIHR_DASHBOARD_HOST_PORT" 8501
$PrometheusPort = Resolve-ServicePort $PrometheusPort "AIHR_PROMETHEUS_HOST_PORT" 9090
$GrafanaPort = Resolve-ServicePort $GrafanaPort "AIHR_GRAFANA_HOST_PORT" 3000
$expectedServices = @(
    "api",
    "cache",
    "dashboard",
    "grafana",
    "otel-collector",
    "postgres",
    "prometheus",
    "tempo",
    "worker"
)

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

try {
    docker compose up --build -d
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed to start every service."
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = "Services have not reported ready yet."
    while ((Get-Date) -lt $deadline) {
        try {
            $ready = Invoke-RestMethod `
                -Uri "http://localhost:$ApiPort/api/v1/ready" `
                -TimeoutSec 5
            $dashboard = Invoke-WebRequest `
                -Uri "http://localhost:$DashboardPort/_stcore/health" `
                -UseBasicParsing `
                -TimeoutSec 5
            $postgres = docker compose exec -T postgres `
                pg_isready -U aihr -d aihr
            $prometheus = Invoke-RestMethod `
                -Uri "http://localhost:$PrometheusPort/api/v1/targets" `
                -TimeoutSec 5
            $grafana = Invoke-RestMethod `
                -Uri "http://localhost:$GrafanaPort/api/health" `
                -TimeoutSec 5
            $runningServices = @(docker compose ps --status running --services)
            $missingServices = @(
                $expectedServices | Where-Object { $runningServices -notcontains $_ }
            )
            $apiTarget = $prometheus.data.activeTargets | Where-Object {
                $_.labels.job -eq "aihr-api"
            }
            if (
                $ready.status -eq "ready" -and
                $dashboard.StatusCode -eq 200 -and
                $postgres -match "accepting connections" -and
                $grafana.database -eq "ok" -and
                $apiTarget.health -eq "up" -and
                $missingServices.Count -eq 0
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
