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
    scripts/*|docker-compose.yml|docker-compose.prod.yml|DEPLOY.md)
      needs_check=1
      break
      ;;
  esac
done

if [ "$needs_check" -eq 0 ]; then
  echo "No deploy-path changes detected."
  exit 0
fi

if [ -f scripts/deploy-live.sh ]; then
  bash -n scripts/deploy-live.sh
fi

echo "Deploy-path change detected."
echo "Remember to keep DEPLOY.md aligned and verify /health after any live rollout."

