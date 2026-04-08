# Ops And Pilot Ticket Set

Basis für dieses Ticket-Set:
- [live_readiness_blockers_current.md](/Users/davidwegener/Desktop/viralflux/docs/live_readiness_blockers_current.md)
- [pilot_runbook_peix_gelo.md](/Users/davidwegener/Desktop/viralflux/docs/pilot_runbook_peix_gelo.md)
- [rsv_h7_live_evaluation_runbook.md](/Users/davidwegener/Desktop/viralflux/docs/rsv_h7_live_evaluation_runbook.md)
- [outcome_data_contract.md](/Users/davidwegener/Desktop/viralflux/docs/outcome_data_contract.md)

Stand: 2026-03-18

## Executive Cut

Es gibt jetzt zwei Ebenen, und genau daran orientiert sich dieses Ticket-Set:

- **Forecast-First-Pilot**
  kann für `GELO / RSV A / h7` glaubwürdig laufen, wenn der scoped Forecast-Pfad grün bleibt
- **Commercial GO**
  bleibt weiterhin blockiert, solange GELO-Outcome-Daten und Aktivierungs-/Holdout-Evidenz fehlen

Die P1-Tickets sind deshalb **keine Forecast-First-Blocker**, sondern **Commercial-GO-Blocker**.

Die P2-Tickets bleiben operative Warnungen.

## P1 - Commercial GO Blockers

### Ticket VF-P1-01

- ticket id: `VF-P1-01`
- title: `GELO outcome history and recurring ingest go-live`
- category: `pilot blocker`
- priority: `P1`
- suggested owner role: `data partner` with `backend` support
- why it matters:
  Der Forecast-First-Pilot kann bereits gezeigt werden. Was weiterhin fehlt, ist die echte GELO-Outcome-Basis für einen späteren Commercial GO.
- exact root cause:
  `PilotReadoutService._missing_requirements()` und `BusinessValidationService.evaluate()` sehen derzeit effektiv keinen belastbaren GELO-Truth-Layer:
  - `coverage_weeks = 0` oder zu wenig
  - keine stabile Spend-Grundlage
  - keine Sales / Orders / Revenue-Metriken
  Dadurch bleibt `commercial_validation_status = NO_GO/WATCH`.
- smallest corrective action:
  GELO an `POST /api/v1/media/outcomes/ingest` anschliessen und den ersten validen Backfill plus wiederkehrende Wochenbatches senden.
- dependencies:
  - produktiver M2M-Ingest ist bereits live
  - GELO braucht den offiziellen JSON-Contract aus [outcome_data_contract.md](/Users/davidwegener/Desktop/viralflux/docs/outcome_data_contract.md)
- acceptance criteria:
  - mindestens ein erfolgreicher GELO-Batch mit `imported > 0`
  - Audit-/Import-Trail zeigt den Batch sauber
  - `commercial_validation_status` springt für den engen Scope mindestens von `NO_GO` auf `WATCH`
  - `coverage_weeks > 0`

### Ticket VF-P1-02

- ticket id: `VF-P1-02`
- title: `GELO activation-cycle, holdout, and lift instrumentation contract`
- category: `pilot blocker`
- priority: `P1`
- suggested owner role: `product` with `data partner` and `backend` support
- why it matters:
  Ein erster Datenbatch reicht nicht für Commercial GO. Die Business-Validierung braucht Aktivierungszyklen, Holdout-Struktur und Lift-Evidenz.
- exact root cause:
  `BusinessValidationService.evaluate()` verlangt für `validated_for_budget_activation = true`:
  - `coverage_weeks >= 26`
  - `activation_cycles >= 2`
  - `holdout_groups >= 2`
  - `lift_metrics_available = true`
- smallest corrective action:
  GELO-Export so festziehen, dass jede relevante Aktivierung explizit `campaign_id` oder `activation_cycle`, `holdout_group` und Lift-bezogene Felder mitfuehrt.
- dependencies:
  - `VF-P1-01`
  - PEIX / GELO müssen die Zielmetrik für den Commercial Layer gemeinsam definieren
- acceptance criteria:
  - Datencontract nennt Aktivierungs-, Holdout- und Lift-Felder explizit
  - mindestens zwei Aktivierungszyklen werden in ViralFlux sichtbar
  - mindestens zwei Holdout-Gruppen sind sichtbar
  - `budget_release_status = GO` ist prinzipiell erreichbar

## P2 - Non-Blocking Operational Warnings

### Ticket VF-P2-01

