from types import SimpleNamespace

import pytest

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
