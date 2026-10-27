#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${1:-}"
if [ -z "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
    echo "Usage: ./scripts/restore.sh <backup_dir>"
    exit 1
fi

echo "=== Starting Gateway-Harness Appliance Restore ==="
echo "Source directory: $BACKUP_DIR"

# 1. Restore PostgreSQL
if [ -f "$BACKUP_DIR/postgres.sql" ] && command -v psql &> /dev/null && [ -n "${GH_DATABASE_URL:-}" ]; then
    echo "Restoring PostgreSQL database..."
    psql "$GH_DATABASE_URL" < "$BACKUP_DIR/postgres.sql"
fi

# 2. Restore Ledger
if [ -f "$BACKUP_DIR/ledger.tar.gz" ]; then
    TARGET_DIR="${GH_DATA_DIR:-/data}/ledger"
    mkdir -p "$TARGET_DIR"
    echo "Restoring analytical ledger to $TARGET_DIR..."
    tar -xzf "$BACKUP_DIR/ledger.tar.gz" -C "$TARGET_DIR"
fi

echo "Restore completed successfully."
