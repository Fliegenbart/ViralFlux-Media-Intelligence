# Truth Scoreboard H5/H7 Implementation Plan

Goal: Add an investor-grade truth scoreboard and stricter H5/H7 media decision policy.
Architecture: Reuse existing regional backtest artifacts, compute per-virus/per-horizon scorecards, expose cockpit/API payloads, and keep business budget activation blocked unless outcome truth exists.
Tech Stack: Python backend, FastAPI media routes, unittest, existing cockpit snapshot builder.

Tasks:
- Add tests for H5/H7 action policy fields.
- Add tests for truth scoreboard cards, quality barriers, and combined H5/H7 decision classes.
- Add tests that cockpit snapshot exposes the truth scoreboard.
- Implement the scoreboard service using existing backtest artifacts.
- Wire the service into cockpit snapshot and a /cockpit/truth-scoreboard endpoint.
- Run focused tests, live server calculation, build if frontend touched, then commit/push.
