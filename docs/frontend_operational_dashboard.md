# Frontend Operational Dashboard

## Ziel

Das Frontend-Dashboard macht den bestehenden regionalen Forecast-/Decision-/Allocation-/Recommendation-Output für PEIX und GELO ohne Code lesbar. Die Ansicht ist bewusst management-tauglich aufgebaut:

- Wo entwickelt sich eine Welle?
- Welche Regionen haben operative Priorität?
- Wie verteilt sich das Budget?
- Welche Produkt- und Keywordcluster werden empfohlen?
- Wie belastbar ist die Empfehlung?

## Einstieg im Frontend

- Route: `/dashboard`
- Page-Komponente: `frontend/src/pages/media/OperationalDashboardPage.tsx`
- Haupt-UI: `frontend/src/components/cockpit/OperationalDashboard.tsx`
- Datenhook: `frontend/src/features/media/useMediaData.ts`
- API-Client: `frontend/src/features/media/api.ts`
- Typen: `frontend/src/types/media/regional.ts`

Die Seite liegt innerhalb von `MediaShell` und nutzt den bestehenden `MediaWorkflowProvider`.

## Verwendete Backend-Endpunkte

Das Dashboard ruft drei bestehende regionale Outputs parallel ab:

1. `/api/v1/forecast/regional/decisions`
   - Forecast + Decision pro Region
   - dient als kanonischer Layer für Regionenranking und Decision Stage
2. `/api/v1/forecast/regional/media-allocation`
   - Budget- und Aktivierungslogik pro Region
   - dient für Budgetsicht, Spend-Gate und Allocation Trace
3. `/api/v1/forecast/regional/campaign-recommendations`
   - konkrete Produkt-/Keywordcluster und operative Diskussionsempfehlung
   - dient für die Campaign-Recommendation-Ansicht

Die Frontend-Seite berechnet keine neuen Decision- oder Allocation-Scores, sondern visualisiert den bestehenden Backend-Output.

## Screen-Aufbau

### 1. Filterleiste

Oben steht eine kombinierte Filterleiste mit:

- Virus
- Horizon (`3`, `5`, `7`)
- Region
- Decision Stage (`Activate`, `Prepare`, `Watch`)
- Budgetbasis als Kontext
- Zeitstempel für Forecast, Allocation und Recommendation

Die Horizon-Auswahl ist ein echter Produktfilter und wird direkt an alle drei Endpunkte durchgereicht.

### 2. Executive Summary

Der Hero-Bereich beantwortet die Frage:

> What should we do now?

Er zeigt:

- führende Region
- empfohlene Stage
- führendes Produktcluster
- Keywordcluster
- Budgetspitze
- Lead-Confidence
- Evidence-/Spend-Gate-Kontext

Die Zusammenfassung priorisiert die beste operative Empfehlung im aktuellen Filter-Scope.

### 3. Decision Stage Visualisierung

Die Stage-Ansicht gruppiert Regionen in:

- `Activate`
- `Prepare`
- `Watch`

Wichtig:

- die Sortierung folgt dem `decision_rank`
- nicht der reinen Forecast-Wahrscheinlichkeit

So bleibt die kanonische Decision-Logik sichtbar.

### 4. Confidence & Unsicherheit

Für die aktuelle Fokusregion werden separat gezeigt:

- Forecast Confidence
- Source Freshness
- Revision Risk
- Cross-Source Agreement
- kompakte Unsicherheitserklärung
- Decision Reason Trace

Damit sieht das Team nicht nur die Empfehlung, sondern auch die Unsicherheitsseite.

### 5. Regionen-Ranking

Die Ranking-Tabelle zeigt pro Region:

- Decision Rank
- Region
- Decision Stage
- Wave Chance
- Trend / Change
- Priority Score
- Forecast Confidence
- erste Reason-Trace-Begründung

Die Tabelle verwendet bewusst den Decision-Rank als operative Sortierung.

### 6. Allocation & Budget

Die Allocation-Tabelle zeigt pro Region:

- Priority Rank
- Activation Level
- Budgetbetrag
- Budget Share
- Confidence
- Spend-Gate-Status

Zusätzlich wird eine kompakte Allocation Summary eingeblendet.

### 7. Recommendation-Ansicht

Die Recommendation-Karten machen den Übergang von Budget zu operativer Aktivierung sichtbar:

- Region
- Product Cluster
- Keyword Cluster
- Activation Level
- Budget Amount / Share
- Confidence
- Evidence Class
- Spend Guardrails
- Recommendation Rationale

Das ist bewusst diskussionsfähig, aber kein vollautomatisches Ad Buying.

### 8. Reason Traces verständlich

Am unteren Ende werden die drei Erklärungs-Layer nebeneinander gezeigt:

- Decision
- Allocation
- Recommendation

So bleibt die Kette von epidemiologischer Logik bis zur Kampagnenempfehlung nachvollziehbar.

## Empty-State-Verhalten

Die Seite behandelt leere oder unvollständige Daten explizit:

- `no_model`
  - klare Meldung, dass für Virus/Horizon noch kein regionales Modell verfügbar ist
- `no_data`
  - klare Meldung, dass aktuell keine verwertbaren Regionensignale vorliegen
- leere Recommendations
  - eigener Hinweis, dass bei `Watch`-Regionen oder blockiertem Spend Gate keine direkte Campaign Recommendation erwartet wird

Wichtig:

- Die Filter bleiben auch im Empty State sichtbar.
- Nutzer können also direkt Virus oder Horizon wechseln.

## Typisierung

Die neuen Frontend-Typen liegen in `frontend/src/types/media/regional.ts`.

Abgedeckt sind:

- Forecast-Response
- per-Region Forecast-/Decision-Payload
- nested Decision Payload
- Allocation-Response
- Campaign-Recommendation-Response
- Reason Trace
- Truth-/Outcome-bezogene Commercial-Gate-Felder
- Empty-State-Felder (`status`, `message`)

Damit ist der regionale Dashboard-Contract im Frontend nicht mehr nur implizit.

## Grenzen des aktuellen Dashboards

- Recommendations kommen aktuell aus dem Top-N-Recommendation-Output des Backends und decken daher nicht immer jede Region ab.
- Das Dashboard zeigt operative Interpretation, ersetzt aber keine Media-Freigabe.
- Budgetbasis wird aus dem bestehenden Workflow-Kontext übernommen und im Dashboard nicht separat neu gepflegt.

## Tests

Abgedeckt ist die neue UI in:

- `frontend/src/components/cockpit/OperationalDashboard.test.tsx`

Die Tests prüfen:

- Success-Rendering
- Filterreaktion auf Decision Stage
- stabilen `no_model`-Empty-State
