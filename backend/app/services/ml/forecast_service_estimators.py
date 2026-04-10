from __future__ import annotations

from typing import Any


def fit_holt_winters(
    y: Any,
    n_steps: int,
    *,
    np_module: Any,
    exponential_smoothing_cls: Any,
    logger: Any,
) -> Any:
    n = len(y)
    try:
        if n >= 104:
            sp = min(52, n // 2)
            hw_model = exponential_smoothing_cls(
                y,
                trend="add",
                seasonal="mul",
                seasonal_periods=sp,
                initialization_method="estimated",
            )
        elif n >= 8:
            sp = min(52, n // 2)
            hw_model = exponential_smoothing_cls(
                y,
                trend="add",
                seasonal="add",
                seasonal_periods=sp,
                initialization_method="estimated",
            )
        elif n >= 4:
            hw_model = exponential_smoothing_cls(
                y,
                trend="add",
                damped_trend=True,
                initialization_method="estimated",
            )
        else:
            recent_mean = float(np_module.mean(y[-min(3, n):]))
            return np_module.full(n_steps, max(0.0, recent_mean))

        hw_fit = hw_model.fit(optimized=True)
        forecast = hw_fit.forecast(n_steps)
        max_hist = float(np_module.max(y)) if len(y) > 0 else 1.0
        forecast = np_module.clip(forecast, 0.0, max_hist * 3.0)
        return forecast
    except Exception as e:
        logger.warning(f"Holt-Winters failed, using damped extrapolation: {e}")
        recent = y[-min(5, n):]
        slope = (recent[-1] - recent[0]) / max(len(recent) - 1, 1)
        base = float(y[-1])
        max_hist = float(np_module.max(y)) if len(y) > 0 else 1.0
        forecast = np_module.array([
            base + slope * (i + 1) * (0.85 ** i)
            for i in range(n_steps)
        ])
        return np_module.clip(forecast, 0.0, max_hist * 3.0)


def fit_ridge(
    df: Any,
    y: Any,
    n_steps: int,
    *,
    np_module: Any,
    ridge_cls: Any,
    logger: Any,
) -> tuple[Any, dict[str, float]]:
    feature_cols = [
        "lag1",
        "lag2",
        "lag3",
        "ma3",
        "ma5",
        "trends_score",
        "schulferien",
        "roc",
        "lab_positivity_rate",
        "lab_signal_available",
        "lab_baseline_mean",
        "lab_baseline_zscore",
    ]
    available = [c for c in feature_cols if c in df.columns]

    if len(available) < 2:
        return np_module.full(n_steps, y[-1]), {}

    try:
        X = df[available].values
        ridge = ridge_cls(alpha=1.0)
        ridge.fit(X, y)

        forecast: list[float] = []
        last_row = df[available].iloc[-1].values.copy()
        last_vals = list(y[-5:])

        for _ in range(n_steps):
            pred = float(ridge.predict(last_row.reshape(1, -1))[0])
            forecast.append(pred)
            last_vals.append(pred)
            if "lag1" in available:
                last_row[available.index("lag1")] = pred
            if "lag2" in available:
                last_row[available.index("lag2")] = last_vals[-2] if len(last_vals) >= 2 else pred
            if "lag3" in available:
                last_row[available.index("lag3")] = last_vals[-3] if len(last_vals) >= 3 else pred
            if "ma3" in available:
                last_row[available.index("ma3")] = np_module.mean(last_vals[-3:])
            if "ma5" in available:
                last_row[available.index("ma5")] = np_module.mean(last_vals[-5:])
            if "roc" in available:
                prev = last_vals[-2] if len(last_vals) >= 2 else 1.0
                last_row[available.index("roc")] = (pred - prev) / prev if prev != 0 else 0.0

        importance: dict[str, float] = {}
        total_abs = float(np_module.sum(np_module.abs(ridge.coef_))) + 1e-9
        for fname, coef in zip(available, ridge.coef_):
            importance[fname] = round(abs(float(coef)) / total_abs, 3)

        return np_module.array(forecast), importance
    except Exception as e:
        logger.warning(f"Ridge regression failed: {e}")
        return np_module.full(n_steps, y[-1]), {}


def fit_prophet(
    service: Any,
    virus_typ: str,
    n_steps: int,
    *,
    np_module: Any,
    logger: Any,
) -> Any | None:
    try:
        from app.services.fusion_engine.prophet_predictor import ProphetPredictor

        predictor = ProphetPredictor(service.db)
        result = predictor.fit_and_predict(
            virus_typ=virus_typ,
            forecast_days=n_steps,
        )

        if result and "forecast" in result and result["forecast"]:
            preds = [max(0.0, item["yhat"]) for item in result["forecast"]]
            return np_module.array(preds[:n_steps])
    except Exception as e:
        logger.warning(f"Prophet failed for {virus_typ}: {e}")

    return None
