"""Forecast-Pipeline Nowcast-Extension (A1 Root-Cause-Fix, 2026-04-21).

Problem (pre-2026-04-21):
    ``prepare_training_data`` liefert einen DataFrame, dessen ``ds``-Spalte
    am letzten AMELAG-Abwasser-Datum endet (heute typischerweise ``today - 13``).
    ``forecast_service_inference`` setzte ``issue_date = df["ds"].max()`` und
    rief ``_expand_forecast_trajectory(issue_date, horizon=7, ...)`` auf.
    Die resultierenden Forecast-Punkte lagen deshalb bei ``today-6 .. today+1``
    — fast vollständig in der Vergangenheit. Das Cockpit zeigte deshalb
    einen retrospektiven Fan ohne echte Zukunfts-Trajektorie; das Integrity-
    Gate hat das heute mit Readiness ``DATA_STALE`` markiert.

Fix-Ansatz:
    Wir extendieren den Training-/Inference-Frame konservativ per Forward-Fill
    bis ``today``. Alle externen Signale (``y``, ``trends_score``, ``amelag_pred``,
    ``xd_load``, ``survstat_incidence``, ``lab_*``) behalten ihren letzten
    bekannten Wert. Lag-Features (``lag1..lag3``, ``ma3``, ``ma5``, ``roc``,
    ``trend_momentum_7d``, ``amelag_lag4/7``, ``xdisease_lag7/14``,
    ``survstat_lag7/14``) werden aus dem erweiterten ``y`` neu berechnet.
    ``schulferien`` wird pro Tag via Callback neu bestimmt (Kalenderfakt).

    Danach ist ``df.iloc[-1]`` eine Feature-Zeile **für today**; downstream
    Code (``_build_live_direct_feature_row`` etc.) muss nicht angepasst
    werden, weil er bereits ``raw.iloc[-1]`` verwendet.

Safety:
    * Extension läuft nur, wenn die Lücke ≤ ``FEATURE_EXTENSION_MAX_GAP_DAYS``
      (default 21). Größere Lücken heißen Pipeline-Ausfall — Forward-Fill
      über so lange Zeiträume wäre nicht vertretbar.
    * Bei Lücken ≤ 0 (df aktuell oder in der Zukunft) ist die Funktion
      no-op.
    * Das Training sieht diese Funktion nie. Sie greift nur in den Live-
      Inference-Pfad ein, damit wir keine gefakten Training-Samples
      erzeugen.

Transparenz:
    Die Funktion gibt neben dem erweiterten Frame auch die Metadaten
    ``feature_as_of`` (ISO-Datum des letzten echten Punktes) und
    ``days_forward_filled`` zurück. ``forecast_service_inference``
    persistiert diese in der ml_forecasts-Zeile (via features_used) und das
    Cockpit rendert sie als "Features as of …"-Badge.
"""

from __future__ import annotations

from typing import Any, Callable


FEATURE_EXTENSION_MAX_GAP_DAYS = 21


