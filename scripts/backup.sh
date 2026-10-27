#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${1:-/data/backups/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$BACKUP_DIR"

echo "=== Starting Gateway-Harness Appliance Backup ==="
echo "Target directory: $BACKUP_DIR"

# 1. PostgreSQL schema and data
if command -v pg_dump &> /dev/null && [ -n "${GH_DATABASE_URL:-}" ]; then
    echo "Dumping PostgreSQL metadata..."
    pg_dump "$GH_DATABASE_URL" > "$BACKUP_DIR/postgres.sql"
fi

# 2. Parquet and DuckDB archive
if [ -d "${GH_DATA_DIR:-/data}/ledger" ]; then
    echo "Archiving analytical ledger..."
    tar -czf "$BACKUP_DIR/ledger.tar.gz" -C "${GH_DATA_DIR:-/data}/ledger" .
fi

echo "Backup complete: $BACKUP_DIR"
