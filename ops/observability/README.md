# AIHR observability runtime

All persistent runtime data and deployment secrets are kept outside the repository
under E:\AIHRData. The Compose stack does not intentionally bind any service data
to the C drive.

Initialize directories and secret files without overwriting existing values:

    .\scripts\initialize-runtime.ps1

The stack provides:

- Prometheus on port 9090 for API and Collector metrics plus alert rules.
- Grafana on port 3000 with a provisioned Prometheus datasource and AIHR dashboard.
- OpenTelemetry Collector for OTLP traces from the FastAPI service, persisted in Tempo.
- RQ worker backed by Redis for analysis-context prewarming.

Tempo exposes an API rather than a browser landing page, so its root URL returning
`404 page not found` is expected. Check the service at
`http://127.0.0.1:3200/status/services`; inspect traces from Grafana Explore after
selecting the provisioned Tempo datasource. Trace storage is under
`E:\AIHRData\tempo`; the Collector's debug exporter remains enabled for local
diagnostics.

Do not start Docker Desktop until its engine data location has also been moved to an
E-drive directory. Compose bind mounts do not relocate Docker Desktop's own image and
VM storage.

## Restricted registry networks

Build `aihr-runtime` once with `scripts\build-runtime.ps1`. The script uses the
configured PyPI mirror (default `https://pypi.tuna.tsinghua.edu.cn/simple`) and
can push to the local registry in `ops\registry`. API and dashboard images then
reuse `AIHR_RUNTIME_IMAGE` instead of reinstalling scientific Python packages.

Container dependency installation uses a 300-second pip read timeout and retries.
For a shared deployment, replace the local registry with a TLS/authenticated
private registry and set `AIHR_RUNTIME_IMAGE` to its versioned image reference.
