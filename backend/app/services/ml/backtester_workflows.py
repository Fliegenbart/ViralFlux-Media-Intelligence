from __future__ import annotations

from datetime import timedelta
import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def run_market_simulation(
    service,
    *,
    virus_typ: str = "Influenza A",
    target_source: str = "RKI_ARE",
    days_back: int = 730,
    horizon_days: int = 7,
    min_train_points: int = 20,
    delay_rules: Optional[dict[str, int]] = None,
    strict_vintage_mode: bool = True,
    bundesland: str = "",
) -> dict:
    """Mode A: Markt-Check ohne Kundendaten gegen externe RKI-Proxy-Targets."""
    service._scores_cache = {}
    service.strict_vintage_mode = bool(strict_vintage_mode)
    logger.info(
        "Starte Markt-Simulation: virus=%s, target_source=%s, days_back=%s, bundesland=%s",
        virus_typ, target_source, days_back, bundesland or "Gesamt",
    )

    try:
        target_df, target_meta = service._load_market_target(
            target_source=target_source,
            days_back=days_back,
            bundesland=bundesland,
        )
    except Exception as exc:
        return {"error": str(exc)}

    if target_df.empty or len(target_df) < 8:
        return {
            "error": (
                f"Zu wenig Daten für Markt-Simulation ({len(target_df)} Punkte). "
                "Mindestens 8 erforderlich."
            ),
            "target_source": target_meta.get("target_source"),
            "target_label": target_meta.get("target_label"),
        }

    n_available = len(target_df)
    if min_train_points <= 0:
        min_train_points = max(20, min(150, int(n_available * 0.6)))
        logger.info(
            "Auto min_train_points=%d (data: %d points)",
            min_train_points, n_available,
        )
    elif min_train_points >= n_available:
        min_train_points = max(20, int(n_available * 0.7))
        logger.info(
            "Capped min_train_points=%d (data: %d points)",
            min_train_points, n_available,
        )

    exclude_are = (target_source or "").strip().upper() == "RKI_ARE"

    result = service._run_walk_forward_market_backtest(
        target_df=target_df,
        virus_typ=virus_typ,
        horizon_days=horizon_days,
        min_train_points=min_train_points,
        delay_rules=delay_rules,
        exclude_are=exclude_are,
        target_disease=target_meta.get("disease"),
    )
    if "error" in result:
        return result

    df_sim = pd.DataFrame([{
        "date": row["date"],
        "bio": row.get("predicted_qty", 0.0),
        "real_qty": row.get("real_qty", 0.0),
    } for row in result.get("chart_data", []) if not row.get("is_forecast")])
    lead_lag = service._augment_lead_lag_with_horizon(
        service._best_bio_lead_lag(df_sim),
        horizon_days=horizon_days,
    )
    relative_lag_days = int(lead_lag.get("relative_lag_days", 0))
    effective_lead_days = int(lead_lag.get("effective_lead_days", 0))
    lag_corr = float(lead_lag.get("lag_correlation", 0.0))
    baseline_delta = result.get("improvement_vs_baselines", {})
    delta_pers = baseline_delta.get("mae_vs_persistence_pct", 0.0)
    delta_seas = baseline_delta.get("mae_vs_seasonal_pct", 0.0)
    decision_records = result.get("decision_forecast_records") or result.get("forecast_records") or []
    decision_metrics = result.get("decision_metrics") or service._compute_decision_metrics(
        forecast_records=decision_records,
        threshold_pct=float(service.DECISION_EVENT_THRESHOLD_PCT),
        vintage_metrics=result.get("vintage_metrics"),
    )
    timing_metrics = result.get("timing_metrics") or service._compute_timing_metrics(
        forecast_records=decision_records,
        horizon_days=int(horizon_days),
    )
    quality_gate = result.get("quality_gate") or service._build_quality_gate(
        decision_metrics,
        timing_metrics,
        improvement_vs_baselines=result.get("improvement_vs_baselines"),
        interval_coverage=result.get("interval_coverage"),
        event_calibration=result.get("event_calibration"),
    )
    result["decision_metrics"] = decision_metrics
    result["timing_metrics"] = timing_metrics
    result["quality_gate"] = quality_gate

    lag_strength = (
        "stark" if abs(lag_corr) >= 0.5
        else "moderat" if abs(lag_corr) >= 0.25
        else "schwach"
    )

    if lag_corr <= 0:
        proof_text = (
            "Kein stabiler positiver Lead erkennbar. "
            f"Prognose-Korrelation am optimalen Lag: r={lag_corr} ({lag_strength})."
        )
    elif lead_lag.get("bio_leads_target_effective"):
        proof_text = (
            f"XGBoost-Prognose läuft dem Ist-Wert um ca. {effective_lead_days} Tage voraus "
            f"(Forecast-Horizont {horizon_days}T + Relativ-Lag {relative_lag_days}T). "
            f"Prognose-Korrelation am optimalen Lag: r={lag_corr} ({lag_strength})."
        )
    elif lead_lag.get("target_leads_bio_effective"):
        proof_text = (
            f"Ist-Wert läuft der XGBoost-Prognose um ca. {abs(effective_lead_days)} Tage voraus "
            f"(Forecast-Horizont {horizon_days}T + Relativ-Lag {relative_lag_days}T). "
            f"Prognose-Korrelation am optimalen Lag: r={lag_corr} ({lag_strength})."
        )
    else:
        proof_text = (
            "Prognose und Ist-Wert sind effektiv gleichzeitig (0T Lead). "
            f"Prognose-Korrelation am optimalen Lag: r={lag_corr} ({lag_strength})."
        )

    result["mode"] = "MARKET_CHECK"
    result["virus_typ"] = virus_typ
    try:
        planning = service._build_planning_curve(
            target_df=target_df,
            virus_typ=virus_typ,
            days_back=days_back,
        )
        result["planning_curve"] = planning
    except Exception as exc:
        logger.warning("Planungskurve fehlgeschlagen: %s", exc)
        result["planning_curve"] = {"lead_days": 0, "correlation": 0, "curve": []}

    result["target_source"] = target_meta.get("target_source")
    result["target_key"] = target_meta.get("target_key", target_source)
    result["target_label"] = target_meta.get("target_label")
    result["target_meta"] = target_meta
    result["lead_lag"] = lead_lag
    result["vintage_mode"] = "STRICT_ASOF" if service.strict_vintage_mode else "EVENT_TIME_ONLY"
    result["cutoff_policy"] = {
        "strict_vintage_mode": bool(service.strict_vintage_mode),
        "fallback": "event_time<=cutoff when available_time is NULL",
    }

    def _safe_metric(value: object, default: float = 0.0) -> float:
        try:
            return float(value) if value is not None else float(default)
        except (TypeError, ValueError):
            return float(default)

    timing_best_corr = _safe_metric(timing_metrics.get("corr_at_best_lag"))
    decision_hit_rate = _safe_metric(decision_metrics.get("hit_rate_pct"))
    decision_false_alarm_rate = _safe_metric(decision_metrics.get("false_alarm_rate_pct"))
    interval_80_coverage = _safe_metric((result.get("interval_coverage") or {}).get("coverage_80_pct"))
    event_brier_score = _safe_metric((result.get("event_calibration") or {}).get("brier_score"))
    result["proof_text"] = (
        f"{proof_text} "
        f"Walk-forward Backtest: MAE vs. Persistence {delta_pers:+.2f}%, "
        f"vs. Seasonal-Naive {delta_seas:+.2f}% (historisch; zukuenftige Performance kann abweichen). "
        f"Timing: best_lag={timing_metrics.get('best_lag_days', 0)} Tage, "
        f"corr@best={timing_best_corr}. "
        f"Decision-Layer: TTD median {decision_metrics.get('median_ttd_days', 0)} Tage, "
        f"Hit-Rate {decision_hit_rate:.1f}%, "
        f"False-Alarms {decision_false_alarm_rate:.1f}%, "
        f"Interval 80% {interval_80_coverage:.1f}%, "
        f"Brier {event_brier_score:.3f}, "
        f"Readiness {'GO' if quality_gate.get('overall_passed') else 'WATCH'}."
    )
    result["llm_insight"] = (
        f"{result['proof_text']} "
        f"Walk-forward Modellguete: R²={result['metrics']['r2_score']}, "
        f"Korrelationsstärke={result['metrics']['correlation_pct']}%, "
        f"sMAPE={result['metrics'].get('smape', 0)}. "
        "Hinweis: Alle Metriken basieren auf historischen Mustern."
    )

    persisted_run_id = service._persist_backtest_result(
        mode="MARKET_CHECK",
        virus_typ=virus_typ,
        target_source=result["target_source"],
        target_key=result["target_key"],
        target_label=result["target_label"],
        result=result,
        parameters={
            "days_back": days_back,
            "horizon_days": horizon_days,
            "min_train_points": min_train_points,
            "strict_vintage_mode": bool(service.strict_vintage_mode),
            "delay_rules": delay_rules or {},
        },
    )
    if persisted_run_id:
        result["run_id"] = persisted_run_id

    return result


