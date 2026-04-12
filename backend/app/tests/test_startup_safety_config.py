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
    settings = build_settings(
        ENVIRONMENT="development",
        DB_ALLOW_RUNTIME_SCHEMA_UPDATES=False,
    )

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


def test_operational_default_brand_is_normalized() -> None:
    settings = build_settings(OPERATIONAL_DEFAULT_BRAND="  ACME Health  ")

    assert settings.NORMALIZED_OPERATIONAL_DEFAULT_BRAND == "acme health"


def test_init_db_warns_when_runtime_schema_updates_flag_is_requested_but_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    monkeypatch.setattr(
        session_module,
        "_runtime_schema_gaps",
        lambda existing_tables=None: {"missing_columns": [], "missing_indexes": []},
    )

    summary = session_module.init_db()

    assert summary["status"] == "warning"
    assert summary["schema_management_mode"] == "verify_only"
    assert summary["actions"] == []
    assert summary["warnings"] == [
        "DB_ALLOW_RUNTIME_SCHEMA_UPDATES is deprecated and ignored. Startup runs in verify-only mode; apply explicit migrations instead."
    ]
