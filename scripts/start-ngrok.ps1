param(
    [int]$Port = 8501,
    [string]$DataRoot = "E:\AIHRData"
)

$ErrorActionPreference = "Stop"
$resolvedRoot = [System.IO.Path]::GetFullPath($DataRoot)
if (-not $resolvedRoot.StartsWith("E:\", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "ngrok runtime data and configuration must stay on the E: drive."
}

$ngrokDirectory = Join-Path $resolvedRoot "ngrok"
$configPath = Join-Path $ngrokDirectory "ngrok.yml"
$logPath = Join-Path $ngrokDirectory "ngrok.log"
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "ngrok configuration not found: $configPath"
}

$portCheck = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -WarningAction SilentlyContinue
if (-not $portCheck.TcpTestSucceeded) {
    throw "No dashboard service is listening on 127.0.0.1:$Port."
}

$existingTunnel = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "ngrok.exe" -and $_.CommandLine -match "\bhttp\s+$Port\b"
}
if ($existingTunnel) {
    Write-Output "ngrok is already forwarding http://localhost:$Port"
    exit 0
}

$ngrokCommand = Get-Command ngrok.exe -ErrorAction Stop
$process = New-Object System.Diagnostics.ProcessStartInfo
$process.FileName = $ngrokCommand.Source
$process.Arguments = "http $Port --config `"$configPath`" --log `"$logPath`" --log-format json"
$process.UseShellExecute = $false
$process.CreateNoWindow = $true
[void]$process.EnvironmentVariables.Remove("HTTP_PROXY")
[void]$process.EnvironmentVariables.Remove("HTTPS_PROXY")
[void]$process.EnvironmentVariables.Remove("ALL_PROXY")
[void][System.Diagnostics.Process]::Start($process)

Start-Sleep -Seconds 3
$tunnels = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels"
$publicUrl = $tunnels.tunnels |
    Where-Object { $_.config.addr -eq "http://localhost:$Port" } |
    Select-Object -First 1 -ExpandProperty public_url
if (-not $publicUrl) {
    throw "ngrok started but did not publish port $Port. Check $logPath."
}

Write-Output "Dashboard tunnel: $publicUrl"
Write-Output "Target: http://localhost:$Port"
