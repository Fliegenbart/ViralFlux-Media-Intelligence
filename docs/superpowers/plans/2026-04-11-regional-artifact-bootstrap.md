# Regional Artifact Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make missing regional forecast artifacts fail clearly, return an operator-friendly bootstrap instruction, and surface the same readiness blocker in the operational health view.

**Architecture:** Keep the existing `no_model` behavior, but add one normalized artifact-diagnostic payload in the regional artifact loader. Reuse that payload in the forecast response and readiness matrix so runtime, operations, and docs all describe the same missing-artifact state.

**Tech Stack:** Python, FastAPI service layer, pytest, existing regional forecast helpers, existing production readiness matrix

---

## File Structure

### Existing files to modify

- `backend/app/services/ml/regional_forecast_artifacts.py`
  Purpose: loads scoped regional model bundles and already knows whether a bundle is missing, incomplete, or structurally invalid.
- `backend/app/services/ml/regional_forecast_prediction.py`
  Purpose: turns artifact-load outcomes into public regional forecast responses.
- `backend/app/services/ml/regional_forecast.py`
  Purpose: routes `_empty_forecast_response()` through the shared response helper.
- `backend/app/services/ml/regional_forecast_views.py`
  Purpose: builds the shared empty forecast response payload returned to callers.
- `backend/app/services/ops/production_readiness_matrix.py`
  Purpose: converts loaded artifact state into portfolio/core readiness matrix rows.
- `backend/app/tests/test_regional_forecast_service.py`
  Purpose: contract tests for missing models, invalid artifacts, and public forecast payloads.
- `backend/app/tests/test_production_readiness_service.py`
  Purpose: readiness snapshot behavior for healthy, warning, and critical regional states.
- `docs/production_readiness_checklist.md`
  Purpose: operator-facing release and bootstrap runbook.

### New file to create

- `backend/app/tests/test_regional_forecast_artifacts.py`
  Purpose: small focused tests for the new artifact diagnostic helper so we do not need to route every loader edge case through the full forecast service.

### Boundary decisions

- Keep all artifact classification logic in `regional_forecast_artifacts.py`.
- Keep response-shaping logic in `regional_forecast_views.py`.
- Keep readiness severity logic in `production_readiness_matrix.py`.
- Do not add startup training, background jobs, or a new registry service.

---

### Task 1: Add a Normalized Regional Artifact Diagnostic

**Files:**
- Create: `backend/app/tests/test_regional_forecast_artifacts.py`
- Modify: `backend/app/services/ml/regional_forecast_artifacts.py`

- [ ] **Step 1: Write the failing artifact diagnostic tests**

```python
from pathlib import Path

from app.services.ml import regional_forecast_artifacts


def test_missing_scope_returns_bootstrap_diagnostic(tmp_path: Path) -> None:
    diagnostic = regional_forecast_artifacts.build_artifact_diagnostic(
        virus_typ="Influenza A",
        horizon_days=5,
        artifact_dir=tmp_path / "influenza_a" / "horizon_5",
        missing_files=[],
        load_error="",
        supported_horizons=[3, 5, 7],
    )

    assert diagnostic["status"] == "missing"
    assert diagnostic["bootstrap_required"] is True
    assert diagnostic["artifact_scope"] == {"virus_typ": "Influenza A", "horizon_days": 5}
    assert "backfill_regional_model_artifacts.py" in diagnostic["bootstrap_command"]


def test_incomplete_scope_lists_missing_files(tmp_path: Path) -> None:
    diagnostic = regional_forecast_artifacts.build_artifact_diagnostic(
        virus_typ="RSV A",
        horizon_days=7,
        artifact_dir=tmp_path / "rsv_a" / "horizon_7",
        missing_files=["classifier.json", "calibration.pkl"],
        load_error="Artefakt-Bundle für RSV A/h7 ist unvollständig.",
        supported_horizons=[5, 7],
    )

    assert diagnostic["status"] == "incomplete"
    assert diagnostic["missing_files"] == ["classifier.json", "calibration.pkl"]
    assert "classifier.json" in diagnostic["operator_message"]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test /Users/davidwegener/Desktop/viralflux/.venv/bin/python -m pytest backend/app/tests/test_regional_forecast_artifacts.py -q --tb=short`

