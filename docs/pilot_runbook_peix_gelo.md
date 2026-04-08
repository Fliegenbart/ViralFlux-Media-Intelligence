# Pilot Runbook PEIX / GELO

Stand: 2026-03-18

## Zweck

Dieses Runbook beschreibt den **eng geschnittenen Forecast-First-Pilot** für PEIX / GELO.

Wichtig:

- `live erreichbar` ist nicht automatisch `commercially validated`
- der Pilot darf heute schon als **Forecast- und Priorisierungs-Tool** gezeigt werden
- eine **Budget- oder ROI-Freigabe** bleibt eine zweite Stufe und braucht GELO-Outcome-Daten

## Zwei Freigabestufen

### 1. Forecast-First GO

Forecast-First GO bedeutet:

- der Scope ist technisch und epidemiologisch tragfähig
- der Forecast ist für den Kunden sichtbar und erklaerbar
- Regionen können priorisiert werden
- Budget darf als **Szenario-Split** gezeigt werden
- Commercial Validation darf noch `WATCH` oder `NO_GO` sein

### 2. Commercial GO

Commercial GO bedeutet zusätzlich:

- GELO-Outcome-Daten sind angeschlossen
- Aktivierungszyklen und Holdout-Logik sind sichtbar
- Lift-/Outcome-Evidenz ist stark genug für eine validierte Budgetfreigabe

## Rollen

### ViralFlux Produkt / Ops

- prüft Live-, Ready- und Smoke-Status
- prüft den scoped `pilot-readout`
- trennt Forecast-Readiness von Commercial-Validation
- ist verantwortlich für Incident-, Rollback- und Freigabeentscheidungen

### PEIX

- nutzt den Forecast-First-Pilot für Kundengespraeche
- verkauft zunächst Priorisierung, Timing und Szenario-Splits
- verspricht ohne GELO-Outcome-Daten keine validierte ROI-Optimierung

### GELO

- bekommt bereits einen belastbaren Forecast-Readout
- liefert später Spend-, Sales-, Orders- oder Revenue-Daten für den Commercial Layer
- entscheidet mit über Produkt-, Keyword- und Aktivierungslogik

## Vor jedem Pilot-Readout

### 1. Live-Prüfung

```bash
curl -s https://fluxengine.labpulse.ai/health/live
```

Erwartung:

- HTTP `200`
- `status = alive`

### 2. Readiness-Prüfung

```bash
curl -s https://fluxengine.labpulse.ai/health/ready
```

Erwartung für den Forecast-First-Pilot:

- kein `unhealthy`
- keine kritischen Blocker im aktiven Demo-Scope
- Warning-only Degradation darf sichtbar bleiben, solange sie den aktiven Demo-Scope nicht fachlich entwertet

### 3. Produktkern-Smoke

```bash
cd /Users/davidwegener/Desktop/viralflux/backend
python scripts/smoke_test_release.py \
  --base-url https://fluxengine.labpulse.ai \
  --virus "RSV A" \
  --horizon 7 \
  --budget-eur 120000 \
  --top-n 3
```

Erwartung für den Forecast-First-Pilot:

- kein `live_failed`
- kein `business_smoke_failed`
- `ready_blocked` ist nur dann kritisch, wenn der aktive Demo-Scope selbst fachlich kippt

### 4. Kanonischen Pilot-Readout prüfen

```bash
curl -s "https://fluxengine.labpulse.ai/api/v1/media/pilot-readout?brand=gelo&virus_typ=RSV%20A&horizon_days=7&weekly_budget_eur=120000"
```

Erwartung für den Forecast-First-Pilot:

- `forecast_readiness = GO`
- `scope_readiness = GO`
- `pilot_mode = forecast_first`
- `budget_mode = scenario_split` oder `validated_allocation`
- `gate_snapshot.operational_readiness.live_source_coverage_readiness = GO`
- `gate_snapshot.operational_readiness.live_source_freshness_readiness = GO`

Commercial-Layer darf dabei noch sein:

- `commercial_validation_status = WATCH` oder `NO_GO`
- `budget_release_status = WATCH`

Wichtig:

- `source_coverage` im Snapshot bleibt Artefakt-/Trainingssicht
- der aktuelle operative Zustand für den Pilot-Readout kommt aus den Live-Feldern im `operational_readiness`-Block

## Offizieller Forecast-First-Pilot-Scope

Nur dieser Scope ist heute für externe Demos freigegeben:

- `brand = gelo`
- `virus_typ = RSV A`
- `horizon_days = 7`
- nur die kanonische `/pilot`-Surface bzw. `GET /api/v1/media/pilot-readout`

## Was im Forecast-First-Pilot gezeigt werden darf

- Regionen-Ranking mit `decision_stage`, `priority_score`, `event_probability`, `reason_trace`
- klare Timing- und Priorisierungsstory für Top-Regionen
- Budget als **forecast-basierter Szenario-Split**
- sichtbare Unsicherheit / Confidence
- klare Trennung zwischen:
  - `Forecast Ready`
  - `Commercial Validation Pending`

## Was noch nicht behauptet werden darf

- keine bereits bewiesene Umsatz- oder ROI-Optimierung
- keine implizite Spend-Freigabe ohne GELO-Outcome-Daten
- kein generelles Plattform-GO über andere Viren oder Horizonte hinweg

## Empfohlener Ablauf pro GELO-Meeting

1. `health/live`
2. `health/ready`
3. Produktkern-Smoke
4. scoped `pilot-readout`
5. Forecast-First GO oder NO_GO festhalten
6. nur dann den Forecast und die Szenario-Splits zeigen
7. Commercial Validation separat einordnen:
   - was schon vorhanden ist
   - was GELO-Daten später freischalten

## Eskalationslogik

### Fall A: `live_failed`

- Incident
- kein Pilotbetrieb

### Fall B: `business_smoke_failed`

- harter Produktkern-Blocker
- kein Forecast-First-GO

### Fall C: `scope_readiness != GO` im scoped `pilot-readout`

- kein externer Forecast-First-Pilot für diesen Scope
- erst Forecast-/Evaluation-/Promotion-Pfad reparieren

### Fall D: `scope_readiness = GO`, aber `commercial_validation_status != GO`

- Forecast-First-Pilot darf gezeigt werden
- Commercial Optimization darf **nicht** behauptet werden

## Aktueller Ist-Zustand am 2026-03-18

- `health/live` = grün
- `/health/ready` = degraded, aber nicht unhealthy
- `RSV A / h7` ist forecast-seitig tragfähig
- der kanonische `pilot-readout` trennt jetzt Forecast-Readiness und Commercial-Validation
- GELO-Outcome-Daten fehlen weiterhin für den Commercial Layer

## Harte operative Aussage

Am 18. Maerz 2026 ist der richtige Modus für PEIX / GELO:

- System live zeigen: ja
- Forecast und regionale Priorisierung zeigen: ja
- forecast-basierte Budget-Szenario-Splits zeigen: ja
- validierte Commercial- oder ROI-Claims machen: nein

Der richtige Satz für GELO ist:

- "Hier seht ihr bereits einen echten Forecast und eine belastbare Regionen-Priorisierung."
- "Wenn wir jetzt eure echten Outcome-Daten anschliessen, wird daraus zusätzlich der validierte Commercial Layer."