def run_customer_simulation(
    service,
    *,
    customer_df: pd.DataFrame,
    virus_typ: str = "Influenza A",
    horizon_days: int = 7,
    min_train_points: int = 20,
    strict_vintage_mode: bool = True,
) -> dict:
    """Mode B: Realitäts-Check mit Kundendaten."""
    service.strict_vintage_mode = bool(strict_vintage_mode)
    df = customer_df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    if "datum" not in df.columns or "menge" not in df.columns:
        return {
            "error": "Fehlende Pflichtspalten. Erwartet: datum, menge",
            "found_columns": list(df.columns),
        }

    if "region" not in df.columns:
        df["region"] = "Gesamt"

    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
    df["menge"] = pd.to_numeric(df["menge"], errors="coerce")
    df["region"] = df["region"].astype(str).fillna("Gesamt")
    df = df.dropna(subset=["datum", "menge"]).sort_values(["region", "datum"])

    if len(df) < 8:
        return {
            "error": f"Zu wenig Datenpunkte ({len(df)}). Mindestens 8 erforderlich.",
        }

    region_results: dict[str, dict] = {}
    combined_chart: list[dict] = []
    combined_historical: list[dict] = []
    combined_forecast_records: list[dict] = []
    combined_decision_forecast_records: list[dict] = []

    for region_name, region_df in df.groupby("region"):
        target_df = region_df[["datum", "menge"]].copy()
        target_df["available_time"] = target_df["datum"]
        if len(target_df) < max(8, min_train_points):
            continue

        region_result = service._run_walk_forward_market_backtest(
            target_df=target_df,
            virus_typ=virus_typ,
            horizon_days=horizon_days,
            min_train_points=min_train_points,
            delay_rules=None,
        )
        if "error" in region_result:
            continue

        sim_df = pd.DataFrame([{
            "date": row["date"],
            "bio": row.get("bio", 0.0),
            "real_qty": row.get("real_qty", 0.0),
        } for row in region_result.get("chart_data", []) if not row.get("is_forecast")])
        region_lead_lag = service._augment_lead_lag_with_horizon(
            service._best_bio_lead_lag(sim_df),
            horizon_days=horizon_days,
        )
        region_result["lead_lag"] = region_lead_lag

        for row in region_result.get("chart_data", []):
            row_copy = dict(row)
            row_copy["region"] = region_name
            combined_chart.append(row_copy)
            if not row_copy.get("is_forecast"):
                combined_historical.append(row_copy)

        for row in region_result.get("forecast_records", []):
            rec_copy = dict(row)
            rec_copy["region"] = region_name
            combined_forecast_records.append(rec_copy)
        for row in region_result.get("decision_forecast_records", []) or []:
            rec_copy = dict(row)
            rec_copy["region"] = region_name
            combined_decision_forecast_records.append(rec_copy)

        region_results[region_name] = {
            "metrics": region_result.get("metrics", {}),
            "lead_lag": region_lead_lag,
            "chart_points": len(region_result.get("chart_data", [])),
        }

    if not combined_chart or not combined_historical:
        return {
            "error": "Keine validen Backtest-Folds aus Kundendaten erzeugt. Bitte mehr Historie hochladen.",
        }

    combined_df = pd.DataFrame(combined_chart).sort_values("date").reset_index(drop=True)
    metrics_df = pd.DataFrame(combined_historical).sort_values("date").reset_index(drop=True)
    forecast_df = pd.DataFrame(combined_forecast_records).copy()
    if forecast_df.empty:
        return {
            "error": "Keine Forecast-Records für OOS-Metriken verfügbar.",
        }

    y_true = pd.to_numeric(forecast_df["y_true"], errors="coerce").to_numpy(dtype=float)
    y_hat = pd.to_numeric(forecast_df["y_hat"], errors="coerce").to_numpy(dtype=float)

    if "baseline_persistence" in forecast_df.columns:
        y_persistence = pd.to_numeric(
            forecast_df["baseline_persistence"], errors="coerce",
        ).to_numpy(dtype=float)
    else:
        y_persistence = y_hat.copy()

    if "baseline_seasonal" in forecast_df.columns:
        y_seasonal = pd.to_numeric(
            forecast_df["baseline_seasonal"], errors="coerce",
        ).to_numpy(dtype=float)
    else:
        y_seasonal = y_hat.copy()

    model_metrics = service._compute_forecast_metrics(y_true, y_hat)
    persistence_metrics = service._compute_forecast_metrics(y_true, y_persistence)
    seasonal_metrics = service._compute_forecast_metrics(y_true, y_seasonal)

    model_mae = max(model_metrics["mae"], 1e-9)
    pers_mae = max(persistence_metrics["mae"], 1e-9)
    seas_mae = max(seasonal_metrics["mae"], 1e-9)

    if "bio" in metrics_df.columns:
        lag_input = metrics_df[["date", "bio", "real_qty"]].copy()
        lag_input["bio"] = pd.to_numeric(lag_input["bio"], errors="coerce").fillna(0.0)
        lag_input["real_qty"] = pd.to_numeric(lag_input["real_qty"], errors="coerce").fillna(0.0)
        lead_lag_base = service._best_bio_lead_lag(lag_input)
    else:
        lead_lag_base = {
            "best_lag_points": 0,
            "best_lag_days": 0,
            "lag_step_days": int(max(1, int(horizon_days) or 7)),
            "lag_correlation": 0.0,
            "bio_leads_target": False,
        }

    lead_lag_global = service._augment_lead_lag_with_horizon(
        lead_lag_base,
        horizon_days=horizon_days,
    )
    decision_records = combined_decision_forecast_records or combined_forecast_records
    vintage_metrics = service._compute_vintage_metrics(
        forecast_records=decision_records,
        configured_horizon_days=int(horizon_days),
    )
    decision_metrics = service._compute_decision_metrics(
        forecast_records=decision_records,
        threshold_pct=float(service.DECISION_EVENT_THRESHOLD_PCT),
        vintage_metrics=vintage_metrics,
    )
    interval_coverage = service._compute_interval_coverage_metrics(combined_historical)
    event_calibration = service._compute_event_calibration_metrics(
        decision_records,
        threshold_pct=float(service.DECISION_EVENT_THRESHOLD_PCT),
    )
    timing_metrics = service._compute_timing_metrics(
        forecast_records=decision_records,
        horizon_days=int(horizon_days),
    )
    quality_gate = service._build_quality_gate(
        decision_metrics,
        timing_metrics,
        improvement_vs_baselines={
            "mae_vs_persistence_pct": round((pers_mae - model_mae) / pers_mae * 100, 2),
            "mae_vs_seasonal_pct": round((seas_mae - model_mae) / seas_mae * 100, 2),
        },
        interval_coverage=interval_coverage,
        event_calibration=event_calibration,
    )
    proof_text = (
        f"Kundendaten-Check über {model_metrics['data_points']} Punkte: "
        f"R²={model_metrics['r2_score']}, Korrelationsstärke={model_metrics['correlation_pct']}%, "
        f"Lead/Lag (effektiv)={lead_lag_global['effective_lead_days']} Tage. "
        f"Forecast-Vintage medianer Vorlauf={vintage_metrics['median_lead_days']} Tage. "
        f"Timing best_lag={timing_metrics.get('best_lag_days', 0)} Tage. "
        f"Decision-Layer: TTD median {decision_metrics.get('median_ttd_days', 0)} Tage, "
        f"Hit-Rate {decision_metrics.get('hit_rate_pct', 0):.1f}%, "
        f"False-Alarms {decision_metrics.get('false_alarm_rate_pct', 0):.1f}%, "
        f"Interval 80% {interval_coverage.get('coverage_80_pct', 0.0):.1f}%, "
        f"Brier {float(event_calibration.get('brier_score') or 0.0):.3f}."
    )
    clean_chart_df = combined_df.replace([np.inf, -np.inf], np.nan).astype(object)
    clean_chart_df = clean_chart_df.where(pd.notna(clean_chart_df), None)
    chart_records = clean_chart_df.to_dict(orient="records")

    result = {
        "mode": "CUSTOMER_CHECK",
        "virus_typ": virus_typ,
        "target_source": "CUSTOMER_SALES",
        "target_key": "CUSTOMER_SALES",
        "target_label": "Kundenumsatz/Bestellmenge",
        "metrics": model_metrics,
        "baseline_metrics": {
            "persistence": persistence_metrics,
            "seasonal_naive": seasonal_metrics,
        },
        "improvement_vs_baselines": {
            "mae_vs_persistence_pct": round((pers_mae - model_mae) / pers_mae * 100, 2),
            "mae_vs_seasonal_pct": round((seas_mae - model_mae) / seas_mae * 100, 2),
        },
        "lead_lag": lead_lag_global,
        "regions": region_results,
        "chart_data": chart_records,
        "forecast_records": combined_forecast_records,
        "decision_forecast_records": decision_records,
        "vintage_metrics": vintage_metrics,
        "decision_metrics": decision_metrics,
        "interval_coverage": interval_coverage,
        "event_calibration": event_calibration,
        "timing_metrics": timing_metrics,
        "quality_gate": quality_gate,
        "proof_text": proof_text,
        "llm_insight": (
            f"{proof_text} Gegenüber Persistence beträgt die MAE-Veränderung "
            f"{((pers_mae - model_mae) / pers_mae * 100):+.2f}%, "
            f"gegenüber Seasonal-Naive {((seas_mae - model_mae) / seas_mae * 100):+.2f}%."
        ),
        "walk_forward": {
            "enabled": True,
            "folds": int(model_metrics["data_points"]),
            "horizon_days": int(horizon_days),
            "min_train_points": int(min_train_points),
            "strict_vintage_mode": bool(service.strict_vintage_mode),
        },
    }
    result = service._sanitize_for_json(result)

    persisted_run_id = service._persist_backtest_result(
        mode="CUSTOMER_CHECK",
        virus_typ=virus_typ,
        target_source="CUSTOMER_SALES",
        target_key="CUSTOMER_SALES",
        target_label="Kundenumsatz/Bestellmenge",
        result=result,
        parameters={
            "horizon_days": horizon_days,
            "min_train_points": min_train_points,
            "strict_vintage_mode": bool(service.strict_vintage_mode),
            "regions_in_input": sorted(df["region"].unique().tolist()),
        },
    )
    if persisted_run_id:
        result["run_id"] = persisted_run_id

    return result


