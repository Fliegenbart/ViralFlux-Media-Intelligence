# Simplified Decision Homepage Design

Date: 2026-04-14
Status: approved in conversation
Owner: Codex + David

## 1. Ausgangslage

Das aktuelle Produkt fuehlt sich wie ein Operator-Dashboard an:

- zu viele gleichrangige Hauptbereiche
- zu viele Wiederholungen derselben Geschichte in verschiedenen Seiten
- zu viele Fachsignale auf einmal
- zu wenig klare Fuehrung zur eigentlichen Entscheidung

Der Nutzerwunsch ist deutlich:

> "Ich will einen schoenen Graph haben, der zeigt: so verlief das bisher und so wird es nach unseren Berechnungen in den naechsten sieben Tagen verlaufen, deshalb solltest du in Region XY Mediabudget schalten."

Das neue Produktziel ist deshalb nicht "mehr Analyse sichtbar machen", sondern:

- schneller verstehen
- schneller entscheiden
- nur bei Bedarf tiefer einsteigen

## 2. Zielbild

Die Startseite wird zu einer einzigen klaren Entscheidungsseite.

Sie beantwortet sofort vier Fragen:

1. Was ist die Empfehlung fuer diese Woche?
2. Wie verlief es bisher?
3. Wie sieht die Prognose fuer die naechsten 7 Tage aus?
4. Warum ist diese Empfehlung glaubwuerdig?

Die Seite soll nach 5 bis 10 Sekunden scanbar sein.

## 3. Nicht-Ziele

Diese Umstellung soll im ersten Schritt nicht:

- das gesamte Backend neu schreiben
- Forecast-, Regionen- oder Evidenzlogik verwerfen
- alle alten Detailinhalte sofort loeschen
- jede historische Route sofort technisch entfernen

Der erste Schritt veraendert vor allem die Produktfuehrung und die Oberflaeche.

## 4. Produktprinzipien

Die neue Seite folgt diesen Regeln:

- Eine Hauptseite, nicht sechs gleich wichtige Arbeitsbereiche.
- Eine Hauptantwort, nicht mehrere konkurrierende Teilantworten.
- Details bleiben verfuegbar, aber nur nachrangig.
- Sprache bleibt klar, aber niemals unehrlich.
- Das Produkt darf auch sagen: "Noch nicht sicher genug."

## 5. Informationsarchitektur

### 5.1 Hauptnavigation

Die bisherige Gleichrangigkeit von

- Virus-Radar
- Diese Woche
- Zeitgraph
- Regionen
- Kampagnen
- Evidenz

wird beendet.

Neue Regel:

- `/virus-radar` bleibt die zentrale Hauptseite.
- Die Inhalte aus `Diese Woche`, `Zeitgraph`, `Regionen`, `Kampagnen` und `Evidenz` werden in die Hauptseite eingebettet oder als nachrangige Details erreichbar gemacht.

Im ersten Umbau sollte die sichtbare Navigation stark reduziert werden.

Empfohlene sichtbare Top-Navigation:

- Entscheidung
- optional: Details

Wenn technisch einfacher, duerfen bestehende Routen vorerst weiter existieren, aber sie sollen nicht mehr als primaere Produktstruktur praesentiert werden.

### 5.2 Detailstruktur auf der Hauptseite

Die Hauptseite besteht aus genau vier Ebenen:

1. Hauptantwort
2. Zentraler Verlauf/Prognose-Graph
3. Drei Kernfakten
4. Aufklappbare Details

## 6. Zielaufbau der neuen Hauptseite

### 6.1 Hero-Antwort

Ganz oben steht die Entscheidung in Alltagssprache.

Beispiele:

- "Diese Woche Budget in Sachsen erhoehen."
- "Diese Woche Sachsen weiter beobachten, aber noch nicht hochfahren."
- "Aktuell keine belastbare regionale Budgetempfehlung."

Direkt darunter steht ein kurzer Erklaersatz mit 1 bis 2 Saetzen.

Beispiel:

- "Der Verlauf steigt seit mehreren Wochen, und die 7-Tage-Prognose zeigt weiter nach oben."

### 6.2 Zentraler Graph

Unter der Antwort steht der wichtigste Visualisierungsblock.

Er zeigt:

- links: historischer Verlauf
- rechts: Prognose fuer die naechsten 7 Tage
- klar unterscheidbar: gemessen vs prognostiziert

Der Graph ist die visuelle Hauptbegruendung der Entscheidung.

Er soll nicht wie ein Analysewerkzeug wirken, sondern wie ein Entscheidungsgraf:

- visuell ruhig
- klar beschriftet
- keine konkurrierenden Sekundaerdiagramme im oberen Bereich

### 6.3 Drei Kernfakten

Direkt unter dem Graphen folgen genau drei kompakte Faktenkarten:

- Region
- Trend/Richtung
- Vertrauen oder Belastbarkeit

Beispiel:

- Region: Sachsen
- Trend: steigend
- Vertrauen: mittel

Mehr als drei Kernkarten sollen im ersten sichtbaren Bereich vermieden werden.

### 6.4 Kurze Begruendung

Unter den Kernfakten steht eine sehr kurze alltagssprachliche Begruendung.

Ziel:

- kein Dashboard-Sprech
- keine Metrikflut
- keine Rechtfertigung ueber mehrere Bloecke

Stattdessen:

- "Sachsen zeigt aktuell die staerkste Dynamik. Andere Regionen bleiben eher stabil oder haben weniger belastbare Signale."

### 6.5 Aufklappbare Details

