# AIHR private registry

This is a local registry for the development machine. It listens only on
`127.0.0.1:5000` and stores image layers under `E:\AIHRData\registry`.

Start it from the repository root:

```powershell
docker compose -f ops/registry/compose.yaml up -d
.
scripts/build-runtime.ps1 -Push
```

The registry is intentionally not exposed to the LAN and has no TLS or basic
auth. Do not bind it to `0.0.0.0` or use it for a shared/production registry
without adding TLS and authentication.
