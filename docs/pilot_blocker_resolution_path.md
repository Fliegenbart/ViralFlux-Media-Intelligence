# Pilot Blocker Resolution Path

Basis:
- [ops_and_pilot_ticket_set.md](/Users/davidwegener/Desktop/viralflux/docs/ops_and_pilot_ticket_set.md)
- [live_readiness_blockers_current.md](/Users/davidwegener/Desktop/viralflux/docs/live_readiness_blockers_current.md)
- [pilot_runbook_peix_gelo.md](/Users/davidwegener/Desktop/viralflux/docs/pilot_runbook_peix_gelo.md)
- [pilot_reporting_and_roi.md](/Users/davidwegener/Desktop/viralflux/docs/pilot_reporting_and_roi.md)
- [outcome_data_contract.md](/Users/davidwegener/Desktop/viralflux/docs/outcome_data_contract.md)

Stand: 2026-03-18

## Executive Answer

Ja: Es gab einen **kurzen, glaubwürdigen GO-Pfad ohne GELO-Daten**.

Dieser GO-Pfad ist aber bewusst **eng**:

- nur `GELO`
- nur `RSV A`
- nur `h7`
- nur als **Forecast-First-Pilot**
- nur für Priorisierung, Timing und Szenario-Splits

Es gab weiterhin **keinen kurzen GO-Pfad** für:

- validierte Commercial-Freigaben
- ROI-Claims
- outcome-belegte Budgetoptimierung

## Die 3 kleinsten Voraussetzungen für ein glaubwürdiges GO

### 1. Der enge Forecast-Scope muss grün bleiben

Ja/Nein-Logik:

- wenn `RSV A / h7` forecast-seitig kippt, gab es keinen ehrlichen Pilot-GO
- wenn `RSV A / h7` forecast-seitig `GO` blieb, konnte der Pilot gezeigt werden

Minimal nötig:

- `scope_readiness = GO` im scoped `pilot-readout`
- `forecast_readiness = GO`
- retained Live-Evaluation bleibt `GO`

### 2. Der Produktclaim muss eng bleiben

Ja/Nein-Logik:

- wenn PEIX bereits ROI- oder Sales-Optimierung behauptete, war der Pilot nicht ehrlich
- wenn PEIX Forecast, Regionen-Priorisierung und Szenario-Splits verkaufte, war der Claim sauber

Minimal nötig:

- Budgetdarstellung bleibt `scenario_split`
- `commercial_validation_status != GO` wird sichtbar benannt
- keine implizite Spend-Freigabe ohne GELO-Daten

### 3. Die Commercial-Luecke muss als Upgrade-Pfad, nicht als Defekt, gezeigt werden

Ja/Nein-Logik:

- wenn fehlende GELO-Daten wie ein Produktfehler wirkten, verlor der Pilot Glaubwürdigkeit
- wenn klar war, dass Forecast schon lief und GELO-Daten die zweite Stufe freischalten, blieb die Story stark

Minimal nötig:

- `/pilot` zeigte bereits Forecast Ready klar vor Commercial Validation
- GELO-Daten werden als nächste Ausbaustufe erklaert

## Minimal Path

Das ist der **kleinste** Weg zu einem glaubwürdigen Forecast-First-GO.

### Scope

Nur dieser Scope:

- `brand = gelo`
- `virus_typ = RSV A`
- `horizon_days = 7`
- nur der kanonische `pilot-readout`

### Reihenfolge

1. **Forecast-First-Semantik aktivieren**
   Das System muss klar trennen zwischen Forecast Ready und Commercial Validation.

2. **Scoped Pilot-Readout prüfen**
   Der enge Scope muss live liefern:
   - `scope_readiness = GO`
   - `forecast_readiness = GO`
   - `pilot_mode = forecast_first`
   - `budget_mode = scenario_split`

3. **Meeting- und Sales-Narrativ fixieren**
   PEIX darf zeigen:
   - Forecast
   - Regionen-Priorisierung
   - Szenario-Splits
   Nicht zeigen:
   - validierte ROI- oder Lift-Claims

### Minimal GO Definition

Ein glaubwürdiger Forecast-First-GO lag vor, wenn alle Punkte gleichzeitig galten:

- der enge Scope `GELO / RSV A / h7` ist forecast-seitig `GO`
- die Live-Evaluation bleibt retained und `GO`
- der Pilot-Readout zeigt die Budgetsicht als `scenario_split`
- Commercial Validation bleibt separat sichtbar
- keine Customer-Copy suggeriert bereits bewiesene Business-Wirkung