- ticket id: `VF-P2-01`
- title: `Restore regional source freshness inside readiness window`
- category: `ops warning`
- priority: `P2`
- suggested owner role: `ops` with `data engineering` support
- why it matters:
  Der enge Forecast-First-Pilot ist fachlich nutzbar, aber `regional_operational` bleibt wegen Source-Freshness degradiert. Das drueckt Vertrauen, obwohl es aktuell kein harter Forecast-First-Blocker ist.
- exact root cause:
  Upstream-Quellen sind für den aktiven Scope nicht frisch genug, deshalb faellt `source_freshness_status` auf `warning`.
- smallest corrective action:
  Quell-Update oder Ingest-Job rerunnen, bis `latest_available_as_of` wieder im frischen Fenster liegt.
- dependencies:
  - Zugriff auf den Live-Ingest / Scheduler
- acceptance criteria:
  - `RSV A / h7` zeigt im regionalen Readiness-Row `source_freshness_status = ok`

### Ticket VF-P2-02

- ticket id: `VF-P2-02`
- title: `Refresh national forecast monitoring artifacts and clear stale monitoring alerts`
- category: `ops warning`
- priority: `P2`
- suggested owner role: `ml`
- why it matters:
  `forecast_monitoring` bleibt warning-lastig. Das blockiert den engen PEIX/GELO-Forecast-Pilot nicht direkt, lässt die Plattform aber schlechter aussehen als der aktive Scope selbst ist.
- exact root cause:
  Monitoring-/Backtest-Artefakte für den nationalen Strang sind stale oder unterbeprobt.
- smallest corrective action:
  Monitoring- und Backtest-Jobs neu laufen lassen und stale Artefakte ersetzen.
- dependencies:
  - idealerweise `VF-P2-01`
- acceptance criteria:
  - `/api/v1/forecast/monitoring` meldet keine rein stale-bedingten Warnungen mehr für den Live-Bestand

## P3 - Hygiene / Lower-Leverage Improvements

### Ticket VF-P3-01

- ticket id: `VF-P3-01`
- title: `Align operator runbooks with forecast-first vs commercial-go semantics`
- category: `hygiene`
- priority: `P3`
- suggested owner role: `product` with `ops` support
- why it matters:
  Ohne saubere Sprache wird aus einem Forecast-First-GO schnell wieder ein falsch verstandenes `WATCH`.
- exact root cause:
  Aeltere Doks setzen `GO` implizit mit Commercial-Evidence gleich.
- smallest corrective action:
  Runbooks und Founder-/Partner-Memos auf die neue Zweistufigkeit angleichen:
  - Forecast-First GO
  - Commercial GO
- dependencies:
  - aktuelle Live- und Pilot-Doks
- acceptance criteria:
  - keine aktive Pilot-Doku behauptet mehr, dass fehlende GELO-Daten den Forecast-First-Pilot komplett blockieren

## Recommended Execution Order

1. **Forecast-First-Pilot direkt nutzen**
   Kein Ticket, sondern die operative Konsequenz. Der enge Scope ist dafür da, jetzt gezeigt zu werden.

2. `VF-P1-01`
   Der Commercial Layer braucht echte Outcome-Daten als erste Stufe.

3. `VF-P1-02`
   Danach Holdout-/Lift-Fähigkeit herstellen.

4. `VF-P2-01`
   Source-Freshness für den aktiven Scope wieder grüner machen.

5. `VF-P2-02`
   Nationales Monitoring aufraeumen.

6. `VF-P3-01`
   Alle operativen Texte auf dieselbe Wahrheit bringen.

## What Would Change Pilot Status From WATCH/NO_GO To Credible GO?

### Credible Forecast-First GO

Der enge Pilot ist ein glaubwürdiger GO, wenn:

1. `RSV A / h7` forecast-seitig grün bleibt
2. `pilot-readout` für den engen Scope `scope_readiness = GO` liefert
3. die Budgetsicht als `scenario_split` ausgewiesen bleibt
4. Commercial Validation sichtbar getrennt ist

### Credible Commercial GO

Die zweite Freigabestufe kommt erst, wenn:

1. GELO-Outcome-Daten produktiv fliessen
2. Aktivierungszyklen und Holdouts sichtbar sind
3. Lift-Evidenz verfügbar ist
4. `commercial_validation_status = GO`
5. `budget_release_status = GO`

Bis dahin ist die ehrliche Sprache:

- Forecast: GO
- Commercial Validation: WATCH oder NO_GO
