# Product Positioning Decision Intelligence

Stand: 2026-03-17

## Kurzfassung

ViralFlux ist kein generisches Dashboard und kein vollautomatischer Media-Bot.

Im Kern ist es ein regionales Entscheidungs- und Aktivierungssystem fuer respiratorische Nachfrage- und Fruehsignale. Es soll vor allem vier Dinge besser machen:

- frueher erkennen, wo regionale Wellen relevant werden koennen
- Regionen operativ priorisieren statt bundesweit unscharf zu reagieren
- Budgets und Aktivierungen erklaerbar staffeln
- spaeter nachvollziehen, was empfohlen wurde, was aktiviert wurde und ob es plausibel war

## Worin der Wert liegt

Das Tool ist wertvoll, weil es eine Entscheidungskette zusammenzieht, die in vielen Teams heute getrennt laeuft:

1. epidemiologisches Signal
2. regionale Priorisierung
3. Budgetheuristik
4. Produkt- oder Keyword-Aktivierung
5. Evidenz- und Pilot-Reporting

Der Wert liegt nicht nur in der Prognose, sondern in der Qualitaet dieser operativen Fragen:

- Wo sollten wir zuerst hinschauen?
- Welche Regionen sind nur zu beobachten und welche verdienen echte Aktivierung?
- Wie stark ist die Empfehlung?
- Wodurch wird sie getragen?
- Wo ist Unsicherheit so hoch, dass Zurueckhaltung sinnvoller ist?
- Wie laesst sich spaeter zeigen, ob die Empfehlung ueberhaupt sinnvoll war?

## Was das System heute real kann

Code- und produktseitig ist heute bereits angelegt:

- regionale Forecast- und Decision-Outputs fuer `3/5/7` Tage
- pro Region `decision_label`, `priority_score`, `reason_trace` und `uncertainty_summary`
- heuristische Media Allocation mit Budget- und Aktivierungslogik
- Campaign Recommendations mit Produktclustern, Keywordclustern, Evidenzklasse und Rationale
- optionaler Commercial- oder Truth-Layer fuer Spend-Gates und Outcome-Kontext
- operatives Frontend-Dashboard
- Pilot-Reporting fuer Recommendation History, Activation History und KPI-Sichten

## Warum Explainability, Readiness und Allocation kaufrelevant sind

### Explainability

Ein hochpreisiges Tool in diesem Feld wird nicht nur daran gemessen, ob es ein Signal findet, sondern daran, ob Teams es intern vertreten koennen.

Deshalb sind `reason_trace`, `uncertainty_summary`, nested `decision`, Allocation-Trace und Recommendation-Rationale Teil des Produkts.

### Readiness

Readiness ist kaufrelevant, weil sie den Unterschied markiert zwischen:

- live vorhanden
- intern diskutierbar
- operativ freigegeben

Gerade fuer einen fruehen Design-Partner-Pilot ist das wichtig, weil Vertrauen schnell zerstoert wird, wenn technische Erreichbarkeit mit fachlicher Freigabe verwechselt wird.

### Allocation

Forecast ohne Allocation bleibt fuer Marketing oft zu abstrakt.

Allocation ist die Schicht, die aus "hier koennte etwas passieren" ein konkreteres "hier lohnt sich eher Aktivierung, dort eher Beobachtung" macht.

## Was das System heute bewusst nicht claimen sollte

ViralFlux sollte aktuell nicht als folgendes verkauft werden:

- vollautonomes Ad Buying
- kausal validiertes MMM
- sichere Umsatzlift-Prognose
- vollstaendig production-grade Plattform fuer alle Viren, Horizonte und Regionen
- extern freigegebener Pilot im aktuellen Live-Zustand

## Offiziell sinnvoller Scope fuer einen Design-Partner

### Heute glaubwuerdig verkaufbar

Nicht als fertige Black-Box-Produktionsmaschine, sondern als:

- hochpreisiger Decision-Intelligence-Layer
- mit regionaler Priorisierung
- mit erklaerbarer Budgetlogik
- mit diskussionsfaehigen Campaign Recommendations
- mit Governance-, Readiness- und Audit-Schichten
- mit klarer Pilot-zu-Plattform-Perspektive

### Heute noch nicht glaubwuerdig verkaufbar

- Always-on Plattform ohne manuelle Gating-Logik
- voll freigegebener operativer Rollout
- outcome-sicherer Budgetoptimierer

## Ehrliche aktuelle Position

Die richtige Positionierung lautet heute:

- ViralFlux ist ein ernstzunehmender regionaler Entscheidungs- und Aktivierungsansatz mit echter Explainability- und Governance-Substanz.
- ViralFlux ist heute noch kein voll freigegebenes Produktionssystem fuer externe operative Empfehlungen.
- Der kaufbare Einstieg ist deshalb ein streng gefuehrter Pilot- oder Design-Partner-Ansatz mit klaren Gates.

## Der verkaeufliche Satz

ViralFlux ist ein regionales Marketing- und Intelligence-System, das epidemiologische Signale in erklaerbare Priorisierungs-, Budget- und Aktivierungsempfehlungen uebersetzt und dabei bewusst zwischen live, pilot-ready und wirklich production-grade unterscheidet.
