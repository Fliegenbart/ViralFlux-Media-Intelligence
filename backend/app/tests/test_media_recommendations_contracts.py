import importlib
import os
import sys
import types
import unittest
from unittest.mock import Mock, patch


os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("OPENWEATHER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")


class _FakeSignal:
    def connect(self, fn):
        return fn


class _FakeCelery:
    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.conf = types.SimpleNamespace(update=lambda **kwargs: None)

    def task(self, *args, **kwargs):
        del args, kwargs

        def decorator(fn):
            return fn

        return decorator


def _load_module():
    fake_celery = types.ModuleType("celery")
    fake_celery.Celery = _FakeCelery

    fake_schedules = types.ModuleType("celery.schedules")
    fake_schedules.crontab = lambda *args, **kwargs: ("crontab", args, kwargs)

    fake_signals = types.ModuleType("celery.signals")
    fake_signals.task_failure = _FakeSignal()
    fake_signals.task_success = _FakeSignal()
    fake_signals.task_prerun = _FakeSignal()
    fake_signals.task_postrun = _FakeSignal()

    with patch.dict(
        sys.modules,
        {
            "celery": fake_celery,
            "celery.schedules": fake_schedules,
            "celery.signals": fake_signals,
        },
    ):
        sys.modules.pop("app.core.celery_app", None)
        sys.modules.pop("app.api.media_routes_recommendations", None)
        return importlib.import_module("app.api.media_routes_recommendations")


class MediaRecommendationsContractTests(unittest.TestCase):
    def test_decorate_card_response_rejects_missing_brand(self) -> None:
        module = _load_module()
        service = Mock()
        service.truth_gate_service.evaluate.return_value = {"gate_open": False}
        service.outcome_signal_service.build_learning_bundle.return_value = {"summary": {}}
        service._attach_outcome_learning_to_card.return_value = {"id": "card-1"}
        module.contract_to_card_response = lambda opp, include_preview=True: {"brand": None}

        with self.assertRaises(ValueError):
            module._decorate_card_response(service, {"id": "opp-1"})


if __name__ == "__main__":
    unittest.main()
