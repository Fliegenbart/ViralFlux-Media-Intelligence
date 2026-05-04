from datetime import date

import pytest
from pydantic import ValidationError

from app.services.research.phase_lead.data_schema import ObservationRow, filter_vintage


def _obs(value: float, *, publication_date: date, revision_date: date | None = None) -> ObservationRow:
    return ObservationRow(
        source="survstat_cases",
        source_type="count",
        observation_unit="DE-BE",
        region_id="DE-BE",
        pathogen="SARS-CoV-2",
        event_date=date(2026, 1, 5),
        publication_date=publication_date,
        revision_date=revision_date,
        value=value,
    )


def test_observation_row_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        ObservationRow(
            source="survstat_cases",
            source_type="count",
            observation_unit="DE-BE",
            pathogen="SARS-CoV-2",
            event_date=date(2026, 1, 5),
            publication_date=date(2026, 1, 7),
            value=-1,
        )


def test_filter_vintage_uses_latest_revision_available_on_issue_date() -> None:
    original = _obs(10.0, publication_date=date(2026, 1, 7), revision_date=date(2026, 1, 7))
    revised = _obs(25.0, publication_date=date(2026, 1, 7), revision_date=date(2026, 1, 12))

    early = filter_vintage([original, revised], issue_date=date(2026, 1, 10))
    late = filter_vintage([original, revised], issue_date=date(2026, 1, 13))

    assert [row.value for row in early] == [10.0]
    assert [row.value for row in late] == [25.0]


def test_filter_vintage_excludes_future_publications() -> None:
    rows = [
        _obs(10.0, publication_date=date(2026, 1, 7), revision_date=date(2026, 1, 7)),
        _obs(30.0, publication_date=date(2026, 1, 20), revision_date=date(2026, 1, 20)),
    ]

    filtered = filter_vintage(rows, issue_date=date(2026, 1, 10))

    assert len(filtered) == 1
    assert filtered[0].value == 10.0
