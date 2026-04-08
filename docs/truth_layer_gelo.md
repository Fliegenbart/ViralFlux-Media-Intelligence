# GELO Truth Layer

## Ziel

Der Truth-Layer erweitert die epidemiologische Entscheidungsschicht um optionale kommerzielle Validierung. Er ersetzt keine epidemiologische Ground Truth und schreibt auch keine Outcome-Daten in Forecast-Targets zurück.

Der Layer beantwortet für GELO-Scope-Fragen wie:

- Gibt es für Region und Produkt überhaupt belastbare Outcome-Daten?
- Wurde in vergleichbaren Aktivierungsfenstern historisch eine kommerzielle Reaktion beobachtet?
- Reicht die Evidenz schon für Budgetentscheidungen oder nur für Decision Support?
- Ist der Scope strukturell bereit für Holdout-/Kontrollgruppen-Designs?

## Implementierte Bausteine

- Persistentes generisches Fact-Table: `OutcomeObservation` in [backend/app/models/database.py](/Users/davidwegener/Desktop/viralflux/backend/app/models/database.py)
- Alembic-Migration: [backend/alembic/versions/d7e4c9a1b2f3_add_outcome_observations.py](/Users/davidwegener/Desktop/viralflux/backend/alembic/versions/d7e4c9a1b2f3_add_outcome_observations.py)
- Typed Contracts: [backend/app/services/media/truth_layer_contracts.py](/Users/davidwegener/Desktop/viralflux/backend/app/services/media/truth_layer_contracts.py)
- Service-Layer: [backend/app/services/media/truth_layer_service.py](/Users/davidwegener/Desktop/viralflux/backend/app/services/media/truth_layer_service.py)
- Tests: [backend/app/tests/test_truth_layer_service.py](/Users/davidwegener/Desktop/viralflux/backend/app/tests/test_truth_layer_service.py)

## Designprinzipien

- Optional: Ohne GELO-Daten bleibt der Forecast- und Decision-Stack lauffähig.
- Entkoppelt: Outcome-Observations liegen in einer separaten Tabelle und werden nicht als Forecast-Truth verwendet.
- Fallback-fähig: Falls `outcome_observations` leer ist, normalisiert der Service bestehende `MediaOutcomeRecord`-Rows nur lesend in das generische Format.
- Transparent: Die Bewertung ist regelbasiert und dokumentiert, nicht als ML modelliert.

## Kernobjekte

### 1. OutcomeObservation

Granulare Outcome-Beobachtung pro:

- `brand`
- `product`
- `region_code`
- `window_start` / `window_end`
- `metric_name`
- `source_label`

Optionale Zusatzfelder:

- `channel`
- `campaign_id`
- `holdout_group`
- `confidence_hint`
- `metadata`

### 2. TruthLayerService

Wichtige Methoden:

- `upsert_observations(...)`
- `assess(...)`

`assess(...)` liefert für Scope `(brand, region_code, product, time window)`:

- `outcome_readiness`
- `signal_outcome_agreement`
- `holdout_eligibility`
- `evidence_status`
- `commercial_gate`

## Bewertungslogik V1

### Outcome readiness

Heuristische Stufen:

- `missing`: keine Outcome-Daten
- `sparse`: zu kurze Historie oder kaum Spend-/Response-Windows
- `partial`: brauchbare Historie, aber noch keine volle Freigabereife
- `ready`: >= 26 Wochen und ausreichend Spend-/Response-Windows

Die Readiness basiert auf:

- Coverage-Wochen
- Spend-Windows
- Response-Windows
- Metrik-Diversitaet

### Signal-outcome agreement

Der Layer nimmt optional `signal_context` an, z. B.:

```json
{
  "event_probability": 0.74,
  "decision_stage": "prepare",
  "confidence": 0.68
}
```

Dann wird geprüft:

1. Ist ein epidemiologisches Signal praesent?
2. Gibt es historische Spend-Windows mit beobachteter kommerzieller Reaktion?
3. Wie stark ist diese Reaktion?
4. Wie hoch ist die Outcome-Konfidenz aus Coverage und Struktur?

Ergebnisstufen:

- `no_signal`
- `no_outcome_support`
- `weak`
- `moderate`
- `strong`

### Evidence status

V1-Klassen:

- `no_truth`
- `explorative`
- `observational`
- `truth_backed`
- `holdout_ready`
- `commercially_validated`

`commercially_validated` wird nur gesetzt, wenn:

- der Scope holdout-ready ist
- explizite Lift-Signale in den Outcome-Metadaten vorliegen

## Was der Layer bewusst nicht tut

- kein MMM
- keine Kausal-Attribution
- keine Vermischung von Outcome und epidemiologischer Forecast-Truth
- kein Training von Budgetmodellen

## Erweiterungspfade

- direkte Connectoren für GELO Sales / Orders / Search / Kampagnenreaktionen
- Scope-spezifische Holdout-Policies
- getrennte Evidence-Snapshots pro Virus/Region/Produkt
- spätere Anbindung an eine Media Allocation Engine