def extend_training_frame_to_today(
    df: Any,
    *,
    today: Any,
    is_holiday_fn: Callable[[Any], bool] | None,
    pd_module: Any,
    np_module: Any,
    timedelta_cls: Any,
    max_gap_days: int = FEATURE_EXTENSION_MAX_GAP_DAYS,
    logger: Any = None,
) -> tuple[Any, dict[str, Any]]:
    """Forward-fill the feature frame from its last ``ds`` up to ``today``.

    Returns ``(extended_df, meta)``. ``meta`` keys:
        * ``feature_as_of``: ISO date string of the last real (non-forward-filled)
          ``ds`` value. When ``days_forward_filled == 0``, equals ``today``.
        * ``days_forward_filled``: int ≥ 0.
        * ``applied``: bool. False when the gap exceeded ``max_gap_days``
          or the frame was already current.
        * ``reason``: short tag ("no_gap" | "extended" | "gap_too_large" |
          "empty_frame") for logs / cockpit transparency.
    """
    meta: dict[str, Any] = {
        "feature_as_of": None,
        "days_forward_filled": 0,
        "applied": False,
        "reason": "no_gap",
    }

    if df is None or getattr(df, "empty", True):
        meta["reason"] = "empty_frame"
        return df, meta

    # Normalise ``today`` and ``ds`` to the same pandas Timestamp type.
    today_ts = pd_module.Timestamp(today).normalize()
    last_ts = pd_module.Timestamp(df["ds"].max()).normalize()
    meta["feature_as_of"] = last_ts.date().isoformat()

    gap_days = int((today_ts - last_ts).days)
    if gap_days <= 0:
        # Frame is already current (or somehow ahead of today).
        meta["applied"] = False
        meta["reason"] = "no_gap"
        return df, meta
    if gap_days > max_gap_days:
        if logger is not None:
            logger.warning(
                "Feature-Pipeline-Lücke %sd > max %sd — extension übersprungen "
                "(feature_as_of=%s, today=%s).",
                gap_days,
                max_gap_days,
                meta["feature_as_of"],
                today_ts.date().isoformat(),
            )
        meta["applied"] = False
        meta["reason"] = "gap_too_large"
        return df, meta

    # Build the extension rows (one per day from last_ts+1 to today_ts).
    extension_dates = pd_module.date_range(
        start=last_ts + timedelta_cls(days=1),
        end=today_ts,
        freq="D",
    )
    if len(extension_dates) == 0:
        return df, meta

    last_row = df.iloc[-1].to_dict()
    # Columns whose last known value we want to carry forward as-is. Lag
    # features are deliberately excluded — they get recomputed below.
    carry_cols = [
        "y",
        "amelag_pred",
        "trends_score",
        "xd_load",
        "survstat_incidence",
        "lab_positivity_rate",
        "lab_signal_available",
        "lab_baseline_mean",
        "lab_baseline_zscore",
        "region",
    ]
    extension_rows = []
    for ds in extension_dates:
        row: dict[str, Any] = {col: last_row.get(col, 0.0) for col in carry_cols if col in df.columns}
        row["ds"] = ds
        if is_holiday_fn is not None and "schulferien" in df.columns:
            try:
                row["schulferien"] = 1.0 if is_holiday_fn(ds.to_pydatetime()) else 0.0
            except Exception:
                row["schulferien"] = float(last_row.get("schulferien", 0.0))
        elif "schulferien" in df.columns:
            row["schulferien"] = float(last_row.get("schulferien", 0.0))
        extension_rows.append(row)

    extended = pd_module.concat(
        [df, pd_module.DataFrame(extension_rows)], ignore_index=True
    ).sort_values("ds").reset_index(drop=True)

    # Recompute lag-based features across the full (extended) series so the
    # last row is a faithful "today" feature vector.
    y = extended["y"]
    if "lag1" in extended.columns:
        extended["lag1"] = y.shift(1)
    if "lag2" in extended.columns:
        extended["lag2"] = y.shift(2)
    if "lag3" in extended.columns:
        extended["lag3"] = y.shift(3)
    if "ma3" in extended.columns:
        extended["ma3"] = y.rolling(window=3, min_periods=1).mean().shift(1)
    if "ma5" in extended.columns:
        extended["ma5"] = y.rolling(window=5, min_periods=1).mean().shift(1)
    if "roc" in extended.columns:
        extended["roc"] = y.pct_change().shift(1)
    if "trend_momentum_7d" in extended.columns:
        y_shifted = y.shift(7).replace(0, np_module.nan)
        extended["trend_momentum_7d"] = y.diff(periods=7) / y_shifted

    amelag = extended.get("amelag_pred")
    if amelag is not None:
        if "amelag_lag4" in extended.columns:
            extended["amelag_lag4"] = amelag.shift(4)
        if "amelag_lag7" in extended.columns:
            extended["amelag_lag7"] = amelag.shift(7)

    xd_load = extended.get("xd_load")
    if xd_load is not None:
        if "xdisease_lag7" in extended.columns:
            extended["xdisease_lag7"] = xd_load.shift(7)
        if "xdisease_lag14" in extended.columns:
            extended["xdisease_lag14"] = xd_load.shift(14)

    survstat = extended.get("survstat_incidence")
    if survstat is not None:
        if "survstat_lag7" in extended.columns:
            extended["survstat_lag7"] = survstat.shift(7)
        if "survstat_lag14" in extended.columns:
            extended["survstat_lag14"] = survstat.shift(14)

    lab_positivity = extended.get("lab_positivity_rate")
    if lab_positivity is not None and "lab_positivity_lag7" in extended.columns:
        extended["lab_positivity_lag7"] = lab_positivity.shift(7)

    # Sanitise: replace inf / NaN introduced by divisions (trend_momentum_7d
    # on flat tails can divide by zero even after the replace() above if the
    # constant stretch is shorter than 7 days).
    extended = extended.replace([np_module.inf, -np_module.inf], np_module.nan)
    extended = extended.fillna(0.0)

    meta["applied"] = True
    meta["days_forward_filled"] = gap_days
    meta["reason"] = "extended"

    if logger is not None:
        logger.info(
            "Feature-Frame extendiert: %sd forward-fill (feature_as_of=%s → today=%s).",
            gap_days,
            meta["feature_as_of"],
            today_ts.date().isoformat(),
        )

    return extended, meta
