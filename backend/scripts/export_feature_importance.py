#!/usr/bin/env python3
"""Export XGBoost feature importance for persisted regional H7 pilot models.

The script reads model artifacts from disk, extracts XGBoost importance scores,
and writes a JSON diagnostic report. It does not use the database and does not
train or modify model files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_ROOT = Path("/app/app/ml_models/regional_panel_h7_pilot_only_v3")
DEFAULT_HORIZON_DAYS = 7
IMPORTANCE_TYPES = ("gain", "weight", "cover")
MODEL_ROLE_FILES = {
    "classifier": "classifier.json",
    "regressor_median": "regressor_median.json",
    "model_median": "model_median.json",
    "quantile_median": "q0500.json",
}
AUTO_MODEL_FILE_PREFERENCE = (
    "model_median.json",
    "classifier.json",
    "regressor_median.json",
    "q0500.json",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--virus", required=True, help="Virus type, for example 'Influenza A'.")
    parser.add_argument("--horizon-days", type=int, default=DEFAULT_HORIZON_DAYS)
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=DEFAULT_MODEL_ROOT,
        help=(
            "Model root or direct horizon directory. Defaults to "
            "/app/app/ml_models/regional_panel_h7_pilot_only_v3."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSON output path. Defaults to <resolved_model_dir>/feature_importance.json.",
    )
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument(
        "--model-role",
        choices=("auto", *MODEL_ROLE_FILES.keys()),
        default="auto",
        help="Which model artifact to inspect. Auto prefers model_median, classifier, regressor_median, then q0500.",
    )
    parser.add_argument(
        "--compare-to",
        type=Path,
        default=None,
        help="Optional model file, horizon dir, or model root to compare against.",
    )
    return parser.parse_args()


def _virus_slug(virus_typ: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", virus_typ.lower())
    return slug.strip("_")


def _horizon_subdir(horizon_days: int) -> str:
    return f"horizon_{int(horizon_days)}"


def _has_model_file(path: Path) -> bool:
    if not path.is_dir():
        return False
    if any((path / name).exists() for name in AUTO_MODEL_FILE_PREFERENCE):
        return True
    return any(path.glob("model_*.json"))


def _summary_artifact_candidates(
    *,
    base: Path,
    virus_typ: str,
) -> list[Path]:
    candidates: list[Path] = []
    for summary_path in sorted(base.glob("*summary*.json")):
        try:
            payload = _read_json(summary_path)
        except Exception:
            continue
        virus_payload = (payload.get("viruses") or {}).get(virus_typ)
        runs = virus_payload.get("runs") if isinstance(virus_payload, dict) else None
        if not isinstance(runs, list):
            continue
        preferred = [row for row in runs if isinstance(row, dict) and row.get("retained")]
        ordered_rows = preferred or [row for row in runs if isinstance(row, dict)]
        for row in ordered_rows:
            artifact_dir = row.get("artifact_dir")
            if artifact_dir:
                candidates.append(Path(str(artifact_dir)))
    return candidates


def _resolve_model_dir(
    *,
    model_dir: Path,
    virus_typ: str,
    horizon_days: int,
) -> Path:
    base = Path(model_dir)
    horizon_name = _horizon_subdir(horizon_days)
    slug = _virus_slug(virus_typ)

    candidates = [
        base,
        base / horizon_name,
        base / slug / horizon_name,
    ]
    candidates.extend(_summary_artifact_candidates(base=base, virus_typ=virus_typ))
    candidates.extend(sorted((base / slug).glob(f"*/{horizon_name}")))
    candidates.extend(sorted((base / slug).glob(f"*/{slug}/{horizon_name}")))

    for candidate in candidates:
        if _has_model_file(candidate):
            return candidate

    expected = base / slug / horizon_name
    raise FileNotFoundError(
        f"No model_*.json files found for {virus_typ} h{horizon_days}. "
        f"Checked {expected} and compatible direct/nested model directories."
    )


def _choose_model_file(model_dir: Path, *, model_role: str = "auto") -> Path:
    if model_role != "auto":
        file_name = MODEL_ROLE_FILES[model_role]
        model_file = model_dir / file_name
        if model_file.exists():
            return model_file
        raise FileNotFoundError(f"Expected {file_name} in {model_dir}")

    for file_name in AUTO_MODEL_FILE_PREFERENCE:
        model_file = model_dir / file_name
        if model_file.exists():
            return model_file

    candidates = sorted(model_dir.glob("model_*.json"))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(f"No model_*.json files found in {model_dir}")
    names = ", ".join(path.name for path in candidates)
    raise ValueError(
        f"Multiple model files found in {model_dir} but no model_median.json: {names}"
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _coerce_feature_names(payload: Any, *, preferred_keys: tuple[str, ...] = ()) -> list[str]:
    if isinstance(payload, list):
        return [str(item) for item in payload]
    if isinstance(payload, dict):
        for key in (*preferred_keys, "feature_names", "features", "selected_features"):
            value = payload.get(key)
            if isinstance(value, list):
                return [str(item) for item in value]
    return []


def _feature_names_from_selection(selection: dict[str, Any] | None) -> list[str]:
    if not selection:
        return []
    include_columns = selection.get("include_columns")
    if isinstance(include_columns, list) and include_columns:
        return [str(item) for item in include_columns]
    return []


def _summary_candidates(model_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for parent in [model_dir, *model_dir.parents[:4]]:
        candidates.extend(parent.glob("*summary*.json"))
        summary = parent / "summary.json"
        if summary.exists():
            candidates.append(summary)
    return sorted(set(candidates))


def _preferred_feature_name_keys(model_file: Path, model_role: str) -> tuple[str, ...]:
    file_name = model_file.name
    if model_role == "classifier" or file_name == "classifier.json":
        return ("event_feature_columns", "feature_columns")
    if "regressor" in file_name or file_name.startswith("q"):
        return ("feature_columns", "hierarchy_feature_columns")
    return ("feature_names", "feature_columns", "event_feature_columns")


def _load_feature_names(
    model_dir: Path,
    virus_typ: str | None = None,
    *,
    model_file: Path | None = None,
    model_role: str = "auto",
) -> list[str]:
    preferred_keys = (
        _preferred_feature_name_keys(model_file, model_role)
        if model_file is not None
        else ()
    )
    feature_names_path = model_dir / "feature_names.json"
    if feature_names_path.exists():
        names = _coerce_feature_names(_read_json(feature_names_path), preferred_keys=preferred_keys)
        if names:
            return names

    metadata_path = model_dir / "metadata.json"
    if metadata_path.exists():
        names = _coerce_feature_names(_read_json(metadata_path), preferred_keys=preferred_keys)
        if names:
            return names

    for summary_path in _summary_candidates(model_dir):
        try:
            payload = _read_json(summary_path)
        except Exception:
            continue
        virus_rows = (payload.get("viruses") or {}) if isinstance(payload, dict) else {}
        rows = []
        if virus_typ and isinstance(virus_rows.get(virus_typ), dict):
            rows.append(virus_rows[virus_typ])
        if isinstance(payload, dict):
            rows.append(payload)
        for row in rows:
            names = _coerce_feature_names(row, preferred_keys=preferred_keys)
            if names:
                return names
            runs = row.get("runs") if isinstance(row, dict) else None
            if isinstance(runs, list):
                for run in runs:
                    names = _feature_names_from_selection(
                        run.get("feature_selection") if isinstance(run, dict) else None
                    )
                    if names:
                        return names
    return []


def _load_booster_scores(model_file: Path) -> tuple[dict[str, float], dict[str, float], dict[str, float], list[str]]:
    try:
        import xgboost as xgb
    except ImportError as exc:
        raise RuntimeError("xgboost is required to export feature importance") from exc

    booster = xgb.Booster()
    booster.load_model(str(model_file))
    feature_names = list(getattr(booster, "feature_names", None) or [])
    scores = []
    for importance_type in IMPORTANCE_TYPES:
        raw = booster.get_score(importance_type=importance_type)
        scores.append({str(key): float(value) for key, value in raw.items()})
    return scores[0], scores[1], scores[2], feature_names


def _feature_label(raw_key: str, feature_names: list[str]) -> str:
    match = re.fullmatch(r"f(\d+)", str(raw_key))
    if match:
        index = int(match.group(1))
        if 0 <= index < len(feature_names):
            return feature_names[index]
    return str(raw_key)


def _build_feature_rows(
    *,
    feature_names: list[str],
    gain: dict[str, float],
    weight: dict[str, float],
    cover: dict[str, float],
) -> list[dict[str, Any]]:
    mapped: dict[str, dict[str, float]] = {}
    for raw_key in sorted(set(gain) | set(weight) | set(cover)):
        name = _feature_label(raw_key, feature_names)
        row = mapped.setdefault(
            name,
            {
                "gain_importance": 0.0,
                "weight_importance": 0.0,
                "cover_importance": 0.0,
            },
        )
        row["gain_importance"] += float(gain.get(raw_key, 0.0))
        row["weight_importance"] += float(weight.get(raw_key, 0.0))
        row["cover_importance"] += float(cover.get(raw_key, 0.0))

    rows = [{"name": name, **scores} for name, scores in mapped.items()]
    return sorted(
        rows,
        key=lambda row: (
            float(row["gain_importance"]),
            float(row["weight_importance"]),
            row["name"],
        ),
        reverse=True,
    )


def _load_importance_report(
    *,
    virus_typ: str,
    horizon_days: int,
    model_dir: Path,
    model_role: str = "auto",
) -> dict[str, Any]:
    resolved_dir = _resolve_model_dir(
        model_dir=model_dir,
        virus_typ=virus_typ,
        horizon_days=horizon_days,
    )
    model_file = _choose_model_file(resolved_dir, model_role=model_role)
    gain, weight, cover, booster_feature_names = _load_booster_scores(model_file)
    sidecar_feature_names = _load_feature_names(
        resolved_dir,
        virus_typ=virus_typ,
        model_file=model_file,
        model_role=model_role,
    )
    feature_names = booster_feature_names or sidecar_feature_names
    features = _build_feature_rows(
        feature_names=feature_names,
        gain=gain,
        weight=weight,
        cover=cover,
    )
    return {
        "virus_typ": virus_typ,
        "horizon_days": int(horizon_days),
        "importance_type": "gain",
        "model_dir": str(resolved_dir),
        "model_file": str(model_file),
        "model_role": model_role,
        "feature_name_source": (
            "booster" if booster_feature_names else "sidecar" if sidecar_feature_names else "raw_booster_keys"
        ),
        "feature_count": len(features),
        "features": features,
    }


def _compare_reports(current: dict[str, Any], baseline: dict[str, Any]) -> list[dict[str, Any]]:
    current_map = {row["name"]: row for row in current.get("features") or []}
    baseline_map = {row["name"]: row for row in baseline.get("features") or []}
    rows = []
    for name in sorted(set(current_map) | set(baseline_map)):
        current_gain = float((current_map.get(name) or {}).get("gain_importance") or 0.0)
        baseline_gain = float((baseline_map.get(name) or {}).get("gain_importance") or 0.0)
        rows.append(
            {
                "name": name,
                "gain_importance": current_gain,
                "baseline_gain_importance": baseline_gain,
                "gain_delta": current_gain - baseline_gain,
            }
        )
    return sorted(rows, key=lambda row: abs(float(row["gain_delta"])), reverse=True)


def _write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _print_text(report: dict[str, Any], *, limit: int = 10) -> None:
    print(
        f"Feature importance: {report['virus_typ']} h{report['horizon_days']} "
        f"({report['feature_count']} features)"
    )
    print(f"Model: {report['model_file']}")
    print("")
    for index, row in enumerate((report.get("features") or [])[:limit], start=1):
        print(
            f"{index:>2}. {row['name']} "
            f"gain={row['gain_importance']:.6g} "
            f"weight={row['weight_importance']:.6g} "
            f"cover={row['cover_importance']:.6g}"
        )
    comparison = report.get("comparison")
    if comparison:
        print("")
        print("Largest gain deltas")
        for index, row in enumerate(comparison[:limit], start=1):
            print(
                f"{index:>2}. {row['name']} "
                f"current={row['gain_importance']:.6g} "
                f"baseline={row['baseline_gain_importance']:.6g} "
                f"delta={row['gain_delta']:.6g}"
            )


def main() -> int:
    args = _parse_args()
    report = _load_importance_report(
        virus_typ=args.virus,
        horizon_days=args.horizon_days,
            model_dir=args.model_dir,
            model_role=args.model_role,
    )
    if args.compare_to:
        baseline_model_dir = args.compare_to
        if baseline_model_dir.is_file():
            baseline_model_dir = baseline_model_dir.parent
        baseline = _load_importance_report(
            virus_typ=args.virus,
            horizon_days=args.horizon_days,
            model_dir=baseline_model_dir,
            model_role=args.model_role,
        )
        report["comparison_model_file"] = baseline["model_file"]
        report["comparison"] = _compare_reports(report, baseline)

    output_path = args.output or (Path(report["model_dir"]) / "feature_importance.json")
    _write_report(report, output_path)
    report["output_path"] = str(output_path)

    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_text(report)
        print("")
        print(f"JSON written to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
