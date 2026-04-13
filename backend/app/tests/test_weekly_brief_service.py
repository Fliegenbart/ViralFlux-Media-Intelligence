import sys
import types
from datetime import datetime
from unittest.mock import ANY, patch

from app.services.media.weekly_brief_service import (
    WeeklyBriefService,
    _ActionBriefPDF,
    _action_card_title,
    _dedupe_cards,
    _format_signal_score,
    _normalize_tile_line,
    _primary_signal_score,
    _source_display_label,
    _tile_display_title,
)


def test_source_display_label_translates_technical_source_names():
    assert _source_display_label("weather") == "Wetter"
    assert _source_display_label("bfarm shortage") == "BfArM-Engpässe"
    assert _source_display_label("marketing") == "Kundendaten"


def test_dedupe_cards_removes_repeated_product_entries():
    cards = [
        {
            "recommended_product": "Atemwegslinie",
            "reason": "kritische Antibiotika-Engpässe",
            "region_codes": ["BY", "HH", "SN"],
        },
        {
            "recommended_product": "Atemwegslinie",
            "reason": "kritische Antibiotika-Engpässe",
            "region_codes": ["SN", "HH", "BY"],
        },
        {
            "recommended_product": "Atemwegslinie",
            "reason": "nasskalte Wetterlage",
            "region_codes": ["BB", "BE"],
        },
    ]

    deduped = _dedupe_cards(cards)

    assert len(deduped) == 2


def test_tile_display_title_translates_legacy_dashboard_terms():
    assert _tile_display_title("Signalscore Deutschland") == "Signalwert Deutschland"
    assert _tile_display_title("SURVSTAT Respiratory") == "SurvStat Atemwege"


def test_normalize_tile_line_translates_legacy_terms_in_full_line():
    line = "[LIVE] SURVSTAT Respiratory: 7789.0/100k Signalwert: 100%"
    assert _normalize_tile_line(line).startswith("[LIVE] SurvStat Atemwege")


def test_primary_signal_score_prefers_explicit_score_over_legacy_probability_alias():
    region = {
        "score_0_100": 77.0,
        "peix_score": 74.0,
        "signal_score": 71.0,
        "impact_probability": 84.0,
    }

    assert _primary_signal_score(region) == 71.0


def test_format_signal_score_uses_score_scale_instead_of_percent():
    assert _format_signal_score(77.0) == "77/100"
    assert _format_signal_score(0.77) == "77/100"


def test_source_display_label_wrapper_delegates_to_formatting_module():
    with patch(
        "app.services.media.weekly_brief_service.weekly_brief_formatting.source_display_label",
        return_value="Delegated Quelle",
    ) as mocked:
        result = _source_display_label("weather")

    assert result == "Delegated Quelle"
    mocked.assert_called_once_with("weather")


def test_dedupe_cards_wrapper_delegates_to_formatting_module():
    cards = [{"recommended_product": "Atemwegslinie", "reason": "kritische Engpässe"}]

    with patch(
        "app.services.media.weekly_brief_service.weekly_brief_formatting.dedupe_cards",
        return_value=[{"recommended_product": "Delegated"}],
    ) as mocked:
        result = _dedupe_cards(cards)

    assert result == [{"recommended_product": "Delegated"}]
    mocked.assert_called_once_with(cards)


def test_primary_signal_score_wrapper_delegates_to_formatting_module():
    payload = {"signal_score": 71.0}

    with patch(
        "app.services.media.weekly_brief_service.weekly_brief_formatting.primary_signal_score",
        return_value=55.0,
    ) as mocked:
        result = _primary_signal_score(payload)

    assert result == 55.0
    mocked.assert_called_once_with(payload)


def test_action_card_title_wrapper_delegates_to_formatting_module():
    card = {"recommended_product": "Atemwegslinie", "reason": "kritische Engpässe"}

    with patch(
        "app.services.media.weekly_brief_service.weekly_brief_formatting.action_card_title",
        return_value="Delegated Titel",
    ) as mocked:
        result = _action_card_title(card)

    assert result == "Delegated Titel"
    mocked.assert_called_once_with(card)


def test_render_signal_page_wrapper_delegates_to_pages_module():
    service = WeeklyBriefService(db=None)
    pdf = _ActionBriefPDF("2026-W15")

    with patch(
        "app.services.media.weekly_brief_service.weekly_brief_pages.render_signal_page"
    ) as mocked:
        service._render_signal_page(
            pdf,
            calendar_week="2026-W15",
            now=datetime(2026, 4, 10, 9, 0, 0),
            iso_week=15,
            iso_year=2026,
            virus_typ="Influenza A",
            peix={},
            tiles=[],
            region_list=[],
        )

    mocked.assert_called_once_with(
        service,
        pdf,
        calendar_week="2026-W15",
        now=datetime(2026, 4, 10, 9, 0, 0),
        iso_week=15,
        iso_year=2026,
        virus_typ="Influenza A",
        peix={},
        tiles=[],
        region_list=[],
    )


