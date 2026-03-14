# Scripts Context

## Purpose

This directory contains operational entrypoints, especially production deployment.

## Non-Negotiables

- Production deploys must go through the documented script path.
- Never hardcode or print secrets into repo files or logs.
- Do not treat a deploy as successful without health verification.
- Keep rollback simple and documented.

## Default Workflow

- Preferred live deploy:
  `./scripts/deploy-live.sh`
- After deploy:
  verify `/health`, the affected API path, and the affected UI surface.
- If deploy behavior changes:
  update [DEPLOY.md](/Users/davidwegener/Desktop/viralflux/DEPLOY.md) in the same change.

