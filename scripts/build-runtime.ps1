param(
    [string]$Registry = "localhost:5000",
    [string]$Version = "0.1.0",
    [string]$BaseImage = "quay.io/fedora/python-312:latest",
    [string]$PypiIndex = "https://pypi.tuna.tsinghua.edu.cn/simple",
    [switch]$Push
)

$ErrorActionPreference = "Stop"
$runtimeTag = "aihr-runtime:local"
$remoteTag = "$Registry/aihr-runtime:$Version"

docker build --file Dockerfile.runtime --tag $runtimeTag `
    --build-arg "PYTHON_BASE_IMAGE=$BaseImage" `
    --build-arg "PIP_INDEX_URL=$PypiIndex" .
docker tag $runtimeTag $remoteTag

if ($Push) {
    docker push $remoteTag
    Write-Host "Pushed $remoteTag"
} else {
    Write-Host "Built $runtimeTag and tagged it as $remoteTag. Use -Push after the registry is running."
}
