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
    frontend/src/components/cockpit/*|frontend/src/features/media/*|frontend/src/pages/media/*)
      needs_check=1
      break
      ;;
  esac
done

if [ "$needs_check" -eq 0 ]; then
  echo "No cockpit UI changes detected."
  exit 0
fi

(
  cd frontend
  CI=true npm test -- --runInBand --watch=false BacktestVisuals.test.tsx
  npm run build
)

