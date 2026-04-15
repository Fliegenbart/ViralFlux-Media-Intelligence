from __future__ import annotations

from typing import Any

from app.services.ml.xgboost_runtime import resolve_xgboost_runtime_config


def build_direct_training_panel_from_frame(
    service,
    raw,
    *,
    horizon_days: int,
    n_splits: int,
    ensure_supported_horizon_fn,
    build_direct_target_frame_fn,
    min_direct_train_points: int,
    ridge_cls,
    time_series_split_cls,
    np_module,
    pd_module,
):
    horizon = ensure_supported_horizon_fn(horizon_days)
    direct = build_direct_target_frame_fn(raw, horizon_days=horizon)
    if direct.empty:
        return direct

    prophet_proxy = direct["current_y"].rolling(window=7, min_periods=1).mean().shift(1)
    direct["prophet_pred"] = prophet_proxy.fillna(direct["current_y"]).astype(float)

    oof = pd_module.DataFrame(index=direct.index, columns=["hw_pred", "ridge_pred"], dtype=float)
    feature_cols = service._direct_ridge_feature_columns(direct)
    n_time_splits = min(max(2, int(n_splits)), max(len(direct) // 8, 2))

    try:
        tscv = time_series_split_cls(n_splits=n_time_splits)
        split_iter = list(tscv.split(direct))
    except ValueError:
        split_iter = []

    for train_idx, val_idx in split_iter:
        if len(train_idx) < max(min_direct_train_points, 12) or len(val_idx) < 1:
            continue

        train_panel = direct.iloc[train_idx].copy()
        val_panel = direct.iloc[val_idx].copy()

        if feature_cols:
            ridge = ridge_cls(alpha=1.0)
            ridge.fit(
                train_panel[feature_cols].to_numpy(dtype=float),
                train_panel["y_target"].to_numpy(dtype=float),
            )
            ridge_preds = np_module.maximum(
                ridge.predict(val_panel[feature_cols].to_numpy(dtype=float)),
                0.0,
            )
            oof.loc[val_idx, "ridge_pred"] = ridge_preds

        for idx in val_idx:
            issue_date = pd_module.Timestamp(direct.iloc[idx]["issue_date"])
            history = raw.loc[raw["ds"] <= issue_date, "y"].to_numpy(dtype=float)
            if len(history) == 0:
                oof.loc[idx, "hw_pred"] = 0.0
                continue
            hw_forecast = service._fit_holt_winters(history, horizon)
            hw_step = min(horizon - 1, max(len(hw_forecast) - 1, 0))
            oof.loc[idx, "hw_pred"] = max(0.0, float(hw_forecast[hw_step]))

    causal_oof_fallback = direct["current_y"].astype(float)
    direct["hw_pred"] = oof["hw_pred"].ffill().fillna(causal_oof_fallback).astype(float)
    direct["ridge_pred"] = oof["ridge_pred"].ffill().fillna(causal_oof_fallback).astype(float)
    direct = direct.replace([np_module.inf, -np_module.inf], np_module.nan).fillna(0.0)
    return direct.reset_index(drop=True)


def build_live_direct_feature_row(
    service,
    raw,
    *,
    virus_typ: str,
    horizon_days: int,
    region: str,
    ensure_supported_horizon_fn,
    default_forecast_region,
    normalize_forecast_region_fn,
    build_direct_target_frame_fn,
    min_direct_train_points: int,
    ridge_cls,
    np_module,
):
    horizon = ensure_supported_horizon_fn(horizon_days)
    if raw.empty:
        return {}

    last_row = raw.iloc[-1].copy()
    history = raw["y"].to_numpy(dtype=float)
    hw_forecast = service._fit_holt_winters(history, horizon)
    hw_pred = max(0.0, float(hw_forecast[min(horizon - 1, max(len(hw_forecast) - 1, 0))]))

    direct_train = build_direct_target_frame_fn(raw, horizon_days=horizon)
    feature_cols = service._direct_ridge_feature_columns(direct_train) if not direct_train.empty else []
    if feature_cols and len(direct_train) >= max(min_direct_train_points, 12):
        ridge = ridge_cls(alpha=1.0)
        ridge.fit(
            direct_train[feature_cols].to_numpy(dtype=float),
            direct_train["y_target"].to_numpy(dtype=float),
        )
        ridge_row = np_module.array([[float(last_row.get(name, 0.0)) for name in feature_cols]], dtype=float)
        ridge_pred = max(0.0, float(ridge.predict(ridge_row)[0]))
    else:
        ridge_pred = max(0.0, float(last_row.get("y", 0.0)))

    prophet_forecast = (
        service._fit_prophet(virus_typ, horizon)
        if normalize_forecast_region_fn(region) == default_forecast_region
        else None
    )
    if prophet_forecast is not None and len(prophet_forecast) >= horizon:
        prophet_pred = max(0.0, float(prophet_forecast[horizon - 1]))
    else:
        prophet_pred = float(raw["y"].tail(min(7, len(raw))).mean())

    feature_row = service._build_meta_feature_row(
        last_row,
        hw_pred=hw_pred,
        ridge_pred=ridge_pred,
        prophet_pred=prophet_pred,
    )
    feature_row["horizon_days"] = float(horizon)
    return feature_row


def fit_xgboost_meta_from_panel(
    service,
    panel,
    *,
    target_column: str,
    model_config,
    meta_features,
    np_module,
):
    from xgboost import XGBRegressor

    available_meta = [f for f in meta_features if f in panel.columns]
    if "horizon_days" in panel.columns and "horizon_days" not in available_meta:
        available_meta.append("horizon_days")
    if not available_meta:
        raise ValueError("No direct meta features available for XGBoost fitting.")

    X = panel[available_meta].to_numpy(dtype=float)
    y = panel[target_column].to_numpy(dtype=float)
    X = np_module.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    cfg = service._resolve_xgb_quantile_config(model_config)
    cfg = {
        name: resolve_xgboost_runtime_config(params)
        for name, params in cfg.items()
    }

    model_median = XGBRegressor(**cfg["median"])
    model_median.fit(X, y)
    model_lower = XGBRegressor(**cfg["lower"])
    model_lower.fit(X, y)
    model_upper = XGBRegressor(**cfg["upper"])
    model_upper.fit(X, y)

    importance_raw = model_median.feature_importances_
    total = float(np_module.sum(importance_raw)) + 1e-9
    feature_importance = {
        fname: round(float(imp) / total, 3)
        for fname, imp in zip(available_meta, importance_raw)
    }
    return model_median, model_lower, model_upper, available_meta, feature_importance


def generate_oof_predictions(
    service,
    df,
    *,
    n_splits: int,
    time_series_split_cls,
    np_module,
    pd_module,
):
    y = df["y"].values
    tscv = time_series_split_cls(n_splits=n_splits)

    oof = pd_module.DataFrame(index=df.index, columns=["hw_pred", "ridge_pred"], dtype=float)
    oof[:] = np_module.nan

    for train_idx, val_idx in tscv.split(df):
        if len(train_idx) < 10 or len(val_idx) < 1:
            continue

        y_train = y[train_idx]
        n_val = len(val_idx)

        hw_preds = service._fit_holt_winters(y_train, n_val)
        oof.loc[val_idx, "hw_pred"] = hw_preds[:n_val]

        df_train = df.iloc[train_idx]
        ridge_preds, _ = service._fit_ridge(df_train, y_train, n_val)
        oof.loc[val_idx, "ridge_pred"] = ridge_preds[:n_val]

    history_series = pd_module.Series(y, index=df.index, dtype=float).ffill()
    causal_history_fallback = history_series.shift(1).fillna(0.0)
    oof["hw_pred"] = oof["hw_pred"].ffill().fillna(causal_history_fallback).astype(float)
    oof["ridge_pred"] = oof["ridge_pred"].ffill().fillna(causal_history_fallback).astype(float)
    return oof


def fit_xgboost_meta(
    service,
    df,
    oof,
    *,
    model_config,
    meta_features,
    np_module,
    logger,
):
    from xgboost import XGBRegressor

    df_meta = df.copy()
    df_meta["hw_pred"] = oof["hw_pred"].values
    df_meta["ridge_pred"] = oof["ridge_pred"].values
    df_meta["prophet_pred"] = df_meta["y"].rolling(window=7, min_periods=1).mean().shift(14)

    available_meta = [f for f in meta_features if f in df_meta.columns]
    X = df_meta[available_meta].values
    y = df_meta["y"].values
    X = np_module.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    cfg = service._resolve_xgb_quantile_config(model_config)
    cfg = {
        name: resolve_xgboost_runtime_config(params)
        for name, params in cfg.items()
    }

    model_median = XGBRegressor(**cfg["median"])
    model_median.fit(X, y)
    model_lower = XGBRegressor(**cfg["lower"])
    model_lower.fit(X, y)
    model_upper = XGBRegressor(**cfg["upper"])
    model_upper.fit(X, y)

    importance_raw = model_median.feature_importances_
    total = float(np_module.sum(importance_raw)) + 1e-9
    feature_importance = {
        fname: round(float(imp) / total, 3)
        for fname, imp in zip(available_meta, importance_raw)
    }

    logger.info(f"XGBoost meta-learner trained on {len(y)} samples, {len(available_meta)} features")
    return model_median, model_lower, model_upper, feature_importance
