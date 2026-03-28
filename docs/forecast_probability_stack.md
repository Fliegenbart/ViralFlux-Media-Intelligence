# Forecast Probability Stack

## Forecast-Hinweis zum Legacy/Simple-Pfad

Der einfache Forecast-Pfad wurde im Probability-Stack sauberer gemacht.

### Früher

Die `event_probability` wurde aus einer Heuristik nachgelagert über eine Sigmoid-Funktion aus Punktforecast, Intervall und Baseline angenähert.

### Jetzt

Die `event_probability` kommt aus einem gelernten `Exceedance-Modell`, das auf dem horizon-spezifischen `event_target` trainiert wird und nur issue-date-saubere Out-of-Fold-Vorhersagen für Backtest und Kalibrierung nutzt.

### Kalibrierung

Bevorzugt wird `isotonic`, bei kleineren Kalibrierungs-Samples `Platt/logistic`, sonst rohe Modellwahrscheinlichkeit als klar gekennzeichneter Fallback.

### Feld-Semantik

`confidence` ist nicht mehr als Fehler-Proxy gedacht.  
Zusätzlich gibt es additive Metadaten wie `reliability_score`, `backtest_quality_score`, `probability_source`, `calibration_mode`, `uncertainty_source` und `fallback_reason`.

### Was bewusst getrennt bleibt

Epidemiologischer Forecast, Business-/Evidence-Gates, Ranking-Signal und Entscheidungs-Priorität bleiben getrennte Ebenen.
