# Pilot To Platform Path

Stand: 2026-03-17

## Ziel

Dieses Dokument beschreibt, wie ViralFlux realistisch von einem bewusst engen Partnerpilot in einen größeren Plattformvertrag wachsen kann, ohne mehr zu versprechen als das System heute hergibt.

## Ausgangspunkt heute

Der Stand des laufenden Systems ist:

- Live erreichbar: ja
- Pilot-ready: nein
- Fully production-grade: nein

Technische Realitaet heute:

- `health/live` ist grün
- `health/ready` ist `503`
- der moderne Kernpfad-Smoke endet mit `business_smoke_failed`
- die regionalen Kernendpunkte liefern aktuell live `500`
- Artefaktseitig ist der Horizon-Scope weitgehend aufgebaut
- `RSV A / h3` ist bewusst unsupported

Das bedeutet:

- ein Plattformvertrag kann heute argumentativ vorbereitet werden
- ein echter externer Pilot darf aber noch nicht als freigegebener Routinebetrieb dargestellt werden

## Die vier Stufen

## Stufe 0: Live Demonstrable System

### Was diese Stufe ist

Das System ist sichtbar, technisch deploybar und in seiner Zielarchitektur erkennbar.

### Was diese Stufe noch nicht ist

- kein freigegebener Pilot
- keine externe operative Handlungsempfehlung
- keine belastbare Always-on Nutzung

### Aktueller Stand

- diese Stufe ist erreicht

## Stufe 1: Internal Shadow Pilot

### Ziel

Pilotpartner und Produktteam nutzen ViralFlux intern parallel zu ihrem bestehenden Entscheidungsprozess, ohne externe Aktivierungen direkt daraus abzuleiten.

### Was geliefert wird

- Dashboard
- regionale Forecast-/Decision-Views
- Allocation- und Recommendation-Outputs
- Readiness- und Smoke-Checks
- Pilot-Reporting als interne Review-Basis

### Eintrittskriterien

- Kernpfad liefert keine `500` mehr
- Release-Smoke faellt nicht mehr mit `business_smoke_failed`
- mindestens ein begrenzter Virus-/Horizon-Scope ist technisch stabil

### Geschaeftlicher Nutzen

- Teams lernen das System kennen
- Explainability wird gegen echte Operatorfragen getestet
- false confidence wird vermieden

## Stufe 2: Guided External Pilot

### Ziel

Ein bewusst enger Pilot-Scope wird extern genutzt, aber mit manueller Governance und klaren Vorbehalten.

### Typischer Scope

- 1 bis 2 Viren
- 1 bis 2 Horizonte
- begrenzte regionale Nutzung
- manuelle Freigabe durch Produktteam und Pilotpartner

### Was offiziell unterstuetzt sein muss

- `health/live`
- `health/ready` nicht `unhealthy`
- Forecast, Allocation und Campaign Recommendations für den Pilot-Scope
- dokumentierte Support-Matrix
- Runbook und Freigabelogik

### Was noch bewusst manuell bleibt

- Spend-Freigabe
- finale Kampagnenentscheidung
- Truth-/Outcome-Interpretation

### Geschaeftlicher Wert

- der Pilot liefert nicht nur Empfehlungen, sondern auch eine auditierbare Geschichte:
  - was wurde gesehen
  - was wurde priorisiert
  - was wurde empfohlen
  - was wurde aktiviert
  - was ist danach passiert

## Stufe 3: Paid Operational Pilot

### Ziel

ViralFlux wird nicht mehr nur als Experiment genutzt, sondern als regelmäßiger Bestandteil regionaler Aktivierungsplanung.

### Merkmale

- fester Weekly oder Twice-Weekly Operating Cadence
- definierter Support-Scope
- klarer Go/No-Go Prozess
- dokumentierte Known Limitations
- Pilot-Reporting und ROI-Readouts für Steering-Runden

### Zusätzlicher Vertragsspielraum

- mehr Produkte / Cluster
- mehr Regionen
- mehr Regelmäßigkeit
- stärkere Outcome- und Reporting-Bindung

## Stufe 4: Platform Contract

### Ziel

Aus dem Pilot wird eine laufende Decision- und Activation-Plattform.

### Was dafür zusätzlich nötig ist

- stabil grüner Kernpfad
- Forecast-Recency über operative Snapshots statt Trainings-Lag
- reduzierte Quality-/Coverage-Blocker im verkauften Scope
- konsistente Release-, Smoke- und Rollback-Routine
- saubere Governance für Rollen, Freigaben und Auditability

### Was dann verkauft wird

- Always-on Regional Activation Intelligence
- nicht nur ein Projekt, sondern ein Operating Layer
- mit klaren Support- und Governance-Grenzen

## Pilot-zu-Plattform Übersetzung

Der größte Fehler waere, so zu tun, als sei der Schritt vom Pilot zur Plattform rein "mehr vom Gleichen".

Tatsaechlich verschiebt sich der Wert in drei Richtungen:

### 1. Von Insights zu Governance

Am Anfang kauft der Kunde Einsicht und Priorisierung.

Später kauft er:

- Release-Sicherheit
- Freigabelogik
- belastbare Betriebsfähigkeit

### 2. Von einer Empfehlung zu einem Entscheidungsprozess

Am Anfang ist die Frage:

- "Ist diese Empfehlung nuetzlich?"

Später ist die Frage:

- "Können wir darauf regelmäßig und teamübergreifend arbeiten?"

### 3. Von Pilot-Evidenz zu Vertragsvertrauen

Pilot-Reporting, Outcome-Overlay und Recommendation-History sind nicht nur Add-ons. Sie sind das Material, aus dem ein größerer Vertrag intern begründet wird.

## Was den Sprung aktuell blockiert

Heute fehlen für den nächsten Schritt vor allem:

1. grüner moderner Kernpfad-Smoke
2. stabile `200` auf den regionalen Produktendpunkten
3. bessere operative Forecast-Recency
4. weniger rote regionale Readiness-Blocker

Deshalb ist die ehrliche Reihenfolge:

1. Kernpfad stabilisieren
2. enger externer Pilot
3. Pilot-Readouts mit harter Evidenz
4. Ausbau zum Plattformvertrag

## Die ehrliche Vertriebslogik

Heute sollte ViralFlux für einen engen Partnerpilot so verkauft werden:

- nicht als "fertige Plattform, die nur noch eingeschaltet werden muss"
- sondern als hochwertiger, streng gefuehrter Pilot mit klarer Plattform-Perspektive

Der Plattformvertrag ist damit keine Fantasie-Stufe, sondern die nächste Ausbaustufe, sobald der operative Kernpfad technisch und fachlich die Pilot-Freigabe wirklich erfüllt.
