import os
import unittest
from unittest.mock import patch

os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("OPENWEATHER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test")

from app.services.marketing_engine import pitch_generator as pitch_module
from app.services.marketing_engine.pitch_generator import PitchGenerator


class PitchGeneratorFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = PitchGenerator()
        self.context = {
            "region_target": {"plz_cluster": "Berlin"},
            "_urgency": 82.0,
            "_competitor": "Wettbewerber X",
            "_article_id": "Gelo-Produkt",
        }

    def test_generate_falls_back_to_deterministic_template_when_llm_raises(self) -> None:
        with patch.object(pitch_module, "LLM_PITCHES_ENABLED", True), patch.object(
            pitch_module,
            "generate_text_sync",
            side_effect=RuntimeError("vLLM down"),
        ):
            pitch = self.generator.generate("RESOURCE_SCARCITY", self.context)

        self.assertEqual(pitch["headline_email"], "Akuter Engpass in Berlin: Verfügbarkeit jetzt kommunizieren")
        self.assertEqual(
            pitch["script_phone"],
            "In Berlin melden BfArM-Daten einen akuten Engpass bei vergleichbaren Produkten "
            "(Wettbewerber X). Empfehlung: Verfügbarkeit von Gelo-Produkt betonen und "
            "symptomnahe Kommunikation regional priorisieren (HWG-konform).",
        )
        self.assertEqual(pitch["call_to_action"], "Sichtbarkeit bei Engpass erhöhen")


if __name__ == "__main__":
    unittest.main()
