#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-/opt/viralflux-media-intelligence-clean}"
BRANCH="${BRANCH:-main}"
PROJECT="${PROJECT:-viralflux-media-intelligence-clean}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
NETWORK="${PROJECT}_virusradar_network"
APP_CONTAINERS=(
  virusradar_frontend_prod
  virusradar_backend
  viralflux_celery_worker
  viralflux_celery_beat
)
INFRA_CONTAINERS=(
  virusradar_db
  viralflux_redis
)

cd "$REPO"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

# Build the static frontend image used by frontend-prod.
docker build -t viralflux-media-frontend -f docker/Dockerfile.frontend .

# Bootstrap the clean compose network if the app stack is not present yet.
docker compose --project-directory "$REPO" -p "$PROJECT" -f "$COMPOSE_FILE" up -d --no-deps frontend-prod >/dev/null 2>&1 || true

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  echo "Expected Docker network missing: $NETWORK" >&2
  exit 1
fi

for infra in "${INFRA_CONTAINERS[@]}"; do
  if ! docker inspect "$infra" >/dev/null 2>&1; then
    echo "Required infra container missing: $infra" >&2
    exit 1
  fi
  docker network connect "$NETWORK" "$infra" >/dev/null 2>&1 || true
done

docker rm -f "${APP_CONTAINERS[@]}" >/dev/null 2>&1 || true

docker compose --project-directory "$REPO" -p "$PROJECT" -f "$COMPOSE_FILE" up -d --no-deps frontend-prod backend celery_worker celery_beat
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'virusradar_frontend_prod|virusradar_backend|viralflux_celery_worker|viralflux_celery_beat'
