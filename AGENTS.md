# AGENTS.md

Applies to the whole repository.

## Change scope

- Make minimal, high-confidence changes.
- Do not change unrelated files, services, routes, ports, or deployment behavior.
- Avoid broad refactors unless the task explicitly requires them.

## API and auth safety

- Preserve existing `/api/v1/public/*` behavior unless the task explicitly changes it.
- Preserve existing M2M / API-key protected endpoint behavior unless the task explicitly changes it.
- Do not silently make an endpoint require both JWT and M2M auth unless the task explicitly says so.
- Do not introduce self-referential service defaults such as backend URLs that point a container to itself when configuring external services like vLLM.

## Validation

- Run targeted validation after edits, not blanket full-suite runs unless needed.
- If Docker or compose files change, run `docker compose config`.
- Frontend changes: at minimum run `cd frontend && npx tsc --noEmit`.
- Frontend behavior changes: also run focused tests such as `cd frontend && CI=true npm test -- --watch=false`.
- If frontend auth changes, add or update tests for token persistence, rehydration, and logout behavior.
- Backend changes: run the smallest relevant `pytest` selection under `backend/app/tests`.
- If backend auth changes, verify representative `401`/`403` cases and explicitly confirm that public and M2M endpoints still behave as intended.
- If `.venv-backend311` exists, prefer it for backend validation commands.
- For config or docs changes, run targeted grep / syntax checks when practical.

## Docs and config alignment

- If runtime behavior changes, update the matching docs and examples in the same change.
- Keep `.env.example`, `README.md`, `QUICKSTART.md`, `ARCHITECTURE.md`, `DEPLOY.md`, and compose files aligned with actual behavior when they are affected.
- Do not leave docs claiming behavior that the code does not implement.
- Use repo-relative paths or placeholders in docs; do not introduce machine-specific absolute paths.

## Handoff

- Summarize the files changed.
- List the commands run and whether they passed, failed, or were unavailable.
- Call out any narrow exceptions, ignored checks, or residual risks explicitly.
