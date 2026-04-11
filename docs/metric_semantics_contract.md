# Metric Semantics Contract

Basis:
- [backend/app/services/media/semantic_contracts.py](../backend/app/services/media/semantic_contracts.py)

Stand: 2026-03-24

## Ziel

Diese Datei legt in einfachen Worten fest, wie zentrale Kennzahlen in ViralFlux gemeint sind.

Die Grundregel lautet:

- ein `Score` bleibt ein `Score`
- eine `Wahrscheinlichkeit` darf nur dann wie eine Wahrscheinlichkeit klingen, wenn sie auch als solche gemeint ist
- eine `Sicherheit` oder `Confidence` muss sagen, wovon sie eigentlich spricht

## Kanonische Kennzahltypen

### 1. `ranking_signal`

- Produktwort: `Signal-Score`
- Bedeutung:
  Hilft beim Vergleichen und Priorisieren von Regionen oder Faellen.
- Wichtig:
  Das ist **keine Eintrittswahrscheinlichkeit**.
- Typische Beispiele:
  - `signal_score`
  - aeltere `impact_probability`-Felder, wenn sie nur aus Score-Abbildungen stammen

### 2. `activation_priority`

- Produktwort: `Prioritaets-Score`
- Bedeutung:
  Hilft bei der Reihenfolge, was zuerst bearbeitet oder freigegeben werden sollte.
- Wichtig:
  Das ist **keine Eintrittswahrscheinlichkeit**.

### 3. `forecast_event_probability`

- Produktwort: `Event-Wahrscheinlichkeit`
- Bedeutung:
  Kalibrierte Wahrscheinlichkeit für ein klar definiertes Forecast-Ereignis.
- Wichtig:
  Nur so benennen, wenn die Zahl wirklich aus dem kalibrierten Forecast-Pfad kommt.
- Zusatzfelder:
  - `probability_source`
  - `fallback_used`
- Anzeige-Regel:
  Wenn `fallback_used = true`, muss das sichtbar gesagt werden.

### 4. `signal_confidence`

- Produktwort: `Signal-Sicherheit`
- Bedeutung:
  Sicherheit des Signals oder Agreement zwischen Hinweisen.
- Wichtig:
  Das ist **nicht automatisch eine Modellwahrscheinlichkeit**.

### 5. `observed_outcome_signal`

- Produktwort: `Outcome-Score`
- Bedeutung:
  Beobachtetes Lernsignal aus Kundendaten.
- Wichtig:
  Das ist **keine Forecast-Wahrscheinlichkeit**.

### 6. `outcome_learning_confidence`

- Produktwort: `Lern-Sicherheit`
- Bedeutung:
  Wie belastbar das Outcome-Lernsignal aktuell ist.
- Wichtig:
  Das ist **keine Modellkalibrierung**.

### 7. `truth_readiness`

- Produktwort: `Kundendatenbasis`
- Bedeutung:
  Wie gut der Outcome-Layer bereits angeschlossen und nutzbar ist.

### 8. `business_validation_gate`

- Produktwort: `Business-Freigabe`
- Bedeutung:
  Ob aus einem epidemiologischen Signal schon eine kommerzielle Freigabe werden darf.

### 9. `business_evidence_tier`

- Produktwort: `Belegstufe`
- Bedeutung:
  Reifegrad der Outcome- und Business-Evidenz.

## Pflichtregeln für UI und API

1. Eine Kennzahl mit `ranking_signal` darf in der UI nicht wie eine Wahrscheinlichkeit dargestellt werden.
2. Eine Kennzahl mit `signal_confidence` darf nicht als Modellwahrscheinlichkeit beschrieben werden.
3. Eine Kennzahl mit `forecast_event_probability` muss sichtbar machen, wenn sie aus einem Fallback kommt.
4. Outcome-Lernsignale müssen sprachlich klar von Forecast-Signalen getrennt bleiben.
5. Wenn die Semantik unklar ist, wird die Zahl konservativ als `Score` behandelt und nicht als `Probability`.

## Kurzfassung für Produkttexte

- `Signal-Score`:
  "Hilft beim Vergleichen, ist aber keine Eintrittswahrscheinlichkeit."
- `Prioritaets-Score`:
  "Hilft bei der Reihenfolge der Aktivierung."
- `Event-Wahrscheinlichkeit`:
  "Kalibrierte Wahrscheinlichkeit für das definierte Forecast-Ereignis."
- `Signal-Sicherheit`:
  "Beschreibt Signalsicherheit oder Agreement, nicht die Modellwahrscheinlichkeit."
- `Outcome-Score`:
  "Beobachtetes Lernsignal aus Kundendaten."
- `Lern-Sicherheit`:
  "Beschreibt die Sicherheit des Outcome-Lernsignals."