Expected: FAIL because `build_artifact_diagnostic` does not exist yet.

- [ ] **Step 3: Add the smallest shared diagnostic helper**

```python
def bootstrap_command(*, supported_horizons: list[int]) -> str:
    horizon_args = " ".join(f"--horizon {int(h)}" for h in sorted(set(supported_horizons)))
    return f"cd backend && python scripts/backfill_regional_model_artifacts.py {horizon_args}".strip()


def build_artifact_diagnostic(
    *,
    virus_typ: str,
    horizon_days: int,
    artifact_dir: Path,
    missing_files: list[str],
    load_error: str,
    supported_horizons: list[int],
    artifact_transition_mode: str | None = None,
) -> dict[str, Any]:
    status = "missing"
    if missing_files:
        status = "incomplete"
    elif load_error:
        status = "invalid"

    operator_message = (
        f"Regionales Modellartefakt für {virus_typ}/h{horizon_days} fehlt. "
        f"Bitte den Bootstrap ausführen: {bootstrap_command(supported_horizons=supported_horizons)}"
    )
    if status == "incomplete":
        operator_message = (
            f"Artefakt-Bundle für {virus_typ}/h{horizon_days} ist unvollständig: "
            f"{', '.join(missing_files)}. "
            f"Bitte den Bootstrap ausführen: {bootstrap_command(supported_horizons=supported_horizons)}"
        )
    if status == "invalid" and load_error:
        operator_message = f"{load_error} Bootstrap: {bootstrap_command(supported_horizons=supported_horizons)}"

    return {
        "status": status,
        "artifact_scope": {"virus_typ": virus_typ, "horizon_days": int(horizon_days)},
        "artifact_dir": str(artifact_dir),
        "missing_files": list(missing_files),
        "bootstrap_required": True,
        "operator_message": operator_message,
        "bootstrap_command": bootstrap_command(supported_horizons=supported_horizons),
        "artifact_transition_mode": artifact_transition_mode,
        "load_error": load_error or None,
    }
```

Also thread that helper into `load_artifacts()` so missing or incomplete scopes attach `artifact_diagnostic` instead of only returning a plain `load_error`.

- [ ] **Step 4: Run the artifact diagnostic tests to verify they pass**

Run: `POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test /Users/davidwegener/Desktop/viralflux/.venv/bin/python -m pytest backend/app/tests/test_regional_forecast_artifacts.py -q --tb=short`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ml/regional_forecast_artifacts.py backend/app/tests/test_regional_forecast_artifacts.py
git commit -m "feat: add regional artifact bootstrap diagnostics"
```

---

### Task 2: Expose Bootstrap Guidance in the Forecast Response

**Files:**
- Modify: `backend/app/services/ml/regional_forecast_prediction.py`
- Modify: `backend/app/services/ml/regional_forecast.py`
- Modify: `backend/app/services/ml/regional_forecast_views.py`
- Modify: `backend/app/tests/test_regional_forecast_service.py`

- [ ] **Step 1: Write the failing forecast-response tests**

Add two focused tests to `backend/app/tests/test_regional_forecast_service.py`:

```python
def test_predict_all_regions_includes_bootstrap_guidance_for_missing_artifacts(self) -> None:
    service = self._make_service()
    service._load_artifacts = lambda virus_typ, horizon_days=7: {
        "artifact_diagnostic": {
            "status": "missing",
            "artifact_scope": {"virus_typ": virus_typ, "horizon_days": horizon_days},
            "artifact_dir": f"/tmp/{virus_typ}/horizon_{horizon_days}",
            "missing_files": [],
            "bootstrap_required": True,
            "operator_message": "Regionales Modell fehlt. Bitte Bootstrap ausführen.",
            "bootstrap_command": "cd backend && python scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7",
            "artifact_transition_mode": None,
            "load_error": None,
        }
    }

    result = service.predict_all_regions(virus_typ="Influenza A", horizon_days=5)

    assert result["status"] == "no_model"
    assert result["missing_artifacts"] is True
    assert result["missing_scopes"] == [{"virus_typ": "Influenza A", "horizon_days": 5}]
    assert "backfill_regional_model_artifacts.py" in result["bootstrap_command"]


