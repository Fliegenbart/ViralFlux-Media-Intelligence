#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

collect_changed_files() {
  if [ "$#" -gt 0 ]; then
    printf '%s\n' "$@"
    return
  fi

  git diff --name-only
  git diff --name-only --cached
}

mapfile -t changed_files < <(collect_changed_files "$@" | awk 'NF' | sort -u)

needs_check=0
for file in "${changed_files[@]}"; do
  case "$file" in
    backend/app/services/ml/*|backend/app/api/forecast.py|backend/app/api/admin_ml.py|backend/app/tests/test_regional_*)
      needs_check=1
      break
      ;;
  esac
done

if [ "$needs_check" -eq 0 ]; then
  echo "No regional ML changes detected."
  exit 0
fi

./.venv-backend311/bin/python -m py_compile \
  backend/app/services/ml/regional_panel_utils.py \
  backend/app/services/ml/regional_features.py \
  backend/app/services/ml/regional_trainer.py \
  backend/app/services/ml/regional_forecast.py

CI=true ./.venv-backend311/bin/pytest \
  backend/app/tests/test_regional_panel_math.py \
  backend/app/tests/test_regional_forecast_service.py \
  -q