## Realistic Path

### Phase 1: Forecast-First GO

Das war der damalige nächste Zielzustand.

Was PEIX dann ehrlich sagen kann:

- "Wir sehen die virale Dynamik früh."
- "Wir priorisieren Regionen belastbar."
- "Wir können daraus bereits eine sinnvolle Budget-Szenarioverteilung ableiten."

Was PEIX noch nicht sagen darf:

- "Wir haben bereits den Sales-Uplift bewiesen."

### Phase 2: Commercial WATCH

Was passiert:

- GELO schickt erste echte Outcome-Daten
- `commercial_validation_status` springt von `NO_GO` auf `WATCH`

Was das bringt:

- der Pilot wird lernender
- Spend-, Sales- und Aktivierungsdaten können gespiegelt werden

### Phase 3: Commercial GO

Erst hier entstand die zweite Freigabestufe.

Nötig:

- Outcome-Historie
- Aktivierungszyklen
- Holdout-Gruppen
- Lift-Metriken
- weiterhin grünes `RSV A / h7`

## Intern vs Extern

### Extern: PEIX / GELO

- PEIX muss den Forecast-First-Claim sauber fuehren
- GELO muss für den Commercial Layer später Outcome-Daten liefern
- PEIX und GELO müssen sich später auf Lift-/Holdout-Definitionen einigen

### Intern: ViralFlux

- den scoped Forecast-Pfad stabil halten
- die Forecast-First-Semantik im damaligen `pilot-readout` und in `/pilot` sauber trennen
- Commercial Validation weiter sichtbar halten, aber nicht mehr als primaren Pilotblocker für Forecast-Demos behandeln

## Was parallel laufen kann

Kann parallel laufen:

- Forecast-First-Pilot live zeigen
- GELO-Ingest vorbereiten
- Aktivierungs-/Holdout-Contract definieren
- P2/P3-Warnungen bereinigen

Kann nicht logisch übersprungen werden:

- echte Commercial-GO-Freigabe ohne Outcome-Daten
- ROI-Claim ohne Aktivierungs- und Lift-Evidenz

## Smallest Pilot We Could Honestly Release

Der kleinste ehrlich freigebbare Pilot war:

- nur `GELO`
- nur `RSV A`
- nur `h7`
- nur `/pilot` als historische Surface
- nur Forecast, Priorisierung und Szenario-Splits

Das ist **genug**, um GELO den Produktkern zu zeigen und Mitwirkung für den Commercial Layer einzuladen.

## What Still Keeps Us At WATCH/NO_GO?

### Haelt den Forecast-First-Pilot auf `NO_GO`

- `RSV A / h7` verliert den retained GO-Pfad
- scoped `pilot-readout` kippt auf `scope_readiness != GO`
- Forecast-/Evaluation-/Promotion-Evidenz bricht weg

### Haelt nur den Commercial Layer auf `WATCH/NO_GO`

- keine GELO-Outcome-Daten
- keine Spend-Daten
- keine Sales/Orders/Revenue-Daten
- weniger als zwei Aktivierungszyklen
- keine Holdout-Gruppen
- keine Lift-Metriken

### Wichtig

Diese zweite Liste blockiert **nicht mehr** den Forecast-First-Pilot.
Sie blockiert nur den späteren Commercial GO.

## Strict Decision Rule

### Credible Forecast-First GO

Nur wenn:

- `scope_readiness = GO`
- `forecast_readiness = GO`
- Budget bleibt als `scenario_split` ausgewiesen
- Commercial Validation ist separat und ehrlich sichtbar

### Honest Commercial WATCH

Wenn:

- Forecast schon läuft
- GELO-Daten aber noch fehlen oder noch unvollstaendig sind

### Credible Commercial GO

Nur wenn:

- GELO truth connected
- business validation contract satisfied
- `budget_release_status = GO`
- `commercial_validation_status = GO`
- der enge Scope forecast-seitig weiter grün bleibt

## Bottom Line

Die Wahrheit war einfacher und nutzbarer:

- Ohne GELO-Daten gab es **keinen Commercial GO**.
- Ohne GELO-Daten gab es aber **sehr wohl einen ehrlichen Forecast-First GO**.
- Genau dieser enge Forecast-First-GO war der richtige Weg, um GELO das Tool zu zeigen und sie für den Outcome-Layer zu gewinnen.
