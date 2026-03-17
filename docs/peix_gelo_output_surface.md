# PEIX / GELO Pilot Output Surface

Stand: 2026-03-17

## Zweck

Diese Oberfläche uebersetzt die bestehenden Forecast-, Allocation-, Recommendation- und Pilot-Evidence-Outputs in eine management-taugliche Sicht fuer PEIX und GELO.

Sie ist bewusst keine neue Scoring- oder Decision-Engine. Die Seite liest nur vorhandene Backend-Outputs und ordnet sie so, dass ein Kunde die aktuelle Lage schnell versteht.

## Route

- Frontend-Route: `/pilot`
- Shell: `MediaShell`
- Page-Komponente: `frontend/src/pages/media/PilotPage.tsx`
- Haupt-UI: `frontend/src/components/cockpit/PilotSurface.tsx`
- Datenhook: `frontend/src/features/media/usePilotSurfaceData.ts`
- API-Client: `frontend/src/features/media/api.ts`
- Typen: `frontend/src/types/media/pilot.ts`

## Datenquellen

Die Seite laedt parallel:

1. regionale Forecast-Daten
2. regionale Allocation-Daten
3. regionale Campaign Recommendations
4. Medien-Evidenz / Truth-Kontext
5. Pilot-Reporting fuer Evidenz und Before/After-Readouts

Verwendete Endpunkte:

- `GET /api/v1/forecast/regional/decisions`
- `GET /api/v1/forecast/regional/media-allocation`
- `GET /api/v1/forecast/regional/campaign-recommendations`
- `GET /api/v1/media/evidence`
- `GET /api/v1/media/pilot-reporting`

## Screen-Struktur

### 1. Executive Summary

Antwortet auf die Frage: `What should we do now?`

Enthaelt:

- aktuelle Lead-Region
- Entscheidungstage
- empfohlene Budgetspitze
- Confidence / Uncertainty
- kurze Reason-Trace in Klartext
- die wichtigsten Regionen im aktuellen Filter

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

Dieser Block macht die Entscheidung nachvollziehbar und archivierungsfaehig.

Enthaelt:

- Pilot KPI Summary
- Region Evidence Rollup
- Before / After Vergleiche
- Truth- und Business-Readiness
- Methodik- und Zeitfenster-Kontext

## Empty States

Die Seite zeigt explizite, kundenlesbare Leermodi:

- `no_model`
- `no_data`
- `watch_only`
- `no_go`

Diese Zustände sind bewusst sichtbar und sollen keine implizite Freigabe suggerieren.

## Designprinzipien

- keine neue Business-Logik im Frontend
- keine Charts um der Charts willen
- klare Entscheidbarkeit statt analytischer Ueberladung
- rohe technische Begriffe nur dort, wo sie wirklich als Evidenz helfen
- GO / WATCH / NO_GO bleibt als operative Sprache sichtbar

## Nutzungslogik

Die Oberflaeche ist fuer den Pilot-Review gedacht:

1. aktuelle Lage lesen
2. Regionen und Budgets verstehen
3. Empfehlung und Evidenz nachvollziehen
4. Readiness beurteilen

Die Seite ist damit die kundennahe Leseschicht fuer PEIX, die GELO in Meetings eine klare und nachvollziehbare Budget- und Priorisierungsstory liefert.
