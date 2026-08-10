param(
    [string]$DataRoot = "E:\AIHRData",
    [string]$DeepSeekApiKey = ""
)

$ErrorActionPreference = "Stop"
$resolvedRoot = [System.IO.Path]::GetFullPath($DataRoot)
if (-not $resolvedRoot.StartsWith("E:\", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "AIHR runtime data must be initialized on the E: drive."
}

$runtimeDirectories = @(
    $resolvedRoot,
    (Join-Path $resolvedRoot "grafana"),
    (Join-Path $resolvedRoot "otel"),
    (Join-Path $resolvedRoot "postgres"),
    (Join-Path $resolvedRoot "prometheus"),
    (Join-Path $resolvedRoot "redis"),
    (Join-Path $resolvedRoot "secrets"),
    (Join-Path $resolvedRoot "tmp")
)
foreach ($directory in $runtimeDirectories) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

function New-RandomSecret {
    param([int]$ByteCount = 32)

    $bytes = New-Object byte[] $ByteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Write-SecretIfMissing {
    param(
        [string]$Path,
        [string]$Value
    )

    if (Test-Path -LiteralPath $Path) {
        Write-Host "kept: $Path"
        return
    }
    [System.IO.File]::WriteAllText(
        $Path,
        $Value,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "created: $Path"
}

if (-not $DeepSeekApiKey) {
    $localSecrets = Join-Path $PSScriptRoot "..\.streamlit\secrets.toml"
    if (Test-Path -LiteralPath $localSecrets) {
        $contents = Get-Content -LiteralPath $localSecrets -Raw
        $match = [regex]::Match(
            $contents,
            '(?m)^\s*AIHR_ASSISTANT_API_KEY\s*=\s*["'']([^"'']+)["'']\s*$'
        )
        if ($match.Success) {
            $DeepSeekApiKey = $match.Groups[1].Value
        }
    }
}
if (-not $DeepSeekApiKey) {
    throw "DeepSeek key not found. Pass -DeepSeekApiKey or configure .streamlit/secrets.toml."
}

$secretRoot = Join-Path $resolvedRoot "secrets"
Write-SecretIfMissing (Join-Path $secretRoot "deepseek_api_key") $DeepSeekApiKey
Write-SecretIfMissing (Join-Path $secretRoot "operations_token") (New-RandomSecret)
Write-SecretIfMissing (Join-Path $secretRoot "postgres_password") (New-RandomSecret)
Write-SecretIfMissing (Join-Path $secretRoot "grafana_admin_password") (New-RandomSecret)
