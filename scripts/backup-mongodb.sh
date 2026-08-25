#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup_root="${AIHR_BACKUP_DIR:-$project_dir/backups/mongodb}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$backup_root/$timestamp"

mkdir -p "$target"
docker compose -f "$project_dir/compose.yaml" exec -T mongo \
    mongodump --db "${AIHR_MONGO_DATABASE:-aihr_documents}" --archive --gzip \
    > "$target/aihr_documents.archive.gz"
sha256sum "$target/aihr_documents.archive.gz" > "$target/SHA256SUMS"
printf 'MongoDB backup created: %s\n' "$target"
