"""Typed contracts for the regional as-of dataset layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceAlignmentRule:
    source_key: str
    source_tables: tuple[str, ...]
    source_grain: str
    regional_mapping: str
    alignment_rule: str
    freshness_rule: str
    missing_value_rule: str
    forward_safe_join_rule: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RegionalAsOfDatasetContract:
    dataset_name: str
    row_grain: str
    forecast_horizon_days: tuple[int, int]
    target_definition: str
    target_tables: tuple[str, ...]
    source_rules: tuple[SourceAlignmentRule, ...]
    validation_checks: tuple[str, ...]
    open_assumptions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["source_rules"] = [rule.to_dict() for rule in self.source_rules]
        return payload


@dataclass
class DatasetValidationReport:
    row_count: int
    duplicate_rows: int
    key_columns: tuple[str, ...]
    null_rates: dict[str, float] = field(default_factory=dict)
    illegal_future_leakage_checks: dict[str, Any] = field(default_factory=dict)
    source_coverage_overall: dict[str, float] = field(default_factory=dict)
    source_coverage_per_region: dict[str, dict[str, float]] = field(default_factory=dict)
    source_freshness_days: dict[str, dict[str, float | None]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_count": int(self.row_count),
            "duplicate_rows": int(self.duplicate_rows),
            "key_columns": list(self.key_columns),
            "null_rates": dict(self.null_rates),
            "illegal_future_leakage_checks": dict(self.illegal_future_leakage_checks),
            "source_coverage_overall": dict(self.source_coverage_overall),
            "source_coverage_per_region": dict(self.source_coverage_per_region),
            "source_freshness_days": dict(self.source_freshness_days),
            "warnings": list(self.warnings),
        }


@dataclass
class DatasetBuildResult:
    panel: Any
    dataset_contract: RegionalAsOfDatasetContract
    dataset_manifest: dict[str, Any]
    validation: DatasetValidationReport
    feature_dictionary: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": int(len(self.panel)) if self.panel is not None else 0,
            "dataset_contract": self.dataset_contract.to_dict(),
            "dataset_manifest": dict(self.dataset_manifest),
            "validation": self.validation.to_dict(),
            "feature_dictionary": list(self.feature_dictionary),
        }