Alle tieferen Themen werden nach unten verschoben und standardmaessig eingeklappt.

Empfohlene Detailbereiche:

- Warum glauben wir das?
- Welche anderen Regionen wurden geprueft?
- Welche Risiken oder Blocker gibt es noch?
- Welche Evidenz liegt zugrunde?

Wichtig:

- Details bleiben vorhanden.
- Sie stehen aber nicht mehr im Weg der Hauptentscheidung.

## 7. Inhaltliche Zustandslogik

Die Seite muss in drei klaren Zustaenden sprechen koennen.

### 7.1 Klarer Go-Fall

Wenn Datenlage und Signale ausreichend stark sind:

- klare Handlungsempfehlung
- klare Zielregion
- klarer Aktionsbutton

Beispiel:

- "Diese Woche Budget in Sachsen erhoehen."

### 7.2 Beobachten-Fall

Wenn erste Signale da sind, aber die Freigabe noch nicht ehrlich vertretbar ist:

- klare Beobachten-Empfehlung
- keine aggressive Aktivierungsformulierung

Beispiel:

- "Diese Woche Sachsen beobachten, aber noch nicht hochfahren."

### 7.3 Kein belastbarer Fall

Wenn die Datenlage keine ehrliche regionale Handlung erlaubt:

- ausdruecklich keine kuenstliche Scheinsicherheit

Beispiel:

- "Aktuell keine belastbare regionale Budgetempfehlung."

Diese dritte Variante ist ein Produktmerkmal, kein Fehlerfall.

## 8. Verhalten der Handlungsbuttons

Es soll genau einen primaeren Call-to-Action geben.

Beispiele je nach Zustand:

- `Empfehlung pruefen`
- `Region genauer pruefen`
- `Evidenz ansehen`

Sekundaere Links oder Aktionen sollen reduziert und klar untergeordnet werden.

Der obere Bereich darf nicht drei fast gleich wichtige Buttons gleichzeitig anbieten.

## 9. Nutzung bestehender Daten und Komponenten

Der Umbau soll auf vorhandenen Datenquellen aufsetzen.

Wiederverwendung im ersten Schritt:

- vorhandene Daten aus `useNowPageData`
- vorhandene Daten aus `useRegionsPageData`
- vorhandene Daten aus Forecast- und Evidenz-View-Modellen
- vorhandene Forecast-/Backtest-Visualisierungen, sofern sie vereinfacht werden koennen

Wahrscheinliche Konsequenz:

- `VirusRadarPage` wird neu zusammengeschnitten
- Teile aus `NowWorkspace`, `TimegraphPage`, `RegionWorkbench` und Evidenzkomponenten werden in die neue Entscheidungsseite integriert
- bisherige Mehrfachdarstellungen derselben Signale werden entfernt

## 10. Was entfernt oder versteckt werden soll

Im ersten sichtbaren Bereich sollen nicht mehr gleichzeitig vorkommen:

- Kartenblock plus Aktivierungs-Queue plus Kampagnen-Reife plus Trend-Board plus Why-Now plus Decision-Risk
- mehrere gleichrangige Seitenaktionen
- mehrere fast gleich wichtige Navigationsziele
- wiederholte Erklaerungen derselben Empfehlung

Wenn diese Inhalte weiterhin fachlich noetig sind, sollen sie in eingeklappten Detailsektionen leben.

## 11. Migrationsstrategie

### Phase 1: UI-Fokus

- `Virus-Radar` zur einzigen echten Entscheidungsseite umbauen
- obere Navigation stark reduzieren
- sichtbaren Above-the-fold-Bereich auf Antwort + Graph + 3 Fakten + Begruendung reduzieren
- tiefe Inhalte nach unten in Details verschieben

### Phase 2: Struktur bereinigen

- alte Seiten auf neue Detailbereiche oder interne Ansichten zurueckfuehren
- doppelte Komponenten und doppelte Erklaerlogik entfernen
- veraltete Navigationspfade umleiten

### Phase 3: Aufraeumen

- ungenutzte Oberflaechen und tote UI-Pfade abbauen
- Tests und Copy finalisieren

## 12. Teststrategie

Es muessen mindestens folgende Nutzungsfaelle getestet werden:

- klarer Go-Fall zeigt deutliche Handlungsempfehlung
- Beobachten-Fall zeigt bewusst zurueckhaltende Sprache
- kein belastbarer Fall zeigt ehrliche Nicht-Empfehlung
- der zentrale Graph ist sichtbar und trennt Vergangenheit von 7-Tage-Prognose
- die Hauptseite zeigt nur wenige Kernfakten sichtbar
- Details sind standardmaessig nachrangig
- alte Einstiege leiten den Nutzer nicht mehr in das fruehere Mehr-Seiten-Labyrinth

## 13. Akzeptanzkriterien

Der Umbau ist erfolgreich, wenn:

- ein neuer Nutzer die Hauptaussage ohne Erklaerung versteht
- die Startseite in 5 bis 10 Sekunden scanbar ist
- die aktuelle Empfehlung, Region und Begruendung sofort sichtbar sind
- der historische Verlauf und die 7-Tage-Prognose zentral im Fokus stehen
- Detailwissen noch verfuegbar ist, aber nicht mehr den ersten Eindruck dominiert
- die Seite auch ehrlich "noch nicht sicher genug" sagen kann

## 14. Entscheidung

Freigegebene Richtung aus der Diskussion:

- Variante A
- radikale Vereinfachung
- eine Hauptseite
- eine Hauptantwort
- Details nur nachrangig