def run_calibration(
    service,
    *,
    customer_df: pd.DataFrame,
    virus_typ: str = "Influenza A",
    horizon_days: int = 7,
    min_train_points: int = 20,
    strict_vintage_mode: bool = True,
) -> dict:
    """Out-of-sample Kalibrierung via Walk-forward Backtest."""
    logger.info(
        "Starte OOS-Kalibrierung: rows=%s, virus=%s, horizon_days=%s, min_train_points=%s",
        len(customer_df),
        virus_typ,
        horizon_days,
        min_train_points,
    )
    service.strict_vintage_mode = bool(strict_vintage_mode)

    df = customer_df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "datum" not in df.columns or "menge" not in df.columns:
        return {
            "error": "Fehlende Pflichtspalten. Erwartet: datum, menge",
            "found_columns": list(df.columns),
        }

    df["datum"] = pd.to_datetime(df["datum"], errors="coerce")
    df["menge"] = pd.to_numeric(df["menge"], errors="coerce")
    df = df.dropna(subset=["datum", "menge"]).sort_values("datum").reset_index(drop=True)

    if len(df) < 8:
        return {
            "error": (
                f"Zu wenig Datenpunkte für OOS-Kalibrierung ({len(df)}). "
                "Mindestens 8 erforderlich."
            )
        }

    target_df = df[["datum", "menge"]].copy()
    target_df["available_time"] = target_df["datum"]

    step_days = service._estimate_step_days(
        pd.DataFrame({"date": target_df["datum"].dt.strftime("%Y-%m-%d")})
    )
    primary_horizon = max(1, int(horizon_days))
    primary_min_train = max(5, min(int(min_train_points), max(5, len(target_df) - 1)))

    candidate_cfgs: list[tuple[int, int]] = [
        (primary_horizon, primary_min_train),
        (step_days, primary_min_train),
        (step_days, max(5, min(primary_min_train, len(target_df) // 2))),
        (step_days, 5),
    ]

    seen: set[tuple[int, int]] = set()
    unique_cfgs: list[tuple[int, int]] = []
    for cfg in candidate_cfgs:
        if cfg in seen:
            continue
        seen.add(cfg)
        unique_cfgs.append(cfg)

    result: dict | None = None
    used_horizon = primary_horizon
    used_min_train = primary_min_train
    last_error: str | None = None

    for cfg_horizon, cfg_min_train in unique_cfgs:
        candidate = service._run_walk_forward_market_backtest(
            target_df=target_df,
            virus_typ=virus_typ,
            horizon_days=cfg_horizon,
            min_train_points=cfg_min_train,
            delay_rules=None,
        )
        if "error" in candidate:
            last_error = str(candidate.get("error"))
            continue
        result = candidate
        used_horizon = cfg_horizon
        used_min_train = cfg_min_train
        break

    if not result:
        return {
            "error": (
                "Walk-forward OOS-Kalibrierung konnte keine validen Folds erzeugen. "
                f"Letzter Fehler: {last_error or 'unbekannt'}"
            ),
            "attempted_configs": [
                {"horizon_days": h, "min_train_points": m}
                for h, m in unique_cfgs
            ],
        }

    df_sim = pd.DataFrame([{
        "date": row["date"],
        "bio": row.get("bio", 0.0),
        "real_qty": row.get("real_qty", 0.0),
    } for row in result.get("chart_data", []) if not row.get("is_forecast")])
    lead_lag = service._augment_lead_lag_with_horizon(
        service._best_bio_lead_lag(df_sim),
        horizon_days=used_horizon,
    )

    metrics = result.get("metrics", {})
    optimized_weights = result.get("optimized_weights", dict(service.DEFAULT_WEIGHTS))
    correlation_signed = float(metrics.get("correlation", 0.0) or 0.0)
    llm_insight = service._generate_llm_insight(
        weights=optimized_weights,
        r2=float(metrics.get("r2_score", 0.0) or 0.0),
        correlation=correlation_signed,
        mae=float(metrics.get("mae", 0.0) or 0.0),
        n_samples=int(metrics.get("data_points", 0) or 0),
        virus_typ=virus_typ,
    )

    proof_text = (
        f"OOS Walk-forward über {metrics.get('data_points', 0)} Folds "
        f"(Horizont {used_horizon}T, min_train_points={used_min_train}). "
        f"R²={metrics.get('r2_score')}, |Korrelation|={metrics.get('correlation_pct')}%, "
        f"sMAPE={metrics.get('smape')}, Lead/Lag (effektiv)="
        f"{lead_lag.get('effective_lead_days', 0)} Tage."
    )

    result["mode"] = "CALIBRATION_OOS"
    result["proof_text"] = proof_text
    result["llm_insight"] = llm_insight
    result["lead_lag"] = lead_lag
    result["walk_forward"] = {
        **(result.get("walk_forward") or {}),
        "enabled": True,
        "horizon_days": int(used_horizon),
        "min_train_points": int(used_min_train),
        "strict_vintage_mode": bool(service.strict_vintage_mode),
        "calibration_mode": "WALK_FORWARD_OOS",
    }

    logger.info(
        "OOS-Kalibrierung abgeschlossen: R²=%s, corr=%s, folds=%s, horizon=%s, min_train=%s, weights=%s",
        result.get("metrics", {}).get("r2_score"),
        result.get("metrics", {}).get("correlation"),
        result.get("walk_forward", {}).get("folds"),
        used_horizon,
        used_min_train,
        result.get("optimized_weights"),
    )
    return result
