"""Cockpit backtest-summary builder.

Reads persisted regional-panel backtest artifacts (produced by
``regional_trainer`` + ``regional_trainer_backtest``) and turns them into
a pitch-friendly payload for the cockpit's Drawer V "Backtest".

Design-stance: the pitch story is a *ranking-validation* statement,
not a counterfactual-uplift claim. So the headline numbers are:
  - top-3 precision: in how many weeks did our top-3 Bundesländer
    include at least one of the actually-top-3 BL?
  - pr-auc: area under precision-recall for event detection
  - brier / ECE: calibration honesty
  - median lead days: how far ahead of SURVSTAT reporting we saw it
  - coverage of the walk-forward window: date-range, fold count,
    per-Bundesland breakdown

GELO can translate ranking hits into € themselves using their own
ROI elasticities — we don't own that counterfactual.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ML_MODELS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "ml_models"
    / "regional_panel"
)

_VIRUS_DIRS = {
    "Influenza A": "influenza_a",
    "Influenza B": "influenza_b",
    "RSV A": "rsv_a",
    "SARS-CoV-2": "sars_cov_2",
}

_BUNDESLAND_NAMES = {
    "BW": "Baden-Württemberg",
    "BY": "Bayern",
    "BE": "Berlin",
    "BB": "Brandenburg",
    "HB": "Bremen",
    "HH": "Hamburg",
    "HE": "Hessen",
    "MV": "Mecklenburg-Vorpommern",
    "NI": "Niedersachsen",
    "NW": "Nordrhein-Westfalen",
    "RP": "Rheinland-Pfalz",
    "SL": "Saarland",
    "SN": "Sachsen",
    "ST": "Sachsen-Anhalt",
    "SH": "Schleswig-Holstein",
    "TH": "Thüringen",
}


def _load_artifact(
    virus_typ: str,
    horizon_days: int,
    models_dir: Path | None = None,
) -> dict[str, Any] | None:
    base = models_dir or _ML_MODELS_DIR
    virus_dir = _VIRUS_DIRS.get(virus_typ)
    if virus_dir is None:
        return None
    path = base / virus_dir / f"horizon_{horizon_days}" / "backtest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "Could not read backtest artifact %s: %s", path, exc
        )
        return None


def _window_span(details: dict[str, Any]) -> dict[str, Any]:
    """Return {start, end, folds, weeks} covering the walk-forward window.

    Uses the first BL's timeline as the master index — all BLs share
    the same as_of_date schedule by construction of the regional panel.
    """
    dates: set[str] = set()
    for info in details.values():
        for entry in info.get("timeline", []) or []:
            d = entry.get("as_of_date")
            if d:
                dates.add(d[:10])
    if not dates:
        return {"start": None, "end": None, "folds": 0, "weeks": 0}
    sorted_dates = sorted(dates)
    weeks = len(sorted_dates)
    folds = weeks  # weekly walk-forward → one fold per unique date
    return {
        "start": sorted_dates[0],
        "end": sorted_dates[-1],
        "folds": folds,
        "weeks": weeks,
    }


def _per_bl_metrics(details: dict[str, Any]) -> list[dict[str, Any]]:
    """Shrink per-BL details to just what the UI needs."""
    rows: list[dict[str, Any]] = []
    for code, info in details.items():
        metrics = info.get("metrics") or {}
        rows.append(
            {
                "code": code,
                "name": info.get("bundesland_name")
                or _BUNDESLAND_NAMES.get(code, code),
                "windows": info.get("total_windows"),
                "precision_at_top3": metrics.get("precision_at_top3"),
                "precision": metrics.get("precision"),
                "recall": metrics.get("recall"),
                "pr_auc": metrics.get("pr_auc"),
                "brier_score": metrics.get("brier_score"),
                "ece": metrics.get("ece"),
                "activations": metrics.get("activations"),
                "events": metrics.get("events"),
            }
        )
    # Sort primarily by pr_auc desc — precision_at_top3 saturates at 1.0
    # for many BLs, which makes it a poor sort key. pr_auc is the more
    # discriminating score. Fall back to precision_at_top3 then name.
    rows.sort(
        key=lambda r: (
            -(r.get("pr_auc") or 0.0),
            -(r.get("precision_at_top3") or 0.0),
            r.get("name") or "",
        )
    )
    return rows


def _headline_metrics(aggregate: dict[str, Any]) -> dict[str, Any]:
    """Return only the numbers the Drawer V actually renders."""
    return {
        "precision_at_top3": aggregate.get("precision_at_top3"),
        "precision_at_top5": aggregate.get("precision_at_top5"),
        "pr_auc": aggregate.get("pr_auc"),
        "brier_score": aggregate.get("brier_score"),
        "ece": aggregate.get("ece"),
        "activation_false_positive_rate": aggregate.get(
            "activation_false_positive_rate"
        ),
        "median_lead_days": aggregate.get("median_lead_days"),
    }


def _quality_gate(artifact: dict[str, Any]) -> dict[str, Any] | None:
    gate = artifact.get("quality_gate")
    if not gate:
        return None
    return {
        "forecast_readiness": gate.get("forecast_readiness"),
        "overall_passed": gate.get("overall_passed"),
        "checks": {
            k: v
            for k, v in gate.items()
            if k.endswith("_passed") and k != "overall_passed"
        },
    }


def _weekly_hits(
    details: dict[str, Any],
    *,
    limit: int = 52,
) -> list[dict[str, Any]]:
    """Build a master weekly timeline: for each as_of_date, which BL
    did we call as top-k and which actually landed.

    Uses the first BL's timeline for the date index + reads each
    entry's predicted/observed top-k if the artifact carries it.
    Falls back gracefully when the artifact is older and only has
    per-BL activation flags.
    """
    # Collect all per-week predicted/observed events across BLs.
    # Field-name convention in the artifacts (see sample):
    #   "activated"                 -> bool: model flagged this BL
    #   "event_label"               -> 0/1 int: BL actually saw an event
    #   "event_probability_calibrated" / "_raw" -> the score used for Top-K
    per_week: dict[str, dict[str, Any]] = {}
    for code, info in details.items():
        for entry in info.get("timeline") or []:
            as_of = entry.get("as_of_date")
            if not as_of:
                continue
            key = as_of[:10]
            target = entry.get("target_date") or key
            bucket = per_week.setdefault(
                key,
                {
                    "as_of_date": key,
                    "target_date": target[:10],
                    "all_scored": [],
                    "observed_top": [],
                },
            )
            # Every BL has a per-fold score — we rebuild Top-K here
            # ourselves so we don't depend on a single "activated" flag
            # that may or may not track the Top-K rule.
            prob = entry.get("event_probability_calibrated")
            if prob is None:
                prob = entry.get("event_probability_raw")
            bucket["all_scored"].append(
                {"code": code, "probability": prob}
            )
            if int(entry.get("event_label") or 0) == 1:
                bucket["observed_top"].append(code)

    rows = list(per_week.values())
    rows.sort(key=lambda r: r["as_of_date"])

    for row in rows:
        all_scored = row.pop("all_scored")
        all_scored.sort(key=lambda p: -(p.get("probability") or 0.0))
        row["predicted_top"] = all_scored[:3]
        predicted_codes = {p["code"] for p in row["predicted_top"]}
        observed_codes = set(row["observed_top"])
        row["hits"] = sorted(predicted_codes & observed_codes)
        row["misses"] = sorted(predicted_codes - observed_codes)
        row["false_negatives"] = sorted(observed_codes - predicted_codes)
        row["was_hit"] = len(row["hits"]) > 0

    if limit and len(rows) > limit:
        rows = rows[-limit:]
    return rows


def build_backtest_summary(
    *,
    virus_typ: str = "Influenza A",
    horizon_days: int = 7,
    models_dir: Path | None = None,
    weeks_to_surface: int = 52,
) -> dict[str, Any]:
    """Return the pitch-friendly backtest payload for Drawer V."""
    artifact = _load_artifact(virus_typ, horizon_days, models_dir)
    if artifact is None:
        return {
            "virus_typ": virus_typ,
            "horizon_days": horizon_days,
            "available": False,
            "reason": (
                f"Kein Backtest-Artefakt für {virus_typ}/h={horizon_days}d. "
                "Training eventuell noch nicht abgeschlossen."
            ),
        }

    details = artifact.get("details") or {}
    aggregate = artifact.get("aggregate_metrics") or {}
    baselines = artifact.get("baselines") or {}
    selected_tau = artifact.get("selected_tau")
    selected_kappa = artifact.get("selected_kappa")
    action_threshold = artifact.get("action_threshold")
    event_version = artifact.get("event_definition_version")

    window = _window_span(details)
    headline = _headline_metrics(aggregate)
    per_bl = _per_bl_metrics(details)
    gate = _quality_gate(artifact)
    weekly = _weekly_hits(details, limit=weeks_to_surface)

    # Baselines — we mostly care whether the model beat persistence
    baseline_precision_top3 = None
    baseline_pr_auc = None
    if isinstance(baselines, dict):
        pers = baselines.get("persistence") or {}
        baseline_precision_top3 = pers.get("precision_at_top3")
        baseline_pr_auc = pers.get("pr_auc")

    return {
        "virus_typ": virus_typ,
        "horizon_days": horizon_days,
        "event_definition_version": event_version,
        "available": True,
        "window": window,
        "headline": headline,
        "baselines": {
            "persistence_precision_at_top3": baseline_precision_top3,
            "persistence_pr_auc": baseline_pr_auc,
        },
        "calibration": {
            "tau": selected_tau,
            "kappa": selected_kappa,
            "action_threshold": action_threshold,
        },
        "quality_gate": gate,
        "per_bundesland": per_bl,
        "weekly_hits": weekly,
    }
