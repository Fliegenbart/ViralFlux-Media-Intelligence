"""Post-hoc Scale-Kalibrierung fuer die Forecast-Pipeline (2026-04-21).

Problem:
    Die persistierten Forecast-Punkte (``ml_forecasts.predicted_value``) liegen
    systematisch ~2-3x ueber den tatsaechlichen AMELAG-Abwasserwerten. Peak-
    Saison-MAPE liegt entsprechend bei 35-70 %. Das ist kein Rauschen — die
    Rangordnung der Regionen ist weiterhin brauchbar — sondern ein
    Skalen-Bias im Modell-Output.

Fix-Idee:
    Eine kleine lineare Transformation ``y_corrected = alpha + beta * y_raw``
    auf jeden T+h-Prediction-Punkt anwenden. Die Koeffizienten ``(alpha, beta)``
    werden aus den letzten N historischen Forecast-Actual-Paaren pro Virus
    gefittet (Peak-Saison bevorzugt, weil da das Signal echt da war).

Sicherheitsnetze:
    * ``min_samples``: unter 8 Paaren kein Fit — zurueck zur Identitaet
      (alpha=0, beta=1). Gilt als ``applied=False`` und faellt im Snapshot
      transparent auf "nicht kalibriert".
    * ``beta`` wird hart auf [``BETA_MIN``, ``BETA_MAX``] = [0.05, 5.0]
      geklampt. Ausreisser (die naechste Peak-Welle bringt hohe residuals
      bis sich der Kalibrator nachzieht) sollen den Forecast nicht
      wegskalieren.
    * ``alpha`` ist additiv, ebenfalls geklampt auf +/- 2 x actual_max aus
      dem Trainings-Sample (hartes Ceiling gegen Solver-Divergenzen).
    * Wenn der Fit mehr RMSE als die Identitaet produziert, fallen wir
      auf Identitaet zurueck (``applied=False``, ``fallback_reason="no_improvement"``).

Der Kalibrator wird **nicht** persistiert — er wird bei jeder Inference
frisch aus der DB gefittet. Das macht ihn selbstregulierend: sobald das
Modell besser wird (z.B. naechstes Retraining), faellt alpha->0 und
beta->1 automatisch zurueck.

Der Snapshot-Builder liest den aktuellen Kalibrator-Snapshot aus
``ml_forecasts.features_used.scale_calibration`` (geschrieben pro Run).
"""

from __future__ import annotations

from typing import Any


BETA_MIN = 0.05
BETA_MAX = 5.0
MIN_FIT_SAMPLES = 8
# How far alpha is allowed to drift from zero, as a multiple of the
# mean of the actuals used in the fit. Guards against solver divergence
# when a few big-residual pairs dominate the regression.
ALPHA_ABS_TO_ACTUAL_MEAN = 2.0


def _polyfit_linear(x: list[float], y: list[float]) -> tuple[float, float]:
    """Minimal least-squares linear regression (y = alpha + beta * x).

    We avoid ``numpy.polyfit`` to keep the helper cheap and pure-Python —
    the fit has at most ~30 points, scipy is overkill.
    """
    n = len(x)
    if n == 0:
        return 0.0, 1.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    if var_x <= 0:
        return 0.0, 1.0
    beta = cov_xy / var_x
    alpha = mean_y - beta * mean_x
    return alpha, beta


def _rmse(pred: list[float], actual: list[float]) -> float:
    if not pred:
        return 0.0
    n = len(pred)
    return (sum((pi - ai) ** 2 for pi, ai in zip(pred, actual)) / n) ** 0.5


def fit_scale_calibrator(
    pairs: list[tuple[float, float]],
    *,
    min_samples: int = MIN_FIT_SAMPLES,
    beta_min: float = BETA_MIN,
    beta_max: float = BETA_MAX,
) -> dict[str, Any]:
    """Fit a linear scale calibrator on (predicted, actual) pairs.

    Returns a dict:
        applied        True when a non-identity calibrator is in use.
        alpha          intercept of ``actual ≈ alpha + beta * predicted``.
        beta           slope, clamped to [beta_min, beta_max].
        samples        Number of pairs used.
        rmse_before    RMSE of raw predictions vs actuals (for transparency).
        rmse_after     RMSE after applying the fitted calibrator.
        fallback_reason  Populated when ``applied=False`` (insufficient data,
                       degenerate fit, no improvement, solver divergence).
    """
    n = len(pairs)
    identity = {
        "applied": False,
        "alpha": 0.0,
        "beta": 1.0,
        "samples": n,
        "rmse_before": None,
        "rmse_after": None,
        "fallback_reason": None,
    }
    if n == 0:
        identity["fallback_reason"] = "no_pairs"
        return identity
    if n < min_samples:
        identity["rmse_before"] = round(
            _rmse([p for p, _ in pairs], [a for _, a in pairs]), 3
        )
        identity["rmse_after"] = identity["rmse_before"]
        identity["fallback_reason"] = f"insufficient_samples_{n}_lt_{min_samples}"
        return identity

    preds = [float(p) for p, _ in pairs]
    acts = [float(a) for _, a in pairs]
    raw_rmse = _rmse(preds, acts)

    alpha_raw, beta_raw = _polyfit_linear(preds, acts)
    beta = max(beta_min, min(beta_max, beta_raw))

    act_mean = sum(acts) / n
    alpha_cap = ALPHA_ABS_TO_ACTUAL_MEAN * max(1.0, abs(act_mean))
    alpha = max(-alpha_cap, min(alpha_cap, alpha_raw))

    calibrated = [alpha + beta * p for p in preds]
    cal_rmse = _rmse(calibrated, acts)

    if cal_rmse >= raw_rmse:
        # Fit did not improve — fall back to identity. Honest: we would
        # rather keep a 2x-biased forecast with known structure than ship
        # an ad-hoc transform that makes things worse.
        identity["rmse_before"] = round(raw_rmse, 3)
        identity["rmse_after"] = round(raw_rmse, 3)
        identity["fallback_reason"] = "no_improvement"
        return identity

    clamped = (beta != beta_raw) or (alpha != alpha_raw)
    return {
        "applied": True,
        "alpha": round(alpha, 4),
        "beta": round(beta, 4),
        "samples": n,
        "rmse_before": round(raw_rmse, 3),
        "rmse_after": round(cal_rmse, 3),
        "fallback_reason": "clamped_coefficients" if clamped else None,
    }


def apply_scale_calibration(
    value: float, calibrator: dict[str, Any]
) -> float:
    """Apply ``alpha + beta * value``; clip at zero (counts can't go negative)."""
    if not calibrator or not calibrator.get("applied"):
        return float(value)
    alpha = float(calibrator.get("alpha") or 0.0)
    beta = float(calibrator.get("beta") or 1.0)
    return max(0.0, alpha + beta * float(value))