def test_predict_all_regions_surfaces_missing_files_for_incomplete_bundle(self) -> None:
    service = self._make_service()
    service._load_artifacts = lambda virus_typ, horizon_days=7: {
        "load_error": "Artefakt-Bundle für Influenza A/h7 ist unvollständig.",
        "artifact_diagnostic": {
            "status": "incomplete",
            "artifact_scope": {"virus_typ": virus_typ, "horizon_days": horizon_days},
            "artifact_dir": f"/tmp/{virus_typ}/horizon_{horizon_days}",
            "missing_files": ["classifier.json", "calibration.pkl"],
            "bootstrap_required": True,
            "operator_message": "Artefakt-Bundle unvollständig.",
            "bootstrap_command": "cd backend && python scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7",
            "artifact_transition_mode": None,
            "load_error": "Artefakt-Bundle für Influenza A/h7 ist unvollständig.",
        },
    }

    result = service.predict_all_regions(virus_typ="Influenza A", horizon_days=7)

    assert result["status"] == "no_model"
    assert result["artifact_diagnostic"]["missing_files"] == ["classifier.json", "calibration.pkl"]
    assert "classifier.json" in result["message"] or "classifier.json" in result["operator_message"]
```

- [ ] **Step 2: Run the targeted forecast tests to verify they fail**

Run: `POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test /Users/davidwegener/Desktop/viralflux/.venv/bin/python -m pytest backend/app/tests/test_regional_forecast_service.py -q --tb=short -k "bootstrap_guidance or incomplete_bundle or explicit_no_model_for_missing_horizon"`

Expected: FAIL because the forecast response does not yet expose `missing_artifacts`, `missing_scopes`, or `bootstrap_command`.

- [ ] **Step 3: Thread the diagnostic payload into the shared empty response**

Update `empty_forecast_response()` and the `_empty_forecast_response()` wrapper to accept an optional diagnostic object and expose it consistently:

```python
def empty_forecast_response(
    service,
    *,
    virus_typ: str,
    horizon_days: int,
    status: str,
    message: str,
    artifact_transition_mode: str | None = None,
    artifact_diagnostic: dict[str, Any] | None = None,
    supported_horizon_days_for_virus: list[int] | None = None,
    ensure_supported_horizon_fn,
    supported_forecast_horizons,
    utc_now_fn,
) -> dict[str, Any]:
    horizon = ensure_supported_horizon_fn(horizon_days)
    diagnostic = dict(artifact_diagnostic or {})
    return {
        "virus_typ": virus_typ,
        "status": status,
        "message": message,
        "operator_message": diagnostic.get("operator_message"),
        "bootstrap_command": diagnostic.get("bootstrap_command"),
        "missing_artifacts": bool(diagnostic.get("bootstrap_required")),
        "missing_scopes": [diagnostic.get("artifact_scope")] if diagnostic.get("artifact_scope") else [],
        "artifact_diagnostic": diagnostic or None,
        "horizon_days": horizon,
        "supported_horizon_days": list(supported_forecast_horizons),
        "supported_horizon_days_for_virus": list(supported_horizon_days_for_virus or supported_forecast_horizons),
        "target_window_days": service._target_window_for_horizon(horizon),
        "artifact_transition_mode": artifact_transition_mode,
        "predictions": [],
        "top_5": [],
        "top_decisions": [],
        "decision_summary": service._decision_summary([]),
        "total_regions": 0,
        "generated_at": utc_now_fn().isoformat(),
    }
