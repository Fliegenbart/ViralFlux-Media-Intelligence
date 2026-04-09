from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.db import session as session_module


def build_settings(**overrides: object) -> Settings:
    base_values = {
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
        "POSTGRES_DB": "test",
        "OPENWEATHER_API_KEY": "test",
        "SECRET_KEY": "test-secret-key-with-minimum-length",
    }
    base_values.update(overrides)
    return Settings(_env_file=None, **base_values)


def test_runtime_schema_updates_default_to_disabled_in_development() -> None:
    settings = build_settings(ENVIRONMENT="development")

    assert settings.EFFECTIVE_DB_ALLOW_RUNTIME_SCHEMA_UPDATES is False


def test_runtime_schema_updates_can_be_explicitly_enabled() -> None:
    settings = build_settings(
        ENVIRONMENT="development",
        DB_ALLOW_RUNTIME_SCHEMA_UPDATES=True,
    )

    assert settings.EFFECTIVE_DB_ALLOW_RUNTIME_SCHEMA_UPDATES is True


def test_startup_bfarm_import_default_is_disabled() -> None:
    settings = build_settings(ENVIRONMENT="development")

    assert settings.STARTUP_ENABLE_BFARM_IMPORT is False


def test_init_db_warns_loudly_when_runtime_schema_updates_are_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    existing_tables = set(session_module.Base.metadata.tables.keys())

    monkeypatch.setattr(
        session_module,
        "settings",
        SimpleNamespace(
            EFFECTIVE_DB_AUTO_CREATE_SCHEMA=False,
            EFFECTIVE_DB_ALLOW_RUNTIME_SCHEMA_UPDATES=True,
        ),
    )
    monkeypatch.setattr(
        session_module,
        "inspect",
        lambda _engine: SimpleNamespace(get_table_names=lambda: existing_tables),
    )
    monkeypatch.setattr(session_module, "get_required_schema_contract_gaps", lambda _engine: {
        "missing_tables": [],
        "missing_columns": [],
        "missing_indexes": [],
    })

    gap_calls = iter([
        {"missing_columns": ["wastewater_data.available_time"], "missing_indexes": []},
        {"missing_columns": [], "missing_indexes": []},
    ])
    monkeypatch.setattr(session_module, "_runtime_schema_gaps", lambda existing_tables=None: next(gap_calls))

    ensure_calls: list[str] = []
    monkeypatch.setattr(session_module, "_ensure_runtime_schema_updates", lambda: ensure_calls.append("called"))

    summary = session_module.init_db()

    assert ensure_calls == ["called"]
    assert summary["status"] == "warning"
    assert summary["actions"] == ["runtime_schema_updates"]
    assert summary["warnings"] == [
        "Runtime schema updates were applied as a temporary safety-net. This must be replaced by explicit migrations before any release."
    ]
