# Product Positioning PEIX / GELO

Stand: 2026-03-17

## Kurzfassung

ViralFlux ist kein generisches Dashboard und kein vollautomatischer Media-Bot.

Im realen Systemkern ist es ein regionales Entscheidungs- und Aktivierungssystem für respiratorische Nachfrage- und Frühsignale, das für PEIX und GELO vor allem vier Dinge besser machen soll:

- früher erkennen, wo regionale Wellen relevant werden können
- Regionen operativ priorisieren statt bundesweit unscharf zu reagieren
- Budgets und Aktivierungen erklaerbar staffeln
- später nachvollziehen, was empfohlen wurde, was aktiviert wurde und ob es plausibel war

## Worin der Wert liegt

Das Tool ist wertvoll, weil es eine Entscheidungskette zusammenzieht, die in vielen Teams heute getrennt läuft:

1. epidemiologisches Signal
2. regionale Priorisierung
3. Budgetheuristik
4. Produkt-/Keyword-Aktivierung
5. Evidenz- und Pilot-Reporting

Für PEIX und GELO verbessert das nicht in erster Linie "die schönste Prognose", sondern die Qualitaet dieser operativen Fragen:

- Wo sollten wir zuerst hinschauen?
- Welche Regionen sind nur zu beobachten und welche verdienen echte Aktivierung?
- Wie stark ist die Empfehlung?
- Wodurch wird sie getragen?
- Wo ist Unsicherheit so hoch, dass Zurückhaltung sinnvoller ist?
- Wie lässt sich später zeigen, ob die Empfehlung überhaupt sinnvoll war?

## Was das System heute real kann

Code- und produktseitig ist heute bereits angelegt:

- regionale Forecast-/Decision-Outputs für `3/5/7` Tage
- per Region:
  - `decision_label`
  - `priority_score`
  - `reason_trace`
  - `uncertainty_summary`
  - nested `decision`
- heuristische Media Allocation mit:
  - `recommended_activation_level`
  - `priority_rank`
  - `suggested_budget_share`
  - `suggested_budget_amount`
  - `confidence`
  - `allocation_reason_trace`
- Campaign Recommendations mit:
  - Produktcluster
  - Keywordcluster
  - Aktivierungslevel
  - Budgetvorschlag
  - Evidenzklasse
  - Rationale
- optionaler Commercial-/Truth-Layer für Spend-Gates und Outcome-Kontext
- operatives Frontend-Dashboard
- Pilot-Reporting für Recommendation History, Activation History und KPI-Sichten

## Warum Explainability, Readiness und Allocation kaufrelevant sind

### Explainability

Ein hochpreisiges Tool in diesem Feld wird nicht nur daran gemessen, ob es "ein Signal" findet, sondern daran, ob Teams es intern vertreten können.

Deshalb sind `reason_trace`, `uncertainty_summary`, nested `decision`, Allocation-Trace und Recommendation-Rationale keine Nebensache, sondern Teil des Produkts.

Ohne diese Schichten bleibt das System eine Black Box. Mit ihnen wird es ein steuerbares Entscheidungswerkzeug.

### Readiness

Readiness ist kaufrelevant, weil sie den Unterschied markiert zwischen:

- live vorhanden
- intern diskutierbar
- operativ freigegeben

Gerade für PEIX / GELO ist das wichtig, weil ein früher Pilot schnell Vertrauen zerstoert, wenn technische Erreichbarkeit mit fachlicher Freigabe verwechselt wird.

### Allocation

Forecast ohne Allocation bleibt für Marketing oft zu abstrakt.

Allocation ist die Schicht, die aus "hier könnte etwas passieren" ein konkreteres "hier lohnt sich eher Aktivierung, dort eher Beobachtung" macht. Genau das ist für Budgetgespraeche wertvoller als eine nackte Wahrscheinlichkeit.

## Was das System heute bewusst nicht claimen sollte

ViralFlux sollte aktuell nicht als folgendes verkauft werden:

- vollautonomes Ad Buying
- kausal validiertes MMM
- sichere Umsatzlift-Prognose
- vollstaendig production-grade Plattform für alle Viren, Horizonte und Regionen
- extern freigegebener Pilot im aktuellen Live-Zustand

Diese Nicht-Claims sind wichtig, weil das System am 17. Maerz 2026 zwar live erreichbar ist, aber noch nicht pilotfreigegeben:

- `health/live` = grün
- `health/ready` = `503`
- moderner Business-Smoke = `business_smoke_failed`

## Offiziell sinnvoller Scope für PEIX / GELO

### Heute glaubwürdig verkaufbar

Nicht als "fertige Black-Box-Produktionsmaschine", sondern als:

- hochpreisiger Decision-Intelligence-Layer
- mit regionaler Priorisierung
- erklaerbarer Budgetlogik
- diskussionsfähigen Campaign Recommendations
- Governance-, Readiness- und Audit-Schichten
- klarer Pilot-zu-Plattform-Perspektive

### Heute noch nicht glaubwürdig verkaufbar

- "Always-on Plattform ohne manuelle Gating-Logik"
- "voll freigegebener operativer Rollout"
- "Outcome-sicherer Budgetoptimierer"

## Warum trotzdem High-Value

Der Preis darf hoch sein, wenn das Produkt nicht als Datenexperiment, sondern als Entscheidungsinfrastruktur positioniert wird.

Der Wert kommt dann aus:

- besserer Priorisierung knapper regionaler Aufmerksamkeit
- weniger blindem Spend
- klareren Eskalations- und Hold-Entscheidungen
- kuerzerer Abstimmung zwischen Data, Media, Brand und Management
- besserer Auditierbarkeit für Pilot-Readouts

Das ist kein "billiges Analytics-Addon", sondern ein Instrument, das Budget-, Timing- und Governance-Entscheidungen strukturiert.

## Ehrliche aktuelle Position

Die richtige Positionierung für PEIX / GELO lautet heute:

- ViralFlux ist ein ernstzunehmender regionaler Entscheidungs- und Aktivierungsansatz mit echter Explainability- und Governance-Substanz.
- ViralFlux ist heute noch kein voll freigegebenes Produktionssystem für externe operative Empfehlungen.
- Der kaufbare Einstieg ist deshalb ein streng gefuehrter Pilot- bzw. Design-Partner-Ansatz mit klaren Gates, nicht sofort der ungebremste Plattformbetrieb.

## Der verkaeufliche Satz

Wenn man es in einem Satz zuspitzt:

> ViralFlux ist ein regionales Marketing- und Intelligence-System, das epidemiologische Signale in erklaerbare Priorisierungs-, Budget- und Aktivierungsempfehlungen übersetzt und dabei bewusst zwischen live, pilot-ready und wirklich production-grade unterscheidet.
