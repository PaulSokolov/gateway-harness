#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:-gateway}"
shift || true

case "${ROLE}" in
  gateway)
    exec litellm --config /app/config/litellm.yaml --port 4000 --num_workers "${GH_WORKERS:-4}" "$@"
    ;;
  worker)
    exec python -m gateway_harness.worker.scheduler "$@"
    ;;
  admin)
    exec uvicorn gateway_harness.admin.app:app --host 0.0.0.0 --port 8100 "$@"
    ;;
  migrate)
    exec python -m gateway_harness.db.pg migrate "$@"
    ;;
  *)
    echo "Unknown appliance role: ${ROLE}. Allowed: gateway | worker | admin | migrate" >&2
    exit 2
    ;;
esac
