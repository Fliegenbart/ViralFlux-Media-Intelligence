# Virus-Radar Hero Mockup Design

**Goal:** Die bestehende `Virus-Radar`-Seite soll die Klarheit und Denkweise des gelieferten Hero-Mockups übernehmen: eine klare Wochenaussage, eine dominante Kurve als Beweis und eine direkte Handlung für PEIX/GELO.

## Problem

Die aktuelle `Virus-Radar`-Seite bündelt viele Informationen, aber sie trifft die Wochenentscheidung nicht schnell genug. Zu viele Bereiche stehen gleichzeitig im Vordergrund. Die Seite wirkt eher wie ein Modul-Dashboard als wie ein fokussierter Wochen-Readout.

Das Mockup zeigt die gewünschte Gegenrichtung:

- eine kleine Live-Einordnung
- eine dominante Headline
- ein kurzer, verständlicher Absatz
- eine große Forecast-Kurve als primärer Beweis
- erst danach sekundäre Orientierung und operative Module

## Zielbild

`Virus-Radar` bleibt die zentrale Entscheidungsseite, aber der obere Bereich wird deutlich neu gewichtet:

1. **Live-Signal oben**
   Eine kleine, klare Zeile wie `Live-Signal · Influenza A`.

2. **Hero-Headline**
   Eine große Aussage in normaler Sprache, zum Beispiel:
   `Berlin läuft heiß. Peak in 4 Tagen.`

3. **Subline**
   Ein kurzer Absatz, der in einfacher Sprache erklärt:
   - was sich aufbaut
   - wann das Zeitfenster kommt
   - warum GELO jetzt handeln sollte

4. **Große Hero-Kurve**
   Die Forecast-Kurve wird direkt in den Hero gezogen und ist der wichtigste visuelle Beweis im ersten Viewport.

5. **Klare Aktionen**
   Primär: `Empfehlung prüfen`
   Sekundär: `Evidenz ansehen`
   Tertiär: `Kampagnen öffnen`

6. **Rest der Seite nachgeordnet**
   Erst unter dem Hero kommen:
   - kompakter Schnellstatus
   - Karte + Regionenleiter
   - Kampagnen-Reife
   - Warum jetzt
   - Risiken

## Nutzer- und Produktlinse

- **Primary user:** PEIX Strategist / GELO Entscheider
- **Screen decision:** Wo sollte diese Woche Media-Druck aufgebaut werden?
- **Primary CTA:** `Empfehlung prüfen`
- **Trust layer:** Forecast, Datenstand, Evidenz-Hinweis, Blocker
- **Preserved constraints:**
  - GELO bleibt explizit
  - Bundesland-Ebene bleibt erhalten
  - keine City-Scheingenauigkeit
  - bestehende Daten-Hooks und Routing-Struktur bleiben erhalten

## Informationshierarchie

### Heute

- `Virus-Radar` Hero mit mehreren gleich wichtigen Signalen
- Unterstützungsbox und Virus-Switcher konkurrieren mit der Hauptaussage
- Forecast-Chart liegt tiefer auf der Seite
- Karte und Statusmodule nehmen dem Hero die erste Aufmerksamkeit

### Nach der Änderung

- Hero beantwortet zuerst: `Was passiert gerade?`
- Chart beantwortet direkt danach: `Woher wissen wir das?`
- CTA beantwortet: `Was tun wir jetzt?`
- Alles andere wird nachgeordnet

## Inhaltliche Logik des neuen Hero

Der Hero baut sich aus echten Daten zusammen:

- **Virus:** aus der aktiven Virus-Auswahl
- **Fokusregion:** aus `focusRegion` oder der höchsten priorisierten Vorhersage
- **Peak:** aus dem höchsten künftigen Wert der Fokusregion-Timeline
- **Signaltonalität:** aus Wahrscheinlichkeit, Empfehlung und Trend

### Headline-Regeln

- Wenn ein klarer Peak bevorsteht und die Wahrscheinlichkeit ausreichend hoch ist:
  - `<Region> läuft heiß. Peak in <x> Tagen.`
- Wenn der Peak heute oder morgen liegt:
  - `<Region> läuft heiß. Peak heute.`
  - `<Region> läuft heiß. Peak morgen.`
- Wenn kein belastbarer Peak erkennbar ist:
  - `<Region> jetzt priorisieren.`
  - oder eine ruhigere Beobachtungsform, abhängig von Signal und Empfehlung

### Subline-Regeln

Die Subline bleibt in normaler Sprache und vermeidet Modell-Sprech. Sie soll:

- die Dynamik benennen
- das Datum des Peak-Fensters nennen
- GELO als Handlungsempfänger klar nennen

## UI-Struktur

### Hero

- Topline mit Produktkontext und Datenstand
- `Live-Signal`-Eyebrow mit Puls
- große Headline
- kurze Subline
- Hero-Chart-Karte mit Legende und Datenstand
- CTA-Reihe
- ruhiger Virus-Switcher unterhalb des Hero oder im Hero-Fuß

### Nachgelagerte Bereiche

- kompakter Radar-Strip
- Karte + Regionenleiter
- Kampagnen / Aktivierungsreihenfolge
- Why Now / Decision Risk

## Komponenten- und Dateiscope

### Direkter Fokus

- `frontend/src/components/cockpit/VirusRadarWorkspace.tsx`
- `frontend/src/styles/pages/virus-radar.css`

### Voraussichtlich nötig

- `frontend/src/components/cockpit/ForecastChart.tsx`
- `frontend/src/components/cockpit/VirusRadarWorkspace.test.tsx`

## Zustände

Der Umbau soll diese Zustände besser sichtbar machen:

- starker Peak
- kein klarer Peak
- niedrige Datenfrische
- fehlende Timeline / leere Forecast-Daten
- keine direkt öffnbare Empfehlung

## Risiken

- Wenn wir zu nah nur am Look kopieren, ohne die Hierarchie zu übernehmen, verlieren wir die eigentliche Stärke des Mockups.
- Wenn wir den Hero zu dekorativ machen, verliert die Seite wieder Ruhe.
- Wenn wir Forecast- und Peak-Text zu aggressiv formulieren, obwohl die Datenlage schwächer ist, wirkt die Seite überverkauft.

## Umsetzungsprinzip

Kleine, gezielte Änderung statt Full-Page-Redesign:

- Hero neu denken
- Chart nach oben ziehen
- Rest der Seite ruhiger staffeln
- bestehende Datenanbindung und restliche Page-Module erhalten
