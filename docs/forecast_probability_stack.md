# Forecast Probability Stack

## Forecast-Hinweis zum Legacy/Simple-Pfad

Der einfache Forecast-Pfad wurde im Probability-Stack sauberer gemacht.

### Früher

Die `event_probability` wurde aus einer Heuristik nachgelagert über eine Sigmoid-Funktion aus Punktforecast, Intervall und Baseline angenähert.

### Jetzt

Der einfache beziehungsweise nationale Fallback-Pfad behauptet **keine** echte `event_probability` mehr, wenn dafuer kein gelerntes und kalibriertes Modell vorliegt.

Stattdessen gilt:
- `event_probability` nur fuer den gelernten und kalibrierten Pfad
- `event_signal_score` fuer den heuristischen Fallback-Pfad

Nur der kalibrierte Pfad kommt aus einem gelernten `Exceedance-Modell`, das auf dem horizon-spezifischen `event_target` trainiert wird und nur issue-date-saubere Out-of-Fold-Vorhersagen fuer Backtest und Kalibrierung nutzt.

### Kalibrierung

Bevorzugt wird `isotonic`, bei kleineren Kalibrierungs-Samples `Platt/logistic`, sonst **kein Umetikettieren zur Wahrscheinlichkeit**, sondern ein klar gekennzeichneter Signal-Fallback.

### Feld-Semantik

`confidence` wird im bereinigten Entscheidungspfad nicht mehr als eigenstaendiger Prognosebegriff verkauft.  
Stattdessen werden `reliability_score` und `reliability_label` als Signal- und Backtest-Metadaten ausgewiesen.

Zusaetzlich gibt es additive Metadaten wie `backtest_quality_score`, `probability_source`, `signal_source`, `calibration_mode`, `uncertainty_source` und `fallback_reason`.

### Was bewusst getrennt bleibt

Epidemiologischer Forecast, Business-/Evidence-Gates, Ranking-Signal und Entscheidungs-Priorität bleiben getrennte Ebenen.
