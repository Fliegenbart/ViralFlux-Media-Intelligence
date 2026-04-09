import json
import importlib
import sys
import types
import unittest

class AiCampaignPlannerNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._original_guardrails = sys.modules.get("app.services.media.campaign_guardrails")
        cls._original_vllm = sys.modules.get("app.services.llm.vllm_service")

        guardrails_stub = types.ModuleType("app.services.media.campaign_guardrails")
        guardrails_stub.HWG_SYSTEM_PROMPT = "test"
        guardrails_stub.check_hwg_compliance = lambda _: True
        sys.modules["app.services.media.campaign_guardrails"] = guardrails_stub

        llm_stub = types.ModuleType("app.services.llm.vllm_service")
        llm_stub.generate_text = lambda *_, **__: "ok"
        llm_stub.generate_text_sync = lambda *_, **__: '{"campaign_name":"A","objective":"B","budget_shift_pct":30,"activation_window_days":10,"channel_plan":[{"channel":"search","share_pct":100}]}'
        sys.modules["app.services.llm.vllm_service"] = llm_stub

        planner_module = importlib.import_module("app.services.media.ai_campaign_planner")
        cls.AiCampaignPlanner = planner_module.AiCampaignPlanner

    @classmethod
    def tearDownClass(cls) -> None:
        if cls._original_guardrails is None:
            sys.modules.pop("app.services.media.campaign_guardrails", None)
        else:
            sys.modules["app.services.media.campaign_guardrails"] = cls._original_guardrails

        if cls._original_vllm is None:
            sys.modules.pop("app.services.llm.vllm_service", None)
        else:
            sys.modules["app.services.llm.vllm_service"] = cls._original_vllm

    def setUp(self) -> None:
        self.planner = self.AiCampaignPlanner()
        self.candidate = {
            "playbook_key": "SUPPLY_SHOCK_ATTACK",
            "playbook_title": "Supply Shock",
            "region_name": "Berlin",
            "message_direction": "Verfügbarkeit in den Fokus",
            "budget_shift_pct": 22.0,
            "shift_bounds": {"min": 25.0, "max": 55.0},
            "channel_mix": {"programmatic": 40, "social": 35, "search": 25},
        }

    def test_to_float_plain_number(self) -> None:
        value = self.planner._to_float("25.0", default=0.0)
        self.assertEqual(value, 25.0)

    def test_to_float_percent_with_comma(self) -> None:
        value = self.planner._to_float("25,5%", default=0.0, percent=True)
        self.assertEqual(value, 25.5)

    def test_to_float_range_text_uses_first_value_and_warns(self) -> None:
        warnings = []
        value = self.planner._to_float(
            "25.0 bis 55.0",
            default=0.0,
            percent=True,
            warnings=warnings,
            field_name="budget_shift_pct",
        )
        self.assertEqual(value, 25.0)
        self.assertTrue(any("normalized to first number" in w for w in warnings))

    def test_to_float_invalid_defaults(self) -> None:
        value = self.planner._to_float("abc", default=12.0)
        self.assertEqual(value, 12.0)

    def test_to_float_clamps(self) -> None:
        low = self.planner._to_float("-5", default=0.0, min_value=0.0)
        high = self.planner._to_float("150", default=0.0, max_value=100.0)
        self.assertEqual(low, 0.0)
        self.assertEqual(high, 100.0)

    def test_normalize_plan_accepts_range_string_and_channel_strings(self) -> None:
        ai_plan = {
            "campaign_name": "Test",
            "objective": "Reach",
            "budget_shift_pct": "25.0 bis 55.0",
            "activation_window_days": "12",
            "channel_plan": [
                {"channel": "programmatic", "share_pct": "60%", "message_angle": "A", "kpi_primary": "CTR"},
                {"channel": "social", "share_pct": "40,0", "message_angle": "B", "kpi_primary": "CTR"},
            ],
        }
        normalized, warnings, flags = self.planner._normalize_plan(ai_plan, self.candidate, "Awareness")
        self.assertEqual(normalized["budget_shift_pct"], 25.0)
        self.assertEqual(normalized["activation_window_days"], 12)
        self.assertEqual(len(normalized["channel_plan"]), 2)
        self.assertIn("budget_shift_pct_range_text", flags)
        self.assertTrue(warnings)

    def test_normalize_plan_uses_channel_defaults_when_invalid(self) -> None:
        ai_plan = {
            "budget_shift_pct": "30",
            "activation_window_days": 10,
            "channel_plan": [{"channel": "", "share_pct": "abc"}],
        }
        normalized, warnings, flags = self.planner._normalize_plan(ai_plan, self.candidate, "Awareness")
        self.assertGreater(len(normalized["channel_plan"]), 0)
        self.assertIn("channel_plan_defaulted", flags)
        self.assertTrue(any("replaced with channel defaults" in w for w in warnings))

    def test_parse_json_response_with_markdown_fence(self) -> None:
        raw = """```json
{"campaign_name":"A","objective":"B","budget_shift_pct":30,"activation_window_days":10,"channel_plan":[{"channel":"search","share_pct":100}]}
```"""
        parsed = self.planner._parse_json_response(raw)
        self.assertEqual(parsed["campaign_name"], "A")

    def test_parse_json_response_with_wrapped_text(self) -> None:
        raw = (
            "Hier die Antwort:\n"
            '{"campaign_name":"A","objective":"B","budget_shift_pct":30,"activation_window_days":10,"channel_plan":[{"channel":"search","share_pct":100}]}\n'
            "Danke"
        )
        parsed = self.planner._parse_json_response(raw)
        self.assertEqual(parsed["objective"], "B")

    def test_parse_json_response_invalid_raises(self) -> None:
        with self.assertRaises(json.JSONDecodeError):
            self.planner._parse_json_response("kein json vorhanden")

    def test_generate_plan_skip_llm_uses_deterministic_fallback(self) -> None:
        result = self.planner.generate_plan(
            playbook_candidate=self.candidate,
            brand="gelo",
            product="product-x",
            campaign_goal="Awareness",
            weekly_budget=120000.0,
            skip_llm=True,
        )

        self.assertEqual(result["ai_generation_status"], "fallback_template")
        self.assertTrue(result["ai_meta"]["fallback_used"])
        self.assertIn("ai_plan", result)


if __name__ == "__main__":
    unittest.main()
