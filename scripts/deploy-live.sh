#!/usr/bin/env bash
# Production deployment script with health checks and rollback.
# The canonical live stack on fluxengine.labpulse.ai is defined in docker-compose.prod.yml.
set -euo pipefail

REPO="${REPO:-/opt/viralflux-media-intelligence-clean}"
BRANCH="${BRANCH:-main}"
PROJECT="${PROJECT:-viralflux-media-intelligence-clean}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health/live}"
READY_URL="${READY_URL:-http://localhost:8000/health/ready}"
MAX_HEALTH_RETRIES=15
HEALTH_INTERVAL=4
REQUIRED_COMPOSE_BASENAME="docker-compose.prod.yml"

APP_CONTAINERS=(
  virusradar_frontend_prod
  virusradar_backend
  viralflux_celery_worker
  viralflux_celery_beat
)
APP_SERVICES=(
  frontend-prod
  backend
  celery_worker
  celery_beat
)
INFRA_SERVICES=(
  db
  redis
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
echo "[$(date)] Using compose file: $COMPOSE_FILE"

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "ERROR: Compose file not found: $COMPOSE_FILE" >&2
    exit 1
fi

if [ "${ALLOW_DEV_COMPOSE_LIVE:-false}" != "true" ] && [ "$(basename "$COMPOSE_FILE")" != "$REQUIRED_COMPOSE_BASENAME" ]; then
    echo "ERROR: Live deploy refuses non-production compose file: $COMPOSE_FILE" >&2
    exit 1
fi

compose() {
    docker compose --project-directory "$REPO" -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}

assert_live_mode_guards() {
    local container="$1"
    local env_dump
    env_dump=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$container")

    printf '%s\n' "$env_dump" | grep -qx 'ENVIRONMENT=production' || {
        echo "ERROR: $container is not running with ENVIRONMENT=production" >&2
        return 1
    }
    printf '%s\n' "$env_dump" | grep -qx 'DB_AUTO_CREATE_SCHEMA=false' || {
        echo "ERROR: $container still allows DB_AUTO_CREATE_SCHEMA" >&2
        return 1
    }
    printf '%s\n' "$env_dump" | grep -qx 'DB_ALLOW_RUNTIME_SCHEMA_UPDATES=false' || {
        echo "ERROR: $container still allows runtime schema updates" >&2
        return 1
    }
}

assert_backend_readiness_flags() {
    local env_dump
    env_dump=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' virusradar_backend)

    printf '%s\n' "$env_dump" | grep -qx 'STARTUP_STRICT_READINESS=true' || {
        echo "ERROR: backend is not running with STARTUP_STRICT_READINESS=true" >&2
        return 1
    }
    printf '%s\n' "$env_dump" | grep -qx 'READINESS_REQUIRE_BROKER=true' || {
        echo "ERROR: backend is not running with READINESS_REQUIRE_BROKER=true" >&2
        return 1
    }
}

assert_no_bind_mounts() {
    local container="$1"
    local bind_count
    bind_count=$(docker inspect -f '{{range .Mounts}}{{if eq .Type "bind"}}bind{{println}}{{end}}{{end}}' "$container" | grep -c '^bind$' || true)
    if [ "$bind_count" -gt 0 ]; then
        echo "ERROR: $container still uses host bind mounts in live mode" >&2
        return 1
    fi
}

# ── Build frontend image ───────────────────────────────────────
echo "[$(date)] Building frontend image..."
docker build -t viralflux-media-frontend -f docker/Dockerfile.frontend .

# ── Build backend/runtime images ───────────────────────────────
echo "[$(date)] Building backend runtime images..."
compose build backend celery_worker celery_beat

# ── Bring up infra first ───────────────────────────────────────
echo "[$(date)] Ensuring infra services are up..."
compose up -d "${INFRA_SERVICES[@]}"

# ── Deploy app containers ─────────────────────────────────────
echo "[$(date)] Deploying app containers..."
docker rm -f "${APP_CONTAINERS[@]}" >/dev/null 2>&1 || true
compose up -d --no-deps "${APP_SERVICES[@]}"

assert_live_mode_guards virusradar_backend
assert_live_mode_guards viralflux_celery_worker
assert_live_mode_guards viralflux_celery_beat
assert_backend_readiness_flags
assert_no_bind_mounts virusradar_backend
assert_no_bind_mounts viralflux_celery_worker
assert_no_bind_mounts viralflux_celery_beat
assert_no_bind_mounts virusradar_frontend_prod

# ── Liveness check ─────────────────────────────────────────────
echo "[$(date)] Waiting for backend liveness check..."
HEALTHY=false
for i in $(seq 1 $MAX_HEALTH_RETRIES); do
    sleep "$HEALTH_INTERVAL"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        HEALTHY=true
        echo "[$(date)] Liveness check passed (attempt $i/$MAX_HEALTH_RETRIES)"
        break
    fi
    echo "[$(date)] Liveness check attempt $i/$MAX_HEALTH_RETRIES: HTTP $HTTP_CODE"
done

if [ "$HEALTHY" = false ]; then
    echo "[$(date)] ERROR: Liveness check failed after $MAX_HEALTH_RETRIES attempts!" >&2
    echo "[$(date)] Rolling back to $PREV_COMMIT..." >&2

    # Rollback: reset to previous commit and redeploy
    git reset --hard "$PREV_COMMIT"
    docker rm -f "${APP_CONTAINERS[@]}" >/dev/null 2>&1 || true
    compose up -d --no-deps "${APP_SERVICES[@]}"

    echo "[$(date)] Rollback complete. Deployed commit: $PREV_COMMIT" >&2
    exit 1
fi

# ── Readiness snapshot (advisory) ──────────────────────────────
READY_HTTP_CODE=$(curl -s -o /tmp/viralflux-ready.json -w "%{http_code}" "$READY_URL" 2>/dev/null || echo "000")
if [ "$READY_HTTP_CODE" = "200" ]; then
    echo "[$(date)] Readiness snapshot OK: $READY_URL"
else
    echo "[$(date)] WARNING: Readiness snapshot returned HTTP $READY_HTTP_CODE: $READY_URL" >&2
    if [ -f /tmp/viralflux-ready.json ]; then
        cat /tmp/viralflux-ready.json >&2 || true
        echo >&2
    fi
fi

# ── Show status ────────────────────────────────────────────────
echo ""
echo "=== Deployment successful ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'virusradar_frontend_prod|virusradar_backend|viralflux_celery_worker|viralflux_celery_beat'
echo ""
echo "Commit: $NEW_COMMIT"
echo "Time:   $(date)"
