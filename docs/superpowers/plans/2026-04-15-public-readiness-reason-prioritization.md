# Public Readiness Reason Prioritization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public `/health/ready` payload show the real top-level warning reasons first and reduce repetitive forecast-monitoring lines without changing the actual readiness status.

**Architecture:** Keep the internal readiness snapshot untouched and change only the public formatting path in `backend/app/main.py`. Add regression tests in `backend/app/tests/test_main_security_surface.py` that first fail, then pass after the minimal implementation.

**Tech Stack:** Python, FastAPI, unittest, pytest

---

### Task 1: Lock Down Public Reason Ordering And Compaction

**Files:**
- Modify: `backend/app/tests/test_main_security_surface.py`
- Modify: `backend/app/main.py`
- Test: `backend/app/tests/test_main_security_surface.py`

- [ ] **Step 1: Write the failing tests**

Add tests that verify:

```python
def test_public_readiness_payload_prioritizes_system_warnings_before_forecast_monitoring(self) -> None:
    ...
    self.assertEqual(payload["status_reasons"][0], "schema_bootstrap: No startup schema summary recorded yet.")
```

```python
def test_public_readiness_payload_compacts_repetitive_forecast_watch_reasons(self) -> None:
    ...
    self.assertIn("Forecast monitoring: 3 viruses with forecast readiness WATCH.", payload["status_reasons"])
```

- [ ] **Step 2: Run the test file to verify the new expectations fail**

Run:

```bash
./.venv/bin/pytest backend/app/tests/test_main_security_surface.py -q
```

Expected:
- FAIL because `backend/app/main.py` still emits the old verbose reason ordering

- [ ] **Step 3: Write the minimal implementation**

In `backend/app/main.py`:

```python
def _compact_public_forecast_monitoring_reasons(...):
    ...
```

Update `_public_warning_reasons()` so that:
- non-forecast warning components with messages are emitted before forecast-monitoring items
- repetitive `forecast readiness WATCH` items with otherwise fresh monitoring fields are grouped into one public line
- freshness and critical forecast-monitoring issues still remain explicit

- [ ] **Step 4: Run the targeted tests to verify they pass**

Run:

```bash
./.venv/bin/pytest backend/app/tests/test_main_security_surface.py -q
```

Expected:
- PASS

- [ ] **Step 5: Run the adjacent regression tests**

Run:

```bash
./.venv/bin/pytest backend/app/tests/test_forecast_decision_service.py -q
```

Expected:
- PASS

- [ ] **Step 6: Commit the implementation**

```bash
git add backend/app/main.py backend/app/tests/test_main_security_surface.py
git commit -m "fix: prioritize public readiness reasons"
```
