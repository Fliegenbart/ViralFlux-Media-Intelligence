"""Explanation and weight-normalization helpers for BacktestService."""

from __future__ import annotations


def generate_llm_insight(
    service,
    *,
    weights: dict,
    r2: float,
    correlation: float,
    mae: float,
    n_samples: int,
    virus_typ: str,
    logger_obj,
) -> str:
    """LLM-Erklärung der Kalibrierungsergebnisse via lokalem vLLM."""
    weights_canonical = service._canonicalize_factor_weights(weights)
    dominant = max(weights_canonical, key=weights_canonical.get)
    weakest = min(weights_canonical, key=weights_canonical.get)

    factor_names = {
        "bio": "Biologische Daten (RKI-Abwasser + Laborpositivrate)",
        "market": "Marktdaten (Lieferengpässe + Bestelltrends)",
        "psycho": "Suchverhalten (Google Trends)",
        "context": "Kontextfaktoren (Wetter + Schulferien)",
    }

    prompt = f"""Du bist ein Senior Data Scientist bei ViralFlux Media Intelligence.
Du hast eine Regressionsanalyse der historischen Bestellungen eines Labors durchgeführt.

Harte Fakten:
- Analysierter Erreger: {virus_typ}
- Anzahl analysierter Datenpunkte: {n_samples}
- Modell-Qualität (R²): {r2:.2f} (1.0 = perfekt, 0.0 = kein Zusammenhang)
- Korrelation zwischen Vorhersage und Realität: {correlation:.1%}
- Durchschnittliche Abweichung (MAE): {mae:.0f} Einheiten

Ermittelte Einflussfaktoren auf die Bestellungen dieses Labors:
- {factor_names['bio']}: {weights_canonical['bio']*100:.0f}% Wichtigkeit
- {factor_names['market']}: {weights_canonical['market']*100:.0f}% Wichtigkeit
- {factor_names['psycho']}: {weights_canonical['psycho']*100:.0f}% Wichtigkeit
- {factor_names['context']}: {weights_canonical['context']*100:.0f}% Wichtigkeit

Stärkster Faktor: {factor_names[dominant]}
Schwächster Faktor: {factor_names[weakest]}

Schreibe eine professionelle Zusammenfassung (3-4 Sätze, auf Deutsch) für den Laborleiter.
Erkläre, worauf seine Bestellungen am stärksten reagiert haben und was weniger relevant war.
Schlage vor, das Modell mit diesen neuen Gewichten zu kalibrieren.
Verwende einen sachlichen, vertrauenswürdigen Ton."""

    try:
        from app.services.llm.vllm_service import generate_text_sync

        messages = [
            {"role": "system", "content": "Du bist ein hilfreicher Assistent."},
            {"role": "user", "content": prompt},
        ]
        return generate_text_sync(messages=messages, temperature=0.2)
    except Exception as exc:
        logger_obj.warning(f"LLM Insight fehlgeschlagen: {exc}")
        return (
            f"Die Analyse von {n_samples} Datenpunkten zeigt eine "
            f"{abs(correlation)*100:.0f}%ige Korrelation zwischen ViralFlux-Signalen "
            f"und Ihren tatsächlichen Bestellungen. Der stärkste Einflussfaktor "
            f"ist \"{factor_names[dominant]}\" ({weights_canonical[dominant]*100:.0f}%). "
            f"Wir empfehlen, das Modell mit diesen optimierten Gewichten zu kalibrieren."
        )


def map_feature_to_factor(feature_name: str) -> str:
    """Mappt beliebige Feature-Namen auf die vier Business-Faktoren."""
    key = str(feature_name or "").strip().lower()
    if not key:
        return "market"

    if (
        key.startswith("bio")
        or key.startswith("ww_")
        or "positivity" in key
        or key.startswith("xdisease")
        or key.startswith("survstat_xdisease")
    ):
        return "bio"

    if key.startswith("psycho") or "trend" in key:
        return "psycho"

    if (
        key.startswith("context")
        or key.startswith("weather")
        or key.startswith("school")
        or key.startswith("week_")
        or key.startswith("seasonal")
    ):
        return "context"

    if (
        key.startswith("market")
        or key.startswith("are_")
        or key.startswith("target_")
        or key.startswith("grippeweb")
        or key.startswith("notaufnahme")
    ):
        return "market"

    return "market"


def canonicalize_factor_weights(
    service,
    weights,
    *,
    np_module,
    map_feature_to_factor_fn,
) -> dict[str, float]:
    """Normiert Gewichte auf bio/market/psycho/context für UI/LLM-Kompatibilität."""
    grouped = {key: 0.0 for key in service.DEFAULT_WEIGHTS.keys()}
    if not isinstance(weights, dict) or not weights:
        return dict(service.DEFAULT_WEIGHTS)

    for raw_key, raw_value in weights.items():
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if not np_module.isfinite(value):
            continue
        value = abs(value)
        factor = raw_key if raw_key in grouped else map_feature_to_factor_fn(raw_key)
        grouped[factor] += value

    total = float(sum(grouped.values()))
    if total <= 0:
        return dict(service.DEFAULT_WEIGHTS)

    return {
        key: round(grouped[key] / total, 3)
        for key in grouped.keys()
    }
