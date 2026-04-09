from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ACTIVE_APP_ROOT = REPO_ROOT / "backend" / "app"
REMOVED_RISK_ENGINE_TOKENS = ("risk_engine.py", "risk_engine_legacy.py", "risk_engine", "risk_engine_legacy")


def test_active_backend_code_does_not_reference_removed_risk_engines() -> None:
    offenders: list[str] = []

    for path in ACTIVE_APP_ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue
        content = path.read_text()
        if any(token in content for token in REMOVED_RISK_ENGINE_TOKENS):
            offenders.append(str(path))

    assert offenders == [], f"Removed risk engine references found in active backend code: {offenders}"