```

In `regional_forecast_prediction.py`, pass `artifacts.get("artifact_diagnostic")` into every `service._empty_forecast_response(...)` call that originates from a missing or invalid artifact bundle.

- [ ] **Step 4: Run the targeted forecast tests to verify they pass**

Run: `POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test /Users/davidwegener/Desktop/viralflux/.venv/bin/python -m pytest backend/app/tests/test_regional_forecast_service.py -q --tb=short -k "bootstrap_guidance or incomplete_bundle or explicit_no_model_for_missing_horizon"`

Expected: PASS, and the old `no_model` tests still pass with the enriched payload.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ml/regional_forecast.py backend/app/services/ml/regional_forecast_prediction.py backend/app/services/ml/regional_forecast_views.py backend/app/tests/test_regional_forecast_service.py
git commit -m "feat: expose bootstrap guidance in regional forecast responses"
```

---

### Task 3: Surface Missing Artifacts in Production Readiness

**Files:**
- Modify: `backend/app/services/ops/production_readiness_matrix.py`
- Modify: `backend/app/services/ops/production_readiness_service.py`
- Modify: `backend/app/tests/test_production_readiness_service.py`

- [ ] **Step 1: Write the failing readiness test**

Add a focused test in `backend/app/tests/test_production_readiness_service.py`:

```python
def test_build_snapshot_exposes_regional_artifact_bootstrap_blocker(self) -> None:
    now = datetime(2026, 4, 11, 10, 0, 0)
    self._seed_wastewater(available_time=now - timedelta(days=1))

    def fake_artifacts(_self, virus_typ: str, horizon_days: int = 7):
        return {
            "artifact_diagnostic": {
                "status": "missing",
                "artifact_scope": {"virus_typ": virus_typ, "horizon_days": horizon_days},
                "artifact_dir": f"/tmp/{virus_typ}/horizon_{horizon_days}",
                "missing_files": [],
                "bootstrap_required": True,
                "operator_message": "Regionales Modell fehlt.",
                "bootstrap_command": "cd backend && python scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7",
                "artifact_transition_mode": None,
                "load_error": None,
            }
        }

    with patch("app.services.ml.regional_forecast.RegionalForecastService._load_artifacts", new=fake_artifacts):
        service = ProductionReadinessService(session_factory=self._session_factory, now_provider=lambda: now)
        service._broker_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
        service._schema_bootstrap_component = lambda: {"status": "ok", "message": "mocked"}  # type: ignore[method-assign]
        snapshot = service.build_snapshot()

    regional = snapshot["components"]["regional_operational"]
    item = next(entry for entry in regional["matrix"] if entry["virus_typ"] == "Influenza A" and entry["horizon_days"] == 5)
    assert regional["status"] == "critical"
    assert item["model_availability"] == "missing"
    assert item["regional_artifacts_ready"] is False
    assert "backfill_regional_model_artifacts.py" in item["regional_artifact_bootstrap_command"]
```

- [ ] **Step 2: Run the readiness test to verify it fails**

Run: `POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test /Users/davidwegener/Desktop/viralflux/.venv/bin/python -m pytest backend/app/tests/test_production_readiness_service.py -q --tb=short -k regional_artifact_bootstrap_blocker`

Expected: FAIL because the readiness matrix does not yet expose `regional_artifacts_ready` or the bootstrap command.

- [ ] **Step 3: Enrich the readiness matrix item with the shared diagnostic**

In `production_readiness_matrix.py`, read the same `artifact_diagnostic` emitted by `service._load_artifacts(...)` and expose it on the matrix row:

```python
artifact_diagnostic = dict(artifacts.get("artifact_diagnostic") or {})
bootstrap_command = artifact_diagnostic.get("bootstrap_command")
operator_message = artifact_diagnostic.get("operator_message")

if not model_available and operator_message and operator_message not in blockers:
    blockers.append(operator_message)

return {
    "virus_typ": virus_typ,
    "horizon_days": horizon_days,
    "status": overall_status,
    "model_availability": model_availability,
    "regional_artifacts_ready": model_available,
    "regional_artifact_blockers": list(dict.fromkeys(blockers)),
    "regional_artifact_bootstrap_command": bootstrap_command,
    "artifact_diagnostic": artifact_diagnostic or None,
    "load_error": load_error or None,
    "artifact_transition_mode": artifact_transition_mode,
    "quality_gate": quality_gate,
    "model_version": metadata.get("model_version"),
    "calibration_version": metadata.get("calibration_version"),
    "trained_at": metadata.get("trained_at"),
    "blockers": list(dict.fromkeys(blockers)),
}
```

