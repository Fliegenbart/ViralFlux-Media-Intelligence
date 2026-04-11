# Commercial Truth Layer

## Ziel

Der Truth-Layer erweitert die epidemiologische Entscheidungsschicht um optionale kommerzielle Validierung. Er ersetzt keine epidemiologische Ground Truth und schreibt keine Outcome-Daten in Forecast-Targets zurueck.

Der Layer beantwortet Fragen wie:

- Gibt es fuer Region und Produkt belastbare Outcome-Daten?
- Wurde in vergleichbaren Aktivierungsfenstern historisch eine kommerzielle Reaktion beobachtet?
- Reicht die Evidenz schon fuer Budgetentscheidungen oder nur fuer Decision Support?
- Ist der Scope strukturell bereit fuer Holdout- oder Kontrollgruppen-Designs?

## Implementierte Bausteine

- Persistentes generisches Fact-Table: `OutcomeObservation`
- Alembic-Migration fuer Outcome-Observations
- Typed Contracts im Truth-Layer
- Service-Layer fuer Bewertung und Readiness
- Tests fuer den Truth-Layer-Service

## Designprinzipien

- Optional: Ohne Outcome-Daten bleibt der Forecast- und Decision-Stack lauffaehig.
- Entkoppelt: Outcome-Observations liegen in einer separaten Tabelle und werden nicht als Forecast-Truth verwendet.
- Fallback-faehig: Falls `outcome_observations` leer ist, normalisiert der Service bestehende Outcome-Rows nur lesend in das generische Format.
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

`assess(...)` liefert fuer Scope `(brand, region_code, product, time window)`:

- `outcome_readiness`
- `signal_outcome_agreement`
- `holdout_eligibility`
- `evidence_status`
- `commercial_gate`

## Bewertungslogik V1

### Outcome readiness

Heuristische Stufen:

- `missing`: keine Outcome-Daten
- `sparse`: zu kurze Historie oder kaum Spend- oder Response-Windows
- `partial`: brauchbare Historie, aber noch keine volle Freigabereife
- `ready`: mindestens 26 Wochen und ausreichend Spend- oder Response-Windows

### Signal-outcome agreement

Der Layer nimmt optional `signal_context` an, zum Beispiel:

```json
{
  "event_probability": 0.74,
  "decision_stage": "prepare",
  "confidence": 0.68
}
```

Dann wird geprueft:

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

## Was der Layer bewusst nicht tut

- kein MMM
- keine Kausal-Attribution
- keine Vermischung von Outcome und epidemiologischer Forecast-Truth
- kein Training von Budgetmodellen

## Erweiterungspfade

- direkte Connectoren fuer Sales, Orders, Search und Kampagnenreaktionen
- Scope-spezifische Holdout-Policies
- getrennte Evidence-Snapshots pro Virus, Region und Produkt
- spaetere Anbindung an eine Media Allocation Engine
