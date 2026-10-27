#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "${SCRIPT_DIR}/../compose" && pwd)"

echo "==> Gateway Harness Appliance: Bootstrap Check"

# 1. Verify Docker and Docker Compose v2
if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is required but not installed or not in PATH." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Error: docker compose (v2) is required." >&2
  exit 1
fi

# 2. Setup .env file
ENV_FILE="${COMPOSE_DIR}/.env"
if [ ! -f "${ENV_FILE}" ]; then
  echo "==> Generating new .env from .env.example with secure random credentials..."
  cp "${COMPOSE_DIR}/.env.example" "${ENV_FILE}"

  RAND_PG_PASS="$(openssl rand -hex 16)"
  RAND_LITELLM_KEY="sk-gh-$(openssl rand -hex 16)"
  RAND_ADMIN_TOKEN="gh-admin-$(openssl rand -hex 16)"

  sed -i.bak \
    -e "s/change-me-to-a-secure-postgres-password/${RAND_PG_PASS}/g" \
    -e "s/sk-gh-change-me-to-a-secure-random-key/${RAND_LITELLM_KEY}/g" \
    -e "s/gh-admin-change-me-to-a-secure-random-token/${RAND_ADMIN_TOKEN}/g" \
    "${ENV_FILE}"
  rm -f "${ENV_FILE}.bak"
  echo "==> Generated ${ENV_FILE}"
else
  echo "==> Existing .env file found; preserving existing credentials."
fi

# 3. Launch Docker Compose
echo "==> Starting Gateway Harness Appliance services..."
cd "${COMPOSE_DIR}"
docker compose up -d

echo "==> Gateway Harness Appliance started successfully!"
echo "    - LiteLLM Gateway: http://localhost:4000/v1"
echo "    - Admin Dashboard: http://localhost:8100"
