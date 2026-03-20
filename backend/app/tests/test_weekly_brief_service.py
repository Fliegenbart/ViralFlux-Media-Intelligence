from app.services.media.weekly_brief_service import _dedupe_cards, _source_display_label, _tile_display_title


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
