# Forecast World-Class Plan

## Ziel

Der Forecast-Stack wird schrittweise von einem punktuellen Direktpfad zu einem probabilistischen, benchmark-getriebenen Champion/Challenger-System erweitert.

## Was jetzt umgesetzt wurde

- neues Benchmarking-Paket für WIS, Coverage, Pinball, Brier, ECE, PR-AUC und Utility
- Dateisystem-Registry für Champion/Challenger-Scopes pro Virus und Horizon
- gemeinsame Challenger-Bausteine für Quantile, Event-Modeling, Ensemble und Hierarchie
- additive Metadaten für gelernte Wahrscheinlichkeiten, Ensemble-Gewichte und Revisions-Policy
- erste Governance-Umstellung im Promotion-Pfad

## Was bewusst bestehen bleibt

- bestehende öffentliche Forecast-APIs
- alter Direktpfad als Fallback und Debug-Referenz
- regionale Produktionspipeline als erste Champion-Basis

## Nächste operative Schritte

1. reale Backtests gegen die Datenbank ausführen
2. Registry mit echten Benchmark-Ergebnissen befüllen
3. adaptive Revisions-Policy erst bei nachgewiesenem Vorteil live schalten
4. optionale TSFM-Challenger nur unter Feature-Flag testen