def test_render_action_page_wrapper_delegates_to_pages_module():
    service = WeeklyBriefService(db=None)
    pdf = _ActionBriefPDF("2026-W15")

    with patch(
        "app.services.media.weekly_brief_service.weekly_brief_pages.render_action_page"
    ) as mocked:
        service._render_action_page(pdf, region_list=[], top_cards=[])

    mocked.assert_called_once_with(service, pdf, region_list=[], top_cards=[])


def test_action_brief_pdf_header_and_footer_use_viralflux_branding():
    pdf = _ActionBriefPDF("2026-W15")
    pdf.set_compression(False)
    pdf.add_page()

    raw = pdf.output(dest="S")
    text = raw.decode("latin1", errors="ignore") if not isinstance(raw, str) else raw

    assert "ViralFlux Frühwarnung" in text
    assert "ViralFlux Wochenbericht | Vertraulich" in text
    assert "PEIX x GELO" not in text


def test_render_signal_page_uses_neutral_viralflux_intro_copy():
    service = WeeklyBriefService(db=None)
    pdf = _ActionBriefPDF("2026-W15")
    pdf.set_compression(False)

    service._render_signal_page(
        pdf,
        calendar_week="2026-W15",
        now=datetime(2026, 4, 10, 9, 0, 0),
        iso_week=15,
        iso_year=2026,
        virus_typ="Influenza A",
        peix={},
        tiles=[],
        region_list=[],
    )

    raw = pdf.output(dest="S")
    text = raw.decode("latin1", errors="ignore") if not isinstance(raw, str) else raw

    assert "ViralFlux Wochenbericht" in text
    assert "Automatisierte Lageeinschätzung für das Team." in text
    assert "PEIX x GELO" not in text


def test_render_evidence_page_wrapper_delegates_to_pages_module():
    service = WeeklyBriefService(db=None)
    pdf = _ActionBriefPDF("2026-W15")

    with patch(
        "app.services.media.weekly_brief_service.weekly_brief_pages.render_evidence_page"
    ) as mocked:
        service._render_evidence_page(
            pdf,
            freshness={},
            now=datetime(2026, 4, 10, 9, 0, 0),
            pitch_results=[],
        )

    mocked.assert_called_once_with(
        service,
        pdf,
        freshness={},
        now=datetime(2026, 4, 10, 9, 0, 0),
        pitch_results=[],
    )


def test_generate_prefers_national_score_over_legacy_alias_in_summary():
    service = WeeklyBriefService(db=None)

    cockpit_module = types.ModuleType("app.services.media.cockpit_service")

    class DummyCockpitService:
        def __init__(self, db):
            self.db = db

        def get_cockpit_payload(self, *, virus_typ: str):
            return {
                "peix_epi_score": {
                    "national_score": 71.0,
                    "national_band": "hoch",
                    "national_impact_probability": 84.0,
                },
                "bento": {"tiles": []},
                "map": {"regions": {}},
                "recommendations": {"cards": []},
                "data_freshness": {},
            }

    cockpit_module.MediaCockpitService = DummyCockpitService

    with patch.dict(sys.modules, {"app.services.media.cockpit_service": cockpit_module}):
        with patch("app.services.media.weekly_brief_service.utc_now", return_value=datetime(2026, 4, 10, 9, 0, 0)):
            with patch.object(service, "_run_backtest_pitches", return_value=[]):
                with patch.object(service, "_save_to_db") as save_mock:
                    result = service.generate(brand="gelo", virus_typ="Influenza A")

    assert result["summary"]["national_impact"] == 71.0
    save_mock.assert_called_once()


def test_generate_requires_explicit_brand_and_persists_it():
    service = WeeklyBriefService(db=None)

    cockpit_module = types.ModuleType("app.services.media.cockpit_service")

    class DummyCockpitService:
        def __init__(self, db):
            self.db = db

        def get_cockpit_payload(self, *, virus_typ: str):
            return {
                "peix_epi_score": {
                    "national_score": 71.0,
                    "national_band": "hoch",
                    "national_impact_probability": 84.0,
                },
                "bento": {"tiles": []},
                "map": {"regions": {}},
                "recommendations": {"cards": []},
                "data_freshness": {},
            }

    cockpit_module.MediaCockpitService = DummyCockpitService

    with patch.dict(sys.modules, {"app.services.media.cockpit_service": cockpit_module}):
        with patch("app.services.media.weekly_brief_service.utc_now", return_value=datetime(2026, 4, 10, 9, 0, 0)):
            with patch.object(service, "_run_backtest_pitches", return_value=[]):
                with patch.object(service, "_save_to_db") as save_mock:
                    result = service.generate(brand="acme", virus_typ="Influenza A")

    assert result["summary"]["brand"] == "acme"
    save_mock.assert_called_once_with(ANY, ANY, ANY, "Influenza A", "acme")
