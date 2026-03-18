# Core Production Readiness

Stand: 2026-03-18

## Warum dieser Pfad existiert

`/health/ready` bleibt der breite Plattform-Readiness-Check.
Er bewertet:

- nationale Forecast-Monitoring-Sichten
- die komplette regionale Scope-Matrix
- auch nicht-pilotige, Shadow- oder bewusst unsupported Scopes

Das ist fuer Plattformtransparenz richtig, aber fuer die Frage

- "Ist unser aktueller Live-Kernbetrieb ehrlich gruen?"

zu breit.

Deshalb gibt es zusaetzlich:

- `GET /health/core-ready`

Dieser Pfad bewertet nur die explizit produktiven Core-Scopes.

## Aktuelle Kernlogik

Konfigurationsquelle:

- `CORE_PRODUCTION_SCOPES`

Default:

- `RSV A:h7`

Beispiel fuer mehrere Scopes:

- `RSV A:h7,Influenza A:h7,Influenza B:h7`

## Was `core-ready` bewertet

Ein Core-Scope gilt nur dann als `ok`, wenn alles hiervon gilt:

1. `model_availability = available`
2. `pilot_contract_supported = true`
3. `quality_gate.forecast_readiness = GO`
4. `forecast_recency_status = ok`
5. `source_freshness_status = ok`
6. `source_coverage_required_status = ok`
7. kein `artifact_transition_mode`

Wenn einer dieser Punkte nicht passt:

- `warning`, wenn der Scope fachlich sichtbar, aber noch nicht sauber genug ist
- `critical`, wenn der Scope als Core konfiguriert ist, aber gar nicht unterstuetzt oder nicht ladbar ist

## Wichtige Abgrenzung

`/health/core-ready` ist **keine weichere** Version von `/health/ready`.

Es ist ein **engerer und ehrlicherer** Check:

- `/health/ready` beantwortet: "Wie sieht das ganze Portfolio aus?"
- `/health/core-ready` beantwortet: "Ist der aktuell produktive Kernbetrieb sauber?"

Beide Pfade koennen gleichzeitig sinnvoll sein:

- `/health/ready = degraded`
- `/health/core-ready = healthy`

Das bedeutet:

- das Portfolio hat noch Warning-Zonen
- aber der produktive Kernscope ist grün

## Zielbild fuer PEIX / GELO

Fuer den aktuellen PEIX/GELO-Kern bedeutet gruen:

- `RSV A / h7` ist im Forecast-First-Betrieb produktionsfaehig
- nicht-pilotige und unsupported Scopes ziehen diese Kernampel nicht mehr mit nach unten

Commercial Validation bleibt weiterhin getrennt:

- GELO-Outcome-Daten und Lift-/Holdout-Evidenz gehoeren nicht in `core-ready`
- sie gehoeren weiter in den Commercial-/Pilot-Layer

## Quick Checks

Breite Plattformsicht:

```bash
curl -s https://fluxengine.labpulse.ai/health/ready
```

Produktiver Kern:

```bash
curl -s https://fluxengine.labpulse.ai/health/core-ready
```
