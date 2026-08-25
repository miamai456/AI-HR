#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"

docker compose up --build -d postgres mongo cache api worker dashboard frontend
docker compose ps
"$project_dir/scripts/healthcheck.sh"
docker compose exec -T api python scripts/index_knowledge_documents.py
