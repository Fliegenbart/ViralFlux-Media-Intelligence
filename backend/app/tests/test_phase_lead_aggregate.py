from app.services.research.phase_lead.aggregate import build_phase_lead_aggregate_snapshot


def _snapshot(
    virus_typ: str,
    *,
    observation_count: int,
    source_count: int,
    latest_event_date: str,
    converged: bool = True,
    fit_mode: str = "map_optimization",
    warning_count: int = 0,
    regions: list[dict] | None = None,
) -> dict:
    source_names = ["wastewater", "survstat", "are", "notaufnahme"][:source_count]
    return {
        "module": "phase_lead_graph_renewal_filter",
        "version": "plgrf_live_v0",
        "mode": "research",
        "as_of": "2026-05-05",
        "virus_typ": virus_typ,
        "horizons": [3, 5, 7, 10, 14],
        "summary": {
            "data_source": "live_database",
            "fit_mode": fit_mode,
            "observation_count": observation_count,
            "window_start": "2026-02-17",
            "window_end": "2026-04-27",
            "converged": converged,
            "objective_value": 100.0,
            "data_vintage_hash": f"data-{virus_typ}",
            "config_hash": f"config-{virus_typ}",
            "top_region": regions[0]["region_code"] if regions else None,
            "warning_count": warning_count,
        },
        "sources": {
            source: {
                "rows": 10,
                "latest_event_date": latest_event_date,
                "units": ["HE", "NI"],
            }
            for source in source_names
        },
        "regions": regions
        or [
            {
                "region_code": "HE",
                "region": "Hessen",
                "current_level": 5.0,
                "current_growth": 0.2,
                "p_up_h7": 0.8,
                "p_surge_h7": 0.4,
                "p_front": 0.2,
                "eeb": 10.0,
                "gegb": 40.0,
                "source_rows": 40,
            }
        ],
        "rankings": {virus_typ: []},
        "warnings": [],
    }


def test_aggregate_weights_are_normalized_and_reward_data_quality() -> None:
    strong = _snapshot(
        "Influenza A",
        observation_count=900,
        source_count=4,
        latest_event_date="2026-05-01",
    )
    weak = _snapshot(
        "RSV A",
        observation_count=100,
        source_count=1,
        latest_event_date="2026-03-20",
        fit_mode="fast_initialization",
        warning_count=2,
    )

    aggregate = build_phase_lead_aggregate_snapshot({"Influenza A": strong, "RSV A": weak})

    weights = {
        item["virus_typ"]: item["weight"]
        for item in aggregate["aggregate"]["virus_weights"]
    }
    assert round(sum(weights.values()), 6) == 1.0
    assert weights["Influenza A"] > weights["RSV A"]


def test_aggregate_ranking_uses_weighted_regional_signal_and_reports_drivers() -> None:
    influenza = _snapshot(
        "Influenza A",
        observation_count=400,
        source_count=4,
        latest_event_date="2026-05-01",
        regions=[
            {
                "region_code": "HE",
                "region": "Hessen",
                "current_level": 2.0,
                "current_growth": 0.05,
                "p_up_h7": 0.3,
                "p_surge_h7": 0.1,
                "p_front": 0.1,
                "eeb": 5.0,
                "gegb": 10.0,
                "source_rows": 20,
            },
            {
                "region_code": "NI",
                "region": "Niedersachsen",
                "current_level": 6.0,
                "current_growth": 0.2,
                "p_up_h7": 0.9,
                "p_surge_h7": 0.6,
                "p_front": 0.2,
                "eeb": 20.0,
                "gegb": 50.0,
                "source_rows": 30,
            },
        ],
    )
    sars = _snapshot(
        "SARS-CoV-2",
        observation_count=400,
        source_count=4,
        latest_event_date="2026-05-01",
        regions=[
            {
                "region_code": "HE",
                "region": "Hessen",
                "current_level": 3.0,
                "current_growth": 0.1,
                "p_up_h7": 0.4,
                "p_surge_h7": 0.2,
                "p_front": 0.1,
                "eeb": 6.0,
                "gegb": 20.0,
                "source_rows": 15,
            },
            {
                "region_code": "NI",
                "region": "Niedersachsen",
                "current_level": 5.0,
                "current_growth": 0.15,
                "p_up_h7": 0.7,
                "p_surge_h7": 0.5,
                "p_front": 0.2,
                "eeb": 18.0,
                "gegb": 40.0,
                "source_rows": 25,
            },
        ],
    )

    aggregate = build_phase_lead_aggregate_snapshot(
        {"Influenza A": influenza, "SARS-CoV-2": sars}
    )

    assert aggregate["virus_typ"] == "Gesamt"
    assert aggregate["summary"]["top_region"] == "NI"
    assert aggregate["regions"][0]["region_code"] == "NI"
    assert aggregate["regions"][0]["gegb"] > aggregate["regions"][1]["gegb"]
    drivers = aggregate["aggregate"]["drivers_by_region"]["NI"]
    assert [driver["virus_typ"] for driver in drivers[:2]] == ["Influenza A", "SARS-CoV-2"]
