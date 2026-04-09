# PEIX / GELO Pilot Output Surface

Stand: 2026-03-17

## Zweck

Diese Oberfläche übersetzt die bestehenden Forecast-, Allocation-, Recommendation- und Pilot-Evidence-Outputs in eine management-taugliche Sicht für PEIX und GELO.

Sie ist bewusst keine neue Scoring- oder Decision-Engine. Die Seite liest nur vorhandene Backend-Outputs und ordnet sie so, dass ein Kunde die aktuelle Lage schnell versteht.

Seit dem Forecast-First-Update gilt:

- die Seite darf bereits ohne GELO-Outcome-Daten einen echten Forecast zeigen
- Forecast-Readiness und Commercial-Validation werden bewusst getrennt dargestellt
- Budget wird ohne GELO-Daten als `scenario_split` und nicht als bewiesene ROI-Freigabe gezeigt

## Route

- Historische Frontend-Route: `/pilot`
- Aktiver Live-Hauptfluss: `Login -> /jetzt -> /regionen -> /kampagnen -> /evidenz`
- `/pilot` ist historisch und nicht mehr Teil des aktiven Live-Hauptflusses.
- Shell: `MediaShell`
- Page-Komponente: `frontend/src/pages/media/PilotPage.tsx`
- Haupt-UI: `frontend/src/components/cockpit/PilotSurface.tsx`
- Datenhook: `frontend/src/features/media/usePilotSurfaceData.ts`
- API-Client: `frontend/src/features/media/api.ts`
- Typen: `frontend/src/types/media/pilotReadout.ts`

## Datenquellen

Die Seite liest jetzt einen kanonischen Customer-Contract statt fuenf lose Frontend-Calls.

Primaerer Endpunkt:

- `GET /api/v1/media/pilot-readout`

Dieser Readout komponiert serverseitig:

1. regionalen Forecast
2. regionale Allocation
3. regionale Campaign Recommendations
4. aktuelle Gate-/Readiness-Sicht
5. letzte archivierte Live-Evaluation

Wichtige Customer-Facing Felder:

- `forecast_readiness`
- `commercial_validation_status`
- `pilot_mode = forecast_first`
- `budget_mode = scenario_split | validated_allocation`
- `validation_disclaimer`

Legacy-/Backoffice-Kontexte bleiben getrennt:

- `GET /api/v1/media/pilot-reporting`
  Nur noch für interne / historische Evidence-Analysen.
- `POST /api/v1/media/outcomes/import`
  Nur noch manueller Backoffice-Fallback.
- `POST /api/v1/media/outcomes/ingest`
  Offizielle GELO M2M-Ingestion für Outcome-Daten.

## Screen-Struktur

### 1. Executive Summary

Antwortet auf die Frage: `What should we do now?`

Enthält:

- aktuelle Lead-Region
- Entscheidungstage
- forecast-basierte Budgetspitze bzw. Szenario-Split
- Confidence / Uncertainty
- kurze Reason-Trace in Klartext
- die wichtigsten Regionen im aktuellen Filter
- getrennte Spur für:
  - `Forecast Ready`
  - `Commercial Validation`

### 2. Operational Recommendations

Zeigt den aktiven Fokus als eine von vier Sichten:

- `forecast`
- `allocation`
- `recommendation`
- `evidence`

Die Filter wirken auf:

- `virus`
- `horizon`
- `scope`
- `stage`

Die Sicht bleibt bewusst business-first:

- Forecast: Regionenranking und Wave Chance
- Allocation: Budgetsplit und Spend-Gate
- Recommendation: Produkt-, Keyword- und Campaign-Plan
- Evidence: Pilot-Readout mit regionaler Evidenz

### 3. Pilot Evidence / Readiness

Dieser Block macht die Entscheidung nachvollziehbar und auditierbar.

Enthält:

- Scope-Readiness für Forecast / Allocation / Recommendation / Evidence
- letzte archivierte Live-Evaluation
- Truth- / Business-Gate / Holdout / Budget-Release Status
- fehlende Voraussetzungen in Klartext
- quarantinierten `legacy_context` mit Sunset-Datum für den Altpfad

## Empty States

Die Seite zeigt explizite, kundenlesbare Leermodi:

- `no_model`
- `no_data`
- `watch_only`
- `no_go`

Diese Zustände sind bewusst sichtbar und sollen keine implizite Freigabe suggerieren.

Wichtig:

- `ready` kann jetzt für den Forecast-First-Pilot gelten, auch wenn der Commercial Layer noch nicht `GO` ist
- der Commercial-Upgrade-Pfad bleibt im Screen sichtbar

## Designprinzipien

- keine neue Business-Logik im Frontend
- keine Charts um der Charts willen
- klare Entscheidbarkeit statt analytischer Überladung
- rohe technische Begriffe nur dort, wo sie wirklich als Evidenz helfen
- GO / WATCH / NO_GO bleibt als operative Sprache sichtbar
- `priority_score` statt Pseudo-Probability, solange keine echte Kalibrierung vorliegt
- kein ROI- oder Lift-Claim ohne echte GELO-Outcome-Daten

## Nutzungslogik

Die Oberflaeche ist für den Pilot-Review gedacht:

1. aktuelle Lage lesen
2. Regionen und Budgets verstehen
3. Empfehlung und Evidenz nachvollziehen
4. Readiness beurteilen

Die Seite ist damit die kundennahe Leseschicht für PEIX, die GELO in Meetings eine klare und nachvollziehbare Budget- und Priorisierungsstory liefert.

Die ehrliche Standardsprache ist:

- "Hier seht ihr bereits einen echten Forecast und eine belastbare Regionen-Priorisierung."
- "Mit euren Outcome-Daten wird daraus zusätzlich der validierte Commercial Layer."
