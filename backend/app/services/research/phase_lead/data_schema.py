"""Typed observation rows and vintage filtering for phase-lead research models."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SourceType = Literal[
    "count",
    "wastewater_log",
    "wastewater_level",
    "are_count",
    "sentinel_composition",
    "hospital_count",
]


class ObservationKey(NamedTuple):
    source: str
    source_type: str
    observation_unit: str
    region_id: str | None
    pathogen: str
    event_date: date
    unit: str | None


class ObservationRow(BaseModel):
    """One point-in-time surveillance observation.

    `publication_date` is the main vintage gate. If `revision_date` is present,
    a historical issue date can only see revisions whose revision date has
    already passed.
    """

    model_config = ConfigDict(extra="forbid")

    source: str
    source_type: SourceType
    observation_unit: str
    region_id: str | None = None
    pathogen: str
    event_date: date
    report_date: date | None = None
    publication_date: date
    revision_date: date | None = None
    source_version: str | None = None
    value: float
    denominator: float | None = None
    unit: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_date", "report_date", "publication_date", "revision_date", mode="before")
    @classmethod
    def _parse_date(cls, value: Any) -> date | None:
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return date.fromisoformat(value[:10])
        raise TypeError(f"Cannot parse date value {value!r}")

    @model_validator(mode="after")
    def _reject_invalid_values(self) -> "ObservationRow":
        count_like = {"count", "are_count", "hospital_count", "sentinel_composition"}
        if self.source_type in count_like and self.value < 0 and not self.metadata.get("allow_negative"):
            raise ValueError(f"Negative value is invalid for source_type={self.source_type}")
        if self.denominator is not None and self.denominator < 0:
            raise ValueError("denominator must be non-negative")
        return self

    def vintage_key(self) -> ObservationKey:
        return ObservationKey(
            self.source,
            self.source_type,
            self.observation_unit,
            self.region_id,
            self.pathogen,
            self.event_date,
            self.unit,
        )

    def available_revision_date(self) -> date:
        return self.revision_date or self.publication_date


def filter_vintage(
    observations: Iterable[ObservationRow | dict[str, Any]],
    issue_date: date | datetime | str,
) -> list[ObservationRow]:
    """Return observations available as of `issue_date`.

    Multiple versions of the same observation key are collapsed to the latest
    revision that was available on the issue date. This prevents retrospective
    validation from seeing final revised data too early.
    """

    if isinstance(issue_date, datetime):
        issue = issue_date.date()
    elif isinstance(issue_date, str):
        issue = date.fromisoformat(issue_date[:10])
    else:
        issue = issue_date

    selected: dict[ObservationKey, ObservationRow] = {}
    for raw in observations:
        row = raw if isinstance(raw, ObservationRow) else ObservationRow.model_validate(raw)
        if row.publication_date > issue:
            continue
        if row.revision_date is not None and row.revision_date > issue:
            continue

        key = row.vintage_key()
        current = selected.get(key)
        if current is None:
            selected[key] = row
            continue

        row_rank = (row.available_revision_date(), row.publication_date, row.source_version or "")
        current_rank = (
            current.available_revision_date(),
            current.publication_date,
            current.source_version or "",
        )
        if row_rank >= current_rank:
            selected[key] = row

    return sorted(
        selected.values(),
        key=lambda row: (row.event_date, row.source, row.observation_unit, row.pathogen),
    )
