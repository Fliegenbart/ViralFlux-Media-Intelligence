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
SMOKE_BASE_URL="${SMOKE_BASE_URL:-http://localhost:8000}"
SMOKE_VIRUS="${SMOKE_VIRUS:-Influenza A}"
SMOKE_HORIZON="${SMOKE_HORIZON:-7}"
SMOKE_WEEKLY_BUDGET_EUR="${SMOKE_WEEKLY_BUDGET_EUR:-50000}"
SMOKE_TOP_N="${SMOKE_TOP_N:-3}"
SMOKE_CHECK_COCKPIT="${SMOKE_CHECK_COCKPIT:-false}"
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
  backend
  frontend-prod
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

ensure_infra_service() {
    local service="$1"
    local container="$2"

    if docker inspect "$container" >/dev/null 2>&1; then
        echo "[$(date)] Reusing existing infra container: $container"
        docker start "$container" >/dev/null 2>&1 || true
        return 0
    fi

    echo "[$(date)] Creating infra service via compose: $service"
    compose up -d "$service"
}

start_app_services_sequentially() {
    local service
    for service in "${APP_SERVICES[@]}"; do
        echo "[$(date)] Starting app service: $service"
        compose up -d --no-deps "$service"
    done
}

rollback_to_previous_commit() {
    echo "[$(date)] Rolling back to $PREV_COMMIT..." >&2
    git reset --hard "$PREV_COMMIT"
    docker rm -f "${APP_CONTAINERS[@]}" >/dev/null 2>&1 || true
    start_app_services_sequentially
    echo "[$(date)] Rollback complete. Deployed commit: $PREV_COMMIT" >&2
}

run_release_smoke() {
    local smoke_args=(
        --base-url "$SMOKE_BASE_URL"
        --virus "$SMOKE_VIRUS"
        --horizon "$SMOKE_HORIZON"
        --budget-eur "$SMOKE_WEEKLY_BUDGET_EUR"
        --top-n "$SMOKE_TOP_N"
    )

    if [ "$SMOKE_CHECK_COCKPIT" = "true" ]; then
        smoke_args+=(--check-cockpit)
    fi

    set +e
    python3 backend/scripts/smoke_test_release.py "${smoke_args[@]}" > /tmp/viralflux-release-smoke.json
    local smoke_exit=$?
    set -e

    if [ -f /tmp/viralflux-release-smoke.json ]; then
        cat /tmp/viralflux-release-smoke.json
        echo ""
    fi

    case "$smoke_exit" in
        0)
            echo "[$(date)] Release smoke passed."
            ;;
        10)
            echo "[$(date)] WARNING: Release smoke reports ready_blocked. Liveness and core business endpoints are up, but readiness is not healthy." >&2
            ;;
        20)
            echo "[$(date)] ERROR: Release smoke reports business_smoke_failed. Core regional product endpoints are not reliable." >&2
            return "$smoke_exit"
            ;;
        30)
            echo "[$(date)] ERROR: Release smoke reports live_failed." >&2
            return "$smoke_exit"
            ;;
        *)
            echo "[$(date)] ERROR: Release smoke returned unexpected exit code $smoke_exit." >&2
            return "$smoke_exit"
            ;;
    esac

    return 0
}

# ── Build frontend image ───────────────────────────────────────
echo "[$(date)] Building frontend image..."
docker build -t viralflux-media-frontend -f docker/Dockerfile.frontend .

# ── Build backend/runtime images ───────────────────────────────
echo "[$(date)] Building backend runtime images..."
compose build backend celery_worker celery_beat

# ── Bring up infra first ───────────────────────────────────────
echo "[$(date)] Ensuring infra services are up..."
ensure_infra_service db virusradar_db
ensure_infra_service redis viralflux_redis

# ── Deploy app containers ─────────────────────────────────────
echo "[$(date)] Deploying app containers..."
docker rm -f "${APP_CONTAINERS[@]}" >/dev/null 2>&1 || true
start_app_services_sequentially

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
    rollback_to_previous_commit
    exit 1
fi

# ── Modern release smoke ───────────────────────────────────────
echo "[$(date)] Running release smoke against live, ready and core regional product endpoints..."
if ! run_release_smoke; then
    rollback_to_previous_commit
    exit 1
fi

# ── Show status ────────────────────────────────────────────────
echo ""
echo "=== Deployment successful ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'virusradar_frontend_prod|virusradar_backend|viralflux_celery_worker|viralflux_celery_beat'
echo ""
echo "Commit: $NEW_COMMIT"
echo "Time:   $(date)"
