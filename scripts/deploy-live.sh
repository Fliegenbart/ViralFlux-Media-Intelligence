#!/usr/bin/env bash
# Production deployment script with health checks and rollback
set -euo pipefail

REPO="${REPO:-/opt/viralflux-media-intelligence-clean}"
BRANCH="${BRANCH:-main}"
PROJECT="${PROJECT:-viralflux-media-intelligence-clean}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
NETWORK="${PROJECT}_virusradar_network"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"
MAX_HEALTH_RETRIES=15
HEALTH_INTERVAL=4

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

# ── Lock: prevent concurrent deploys ───────────────────────────
LOCKFILE="/var/run/viralflux-deploy.lock"
exec 200>"$LOCKFILE"
if ! flock -n 200; then
    echo "ERROR: Another deployment is already in progress." >&2
    exit 1
fi

cd "$REPO"

# ── Save current state for rollback ────────────────────────────
PREV_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
echo "[$(date)] Current commit: $PREV_COMMIT"

# ── Pull latest code ───────────────────────────────────────────
echo "[$(date)] Fetching $BRANCH..."
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"
NEW_COMMIT=$(git rev-parse HEAD)
echo "[$(date)] Deploying commit: $NEW_COMMIT"

# ── Build frontend image ───────────────────────────────────────
echo "[$(date)] Building frontend image..."
docker build -t viralflux-media-frontend -f docker/Dockerfile.frontend .

# ── Ensure network exists ──────────────────────────────────────
docker compose --project-directory "$REPO" -p "$PROJECT" -f "$COMPOSE_FILE" up -d --no-deps frontend-prod >/dev/null 2>&1 || true

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
    echo "ERROR: Docker network missing: $NETWORK" >&2
    exit 1
fi

# ── Connect infra containers ──────────────────────────────────
for infra in "${INFRA_CONTAINERS[@]}"; do
    if ! docker inspect "$infra" >/dev/null 2>&1; then
        echo "ERROR: Required infra container missing: $infra" >&2
        exit 1
    fi
    docker network connect "$NETWORK" "$infra" >/dev/null 2>&1 || true
done

# ── Deploy app containers ─────────────────────────────────────
echo "[$(date)] Deploying app containers..."
docker rm -f "${APP_CONTAINERS[@]}" >/dev/null 2>&1 || true
docker compose --project-directory "$REPO" -p "$PROJECT" -f "$COMPOSE_FILE" up -d --no-deps frontend-prod backend celery_worker celery_beat

# ── Health check ───────────────────────────────────────────────
echo "[$(date)] Waiting for backend health check..."
HEALTHY=false
for i in $(seq 1 $MAX_HEALTH_RETRIES); do
    sleep "$HEALTH_INTERVAL"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        HEALTHY=true
        echo "[$(date)] Health check passed (attempt $i/$MAX_HEALTH_RETRIES)"
        break
    fi
    echo "[$(date)] Health check attempt $i/$MAX_HEALTH_RETRIES: HTTP $HTTP_CODE"
done

if [ "$HEALTHY" = false ]; then
    echo "[$(date)] ERROR: Health check failed after $MAX_HEALTH_RETRIES attempts!" >&2
    echo "[$(date)] Rolling back to $PREV_COMMIT..." >&2

    # Rollback: reset to previous commit and redeploy
    git reset --hard "$PREV_COMMIT"
    docker rm -f "${APP_CONTAINERS[@]}" >/dev/null 2>&1 || true
    docker compose --project-directory "$REPO" -p "$PROJECT" -f "$COMPOSE_FILE" up -d --no-deps frontend-prod backend celery_worker celery_beat

    echo "[$(date)] Rollback complete. Deployed commit: $PREV_COMMIT" >&2
    exit 1
fi

# ── Show status ────────────────────────────────────────────────
echo ""
echo "=== Deployment successful ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'virusradar_frontend_prod|virusradar_backend|viralflux_celery_worker|viralflux_celery_beat'
echo ""
echo "Commit: $NEW_COMMIT"
echo "Time:   $(date)"
