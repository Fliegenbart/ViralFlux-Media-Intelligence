from __future__ import annotations

from typing import Any


def load_cached_models(
    virus_typ: str,
    *,
    region: str,
    horizon_days: int,
    ml_models_dir: Any,
    event_model_artifact_name: str,
    default_forecast_region: str,
    default_decision_horizon_days: int,
    learned_probability_model_cls: Any,
    normalize_forecast_region_fn: Any,
    ensure_supported_horizon_fn: Any,
    model_artifact_dir_fn: Any,
    json_module: Any,
    pickle_module: Any,
    cache: dict[str, Any],
    cache_lock: Any,
    logger: Any,
) -> tuple[Any, Any, Any, dict[str, Any], Any | None] | None:
    from xgboost import XGBRegressor

    slug = virus_typ.lower().replace(" ", "_").replace("-", "_")
    region_code = normalize_forecast_region_fn(region)
    horizon = ensure_supported_horizon_fn(horizon_days)
    cache_key = f"{slug}|{region_code}|{horizon}"

    with cache_lock:
        if cache_key in cache:
            return cache[cache_key]

    model_dir = model_artifact_dir_fn(
        ml_models_dir,
        virus_typ=virus_typ,
        region=region_code,
        horizon_days=horizon,
    )
    metadata_path = model_dir / "metadata.json"

    if not metadata_path.exists() and region_code == default_forecast_region and horizon == default_decision_horizon_days:
        legacy_dir = ml_models_dir / slug
        legacy_metadata = legacy_dir / "metadata.json"
        if legacy_metadata.exists():
            model_dir = legacy_dir
            metadata_path = legacy_metadata

    if not metadata_path.exists():
        return None

    try:
        with open(metadata_path) as f:
            metadata = json_module.load(f)

        model_med = XGBRegressor()
        model_med.load_model(str(model_dir / "model_median.json"))

        model_lo = XGBRegressor()
        model_lo.load_model(str(model_dir / "model_lower.json"))

        model_hi = XGBRegressor()
        model_hi.load_model(str(model_dir / "model_upper.json"))

        event_model = None
        event_model_path = model_dir / event_model_artifact_name
        if event_model_path.exists():
            with open(event_model_path, "rb") as handle:
                loaded = pickle_module.load(handle)
            if isinstance(loaded, learned_probability_model_cls):
                event_model = loaded

        result = (model_med, model_lo, model_hi, metadata, event_model)

        with cache_lock:
            cache[cache_key] = result

        logger.info(
            f"Loaded XGBoost models from disk for {virus_typ}/{region_code}/h{horizon} "
            f"(version={metadata.get('version')}, "
            f"trained_at={metadata.get('trained_at')})"
        )
        return result
    except Exception as e:
        logger.warning(f"Failed to load models for {virus_typ}: {e}")
        return None


def invalidate_model_cache(
    virus_typ: str | None,
    *,
    virus_slug_fn: Any,
    cache: dict[str, Any],
    cache_lock: Any,
) -> None:
    with cache_lock:
        if virus_typ:
            prefix = f"{virus_slug_fn(virus_typ)}|"
            for key in list(cache.keys()):
                if key.startswith(prefix):
                    cache.pop(key, None)
        else:
            cache.clear()


def is_model_feature_compatibility_error(exc: Exception) -> bool:
    message = str(exc or "").lower()
    return (
        "feature shape mismatch" in message
        or "number of columns does not match" in message
        or "feature_names mismatch" in message
    )


def _loaded_model_expected_feature_count(model: Any | None) -> int | None:
    if model is None:
        return None
    try:
        booster = model.get_booster()
        return int(booster.num_features())
    except Exception:
        return None


def resolve_loaded_model_feature_names(
    *,
    metadata: dict[str, Any],
    live_feature_row: dict[str, Any],
    model: Any | None,
    meta_features: list[str],
) -> list[str]:
    explicit_feature_names = list(metadata.get("feature_names") or [])
    if explicit_feature_names:
        return explicit_feature_names

    feature_names = list(meta_features)
    if "horizon_days" in live_feature_row and "horizon_days" not in feature_names:
        expected_feature_count = _loaded_model_expected_feature_count(model)
        if expected_feature_count is None or expected_feature_count >= len(feature_names) + 1:
            feature_names.append("horizon_days")
    return feature_names
