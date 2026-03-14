# Cockpit UI Context

## Purpose

This module translates forecast outputs into decision-safe UI for media planning.

## Non-Negotiables

- Labels must match the underlying data semantics.
- Freshness must be visible whenever the latest observed point is not "today".
- Do not imply certainty the model does not have.
- If a panel is virus-based, do not present it as product truth.
- Watch/shadow states must be explicit and understandable.

## Default Checks

- For wave or marker changes:
  `cd frontend && CI=true npm test -- --runInBand --watch=false BacktestVisuals.test.tsx`
- Before closing UI work:
  `cd frontend && npm run build`

