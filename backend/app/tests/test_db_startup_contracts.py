import pytest
from unittest.mock import MagicMock

from app.db import session as db_session


class _FakeInspector:
    def get_table_names(self):
        return list(db_session.Base.metadata.tables.keys())


def test_init_db_does_not_apply_runtime_schema_updates(monkeypatch):
    runtime_update_mock = MagicMock()
    monkeypatch.setattr(db_session, "inspect", lambda *_args, **_kwargs: _FakeInspector())
    monkeypatch.setattr(db_session, "_ensure_runtime_schema_updates", runtime_update_mock)
    monkeypatch.setattr(db_session, "_runtime_schema_gaps", lambda *_args, **_kwargs: {
        "missing_columns": ["marketing_opportunities.updated_at"],
        "missing_indexes": [],
    })
    monkeypatch.setattr(db_session, "get_required_schema_contract_gaps", lambda *_args, **_kwargs: {
        "missing_tables": [],
        "missing_columns": [],
        "missing_indexes": [],
    })

    with pytest.raises(RuntimeError, match="Fehlende DB-Migrationen/Schema-Gaps"):
        db_session.init_db()

    runtime_update_mock.assert_not_called()
