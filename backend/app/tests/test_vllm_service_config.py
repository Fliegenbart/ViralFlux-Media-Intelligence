import importlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_core import ValidationError

from app.core import config as config_module
from app.core.config import Settings
from app.services.llm import vllm_service


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


def test_settings_load_repo_env_file_when_started_from_backend_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    monkeypatch.chdir(repo_root / "backend")
    for key in ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "OPENWEATHER_API_KEY", "SECRET_KEY"]:
        monkeypatch.delenv(key, raising=False)

    try:
        settings = Settings()
    except ValidationError as exc:  # pragma: no cover - this is the regression signal we care about
        pytest.fail(f"Settings should load values from the repo .env even inside backend/: {exc}")

    assert settings.POSTGRES_USER == "virusradar"
    assert settings.POSTGRES_DB == "virusradar_db"


def test_config_import_loads_repo_env_into_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    monkeypatch.chdir(repo_root / "backend")
    for key in ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "OPENWEATHER_API_KEY", "SECRET_KEY"]:
        monkeypatch.delenv(key, raising=False)

    importlib.reload(config_module)

    assert os.getenv("POSTGRES_USER") == "virusradar"
    assert os.getenv("SECRET_KEY") == "local-dev-secret-key-1234567890"


def test_required_vllm_base_url_raises_when_missing() -> None:
    settings = build_settings(VLLM_BASE_URL=None)

    with pytest.raises(RuntimeError, match="VLLM_BASE_URL ist nicht gesetzt"):
        _ = settings.REQUIRED_VLLM_BASE_URL


def test_required_vllm_base_url_returns_configured_value() -> None:
    settings = build_settings(VLLM_BASE_URL="http://host.docker.internal:8001/v1/")

    assert settings.REQUIRED_VLLM_BASE_URL == "http://host.docker.internal:8001/v1"


def test_vllm_clients_use_central_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, dict[str, str]] = {}

    class DummyClient:
        pass

    def fake_async_openai(*, base_url: str, api_key: str) -> DummyClient:
        captured["async"] = {"base_url": base_url, "api_key": api_key}
        return DummyClient()

    def fake_openai(*, base_url: str, api_key: str) -> DummyClient:
        captured["sync"] = {"base_url": base_url, "api_key": api_key}
        return DummyClient()

    monkeypatch.setattr(
        vllm_service,
        "get_settings",
        lambda: SimpleNamespace(
            REQUIRED_VLLM_BASE_URL="http://host.docker.internal:8001/v1",
            VLLM_API_KEY="local",
        ),
    )
    monkeypatch.setattr(vllm_service, "AsyncOpenAI", fake_async_openai)
    monkeypatch.setattr(vllm_service, "OpenAI", fake_openai)

    vllm_service.get_async_client.cache_clear()
    vllm_service.get_sync_client.cache_clear()

    vllm_service.get_async_client()
    vllm_service.get_sync_client()

    assert captured == {
        "async": {
            "base_url": "http://host.docker.internal:8001/v1",
            "api_key": "local",
        },
        "sync": {
            "base_url": "http://host.docker.internal:8001/v1",
            "api_key": "local",
        },
    }
