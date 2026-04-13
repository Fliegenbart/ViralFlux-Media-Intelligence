#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BACKEND_DIR="${BACKEND_DIR:-$REPO/backend}"
ENV_FILE="${ENV_FILE:-$REPO/server.env}"
IMAGE="${IMAGE:-viralflux-media-intelligence-clean-backend}"
NETWORK_CONTAINER="${NETWORK_CONTAINER:-virusradar_backend}"
MODELS_ROOT="${MODELS_ROOT:-/root/viralflux-h7-runs/models}"
REGISTRY_ROOT="${REGISTRY_ROOT:-/root/viralflux-h7-runs/forecast_registry}"
MODELS_CONTAINER_ROOT="${MODELS_CONTAINER_ROOT:-/runs/models}"
REGISTRY_CONTAINER_DIR="${REGISTRY_CONTAINER_DIR:-/app/backend/app/ml_models/forecast_registry}"
BOOTSTRAP_ITERATIONS="${REGIONAL_EVENT_BOOTSTRAP_ITERATIONS:-1}"
LOOKBACK_DAYS="${LOOKBACK_DAYS:-900}"
HORIZON_DAYS="${HORIZON_DAYS:-7}"
DETACH="${DETACH:-true}"
VIRUS="${VIRUS:-Influenza A}"

slugify() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '_'
}

VIRUS_SLUG="$(slugify "$VIRUS")"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)_${VIRUS_SLUG}_h${HORIZON_DAYS}_server_eval}"
CONTAINER_NAME="${CONTAINER_NAME:-h7_eval_${VIRUS_SLUG}_h${HORIZON_DAYS}}"
RUN_COMMIT="${RUN_COMMIT:-$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)}"
RUNNER_SCRIPT="/tmp/run_h7_scope.py"

if [ ! -d "$BACKEND_DIR" ]; then
    echo "ERROR: Backend directory not found: $BACKEND_DIR" >&2
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: Env file not found: $ENV_FILE" >&2
    exit 1
fi

mkdir -p "$MODELS_ROOT/$RUN_ID" "$REGISTRY_ROOT"
chmod 0777 "$MODELS_ROOT" "$MODELS_ROOT/$RUN_ID" "$REGISTRY_ROOT" || true

cat > "$RUNNER_SCRIPT" <<'PY'
import json
import os
from pathlib import Path

from app.db.session import get_db_context
from app.services.ml.regional_trainer import RegionalModelTrainer

models_dir = Path(os.environ["MODELS_DIR"])
virus_typ = os.environ["VIRUS_TYP"]
lookback_days = int(os.environ["LOOKBACK_DAYS"])
horizon_days = int(os.environ["HORIZON_DAYS"])
bootstrap_iterations = os.getenv("REGIONAL_EVENT_BOOTSTRAP_ITERATIONS")

print(
    f"DEBUG_START virus={virus_typ} models_dir={models_dir} bootstrap_iterations={bootstrap_iterations}",
    flush=True,
)

with get_db_context() as db:
    trainer = RegionalModelTrainer(db, models_dir=models_dir)
    result = trainer.train_all_regions(
        virus_typ=virus_typ,
        lookback_days=lookback_days,
        horizon_days=horizon_days,
    )

print(json.dumps(result, indent=2, default=str), flush=True)
PY

cleanup() {
    rm -f "$RUNNER_SCRIPT"
}
trap cleanup EXIT

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

DOCKER_ARGS=(
    run
)

if [ "$DETACH" = "true" ]; then
    DOCKER_ARGS+=(-d)
fi

DOCKER_ARGS+=(
    --name "$CONTAINER_NAME"
    --network "container:$NETWORK_CONTAINER"
    --env-file "$ENV_FILE"
    -e PYTHONPATH=/app/backend
    -e "MODELS_DIR=$MODELS_CONTAINER_ROOT/$RUN_ID"
    -e "FORECAST_REGISTRY_DIR=$REGISTRY_CONTAINER_DIR"
    -e "REGIONAL_EVENT_BOOTSTRAP_ITERATIONS=$BOOTSTRAP_ITERATIONS"
    -e "RUN_COMMIT=$RUN_COMMIT"
    -e "VIRUS_TYP=$VIRUS"
    -e "LOOKBACK_DAYS=$LOOKBACK_DAYS"
    -e "HORIZON_DAYS=$HORIZON_DAYS"
    -v "$BACKEND_DIR:/app/backend"
    -v "$MODELS_ROOT:$MODELS_CONTAINER_ROOT"
    -v "$REGISTRY_ROOT:$REGISTRY_CONTAINER_DIR"
    -v "$RUNNER_SCRIPT:/tmp/run_h7_scope.py"
    "$IMAGE"
    python3 /tmp/run_h7_scope.py
)

CONTAINER_ID="$(docker "${DOCKER_ARGS[@]}")"

echo "RUN_ID=$RUN_ID"
echo "CONTAINER_NAME=$CONTAINER_NAME"
if [ -n "$CONTAINER_ID" ]; then
    echo "CONTAINER_ID=$CONTAINER_ID"
fi
echo "VIRUS=$VIRUS"
echo "MODELS_DIR=$MODELS_ROOT/$RUN_ID"
echo "REGISTRY_ROOT=$REGISTRY_ROOT"
echo "FORECAST_REGISTRY_DIR=$REGISTRY_CONTAINER_DIR"

if [ "$DETACH" = "true" ]; then
    echo "Follow logs with: docker logs -f $CONTAINER_NAME"
fi
