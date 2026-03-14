# Live Deploy

## Use When

- pushing a validated change to production

## Workflow

1. Confirm the repo is on the intended commit.
2. Run relevant local checks first.
3. Deploy only through `./scripts/deploy-live.sh` or the documented server wrapper.
4. Verify:
   - `/health`
   - affected API endpoint
   - affected UI path
5. If behavior changed, update `DEPLOY.md` or adjacent docs as needed.

## Rule

No deploy is complete until the health check and the touched product surface were verified.

