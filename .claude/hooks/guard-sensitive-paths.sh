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

if [ "${#changed_files[@]}" -eq 0 ]; then
  exit 0
fi

protected_paths=(
  "backend/alembic/"
  "backend/app/core/"
  "docker-compose.yml"
  "docker-compose.prod.yml"
  "scripts/deploy-live.sh"
  ".github/workflows/"
)

blocked=()
for file in "${changed_files[@]}"; do
  for protected in "${protected_paths[@]}"; do
    if [[ "$file" == "$protected"* ]] || [[ "$file" == "$protected" ]]; then
      blocked+=("$file")
      break
    fi
  done
done

if [ "${#blocked[@]}" -eq 0 ]; then
  exit 0
fi

if [ "${ALLOW_SENSITIVE_CHANGES:-0}" = "1" ]; then
  printf 'Sensitive-path override enabled for:\n' >&2
  printf '  - %s\n' "${blocked[@]}" >&2
  exit 0
fi

printf 'Blocked sensitive path changes:\n' >&2
printf '  - %s\n' "${blocked[@]}" >&2
printf 'Set ALLOW_SENSITIVE_CHANGES=1 if this was intentional and reviewed.\n' >&2
exit 2