In `production_readiness_service.py`, extend the regional summary if needed so the component makes the missing-artifact count and blockers easy to inspect, for example by counting rows where `regional_artifacts_ready` is `False`.

- [ ] **Step 4: Run the readiness tests to verify they pass**

Run: `POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test /Users/davidwegener/Desktop/viralflux/.venv/bin/python -m pytest backend/app/tests/test_production_readiness_service.py -q --tb=short -k "regional_artifact_bootstrap_blocker or healthy_when_models_and_sources_are_fresh"`

Expected: PASS, including the new blocker case and one pre-existing healthy case to prove the matrix still works.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ops/production_readiness_matrix.py backend/app/services/ops/production_readiness_service.py backend/app/tests/test_production_readiness_service.py
git commit -m "feat: surface regional artifact bootstrap state in readiness"
```

---

### Task 4: Align the Operator Documentation with the Runtime Message

**Files:**
- Modify: `docs/production_readiness_checklist.md`

- [ ] **Step 1: Write the failing documentation expectation as a tiny grep check**

Run this before editing:

```bash
rg -n "backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7|regional_artifacts_ready|bootstrap command" docs/production_readiness_checklist.md
```

Expected: either no hit for the exact runtime wording or wording that does not yet mention the new readiness fields.

- [ ] **Step 2: Update the operator doc to match the runtime contract**

Add a short section like this to `docs/production_readiness_checklist.md`:

````md
### Missing Regional Artifacts

If the regional forecast path reports `missing_artifacts=true` or readiness shows `regional_artifacts_ready=false`, bootstrap the regional models first:

```bash
cd backend
python scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7
```

After that:

1. recompute operational views
2. rerun the smoke test
3. confirm readiness no longer reports regional artifact blockers
```
````

- [ ] **Step 3: Verify the doc now contains the exact bootstrap command**

Run: `rg -n "python scripts/backfill_regional_model_artifacts.py --horizon 3 --horizon 5 --horizon 7|regional_artifacts_ready" docs/production_readiness_checklist.md`

Expected: PASS with at least one hit for the exact bootstrap command and one hit for the readiness wording.

- [ ] **Step 4: Run the focused regression suite for this whole feature**

Run: `POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test /Users/davidwegener/Desktop/viralflux/.venv/bin/python -m pytest backend/app/tests/test_regional_forecast_artifacts.py backend/app/tests/test_regional_forecast_service.py backend/app/tests/test_production_readiness_service.py -q --tb=short`

Expected: PASS for all three suites.

- [ ] **Step 5: Commit**

```bash
git add docs/production_readiness_checklist.md backend/app/tests/test_regional_forecast_artifacts.py backend/app/tests/test_regional_forecast_service.py backend/app/tests/test_production_readiness_service.py backend/app/services/ml/regional_forecast_artifacts.py backend/app/services/ml/regional_forecast.py backend/app/services/ml/regional_forecast_prediction.py backend/app/services/ml/regional_forecast_views.py backend/app/services/ops/production_readiness_matrix.py backend/app/services/ops/production_readiness_service.py
git commit -m "docs: align regional artifact bootstrap guidance"
```

---

## Spec Coverage Check

- Central artifact diagnostic payload: covered by Task 1.
- Forecast response enrichment with bootstrap command and missing scopes: covered by Task 2.
- Readiness exposure of missing regional artifacts: covered by Task 3.
- Operator docs aligned with emitted runtime command: covered by Task 4.

## Self-Review Notes

- No placeholder tasks remain.
- The same `bootstrap_command` string is reused across runtime and docs to avoid contract drift.
- The plan keeps boundaries clear: loader logic in artifact helpers, response logic in forecast views, severity logic in readiness matrix.
