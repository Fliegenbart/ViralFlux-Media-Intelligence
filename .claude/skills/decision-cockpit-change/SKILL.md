# Decision Cockpit Change

## Use When

- changing decision cards, wave charts, portfolio views, or freshness communication

## Workflow

1. Check the backend payload semantics first.
2. Use explicit wording for stale vs current observations.
3. Prefer semantically precise labels over marketing-friendly labels.
4. Keep watch, prepare, activate, and shadow states visually distinct.
5. Build after changes.

## Minimum Checks

- `cd frontend && CI=true npm test -- --runInBand --watch=false BacktestVisuals.test.tsx`
- `cd frontend && npm run build`

