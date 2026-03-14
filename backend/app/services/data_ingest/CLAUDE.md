# Data Ingest Context

## Purpose

This module owns source imports and the point-in-time semantics the forecast stack depends on.

## Non-Negotiables

- Every source needs a trustworthy availability rule:
  real `available_time` if possible, otherwise a documented publication lag.
- Imports should be idempotent and reproducible.
- Do not silently replace source timing semantics with import time unless the fallback is explicit and documented.
- Preserve raw signal meaning:
  no hidden normalization changes without touching downstream assumptions.

## Default Workflow

- When onboarding a source:
  define schema, availability semantics, and downstream feature usage together.
- When changing an existing import:
  check ML consumers and dashboard consumers, not just the ingest path.
- For operational imports:
  prefer additive, observable changes over hidden backfills.

