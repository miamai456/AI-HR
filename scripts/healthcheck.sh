#!/usr/bin/env bash
set -euo pipefail

api_url="${AIHR_API_PUBLIC_URL:-http://localhost:${AIHR_API_HOST_PORT:-8000}}"
frontend_url="${AIHR_FRONTEND_PUBLIC_URL:-http://localhost:${AIHR_FRONTEND_HOST_PORT:-5173}}"

check_url() {
    local name="$1"
    local url="$2"
    local attempts=20
    while (( attempts > 0 )); do
        if curl --fail --silent --show-error "$url" >/dev/null; then
            printf '%s: ready (%s)\n' "$name" "$url"
            return 0
        fi
        attempts=$((attempts - 1))
        sleep 2
    done
    printf '%s: unavailable (%s)\n' "$name" "$url" >&2
    return 1
}

check_url "api" "$api_url/api/v1/ready"
check_url "document-store" "$api_url/api/v1/documents/status"
check_url "frontend" "$frontend_url/health"
