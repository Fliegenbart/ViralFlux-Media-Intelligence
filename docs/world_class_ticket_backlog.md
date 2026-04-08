# World-Class Ticket Backlog

Basis für dieses Ticket-Set:
- [technical_audit_current_state.md](/Users/davidwegener/Desktop/viralflux/docs/technical_audit_current_state.md)
- [fluxengine_technical_audit_2026-03-10.md](/Users/davidwegener/Desktop/viralflux/docs/fluxengine_technical_audit_2026-03-10.md)
- [information-architecture-audit.md](/Users/davidwegener/Desktop/viralflux/docs/information-architecture-audit.md)
- [forecast_world_class_plan.md](/Users/davidwegener/Desktop/viralflux/docs/forecast_world_class_plan.md)
- [media_allocation_engine_v1.md](/Users/davidwegener/Desktop/viralflux/docs/media_allocation_engine_v1.md)
- [live_readiness_blockers_current.md](/Users/davidwegener/Desktop/viralflux/docs/live_readiness_blockers_current.md)

Stand: 2026-03-24

## Zielbild

Dieses Ticket-Set beantwortet eine einfache Frage:

Was muss noch passieren, damit ViralFlux nicht nur interessant wirkt, sondern wirklich weltklasse, leicht bedienbar und mathematisch belastbar wird?

Weltklasse bedeutet hier:

- der Nutzer versteht in kurzer Zeit, was passiert und was als Nächstes zu tun ist
- jede Zahl hat eine ehrliche Bedeutung
- Budget- und Aktivierungsempfehlungen sind nicht nur regelbasiert, sondern auf echte Ergebnisse rueckfuehrbar
- das System lässt sich operativ stabil betreiben

## Leitprinzipien

- Keine neue UI-Flaeche bauen, solange der Hauptfluss noch doppelt oder unklar ist.
- Keine Zahl als `Probability` oder `Confidence` benennen, wenn sie das mathematisch nicht wirklich ist.
- Keine "intelligente" Budgetlogik aufhaengen, bevor Outcome- und Lift-Daten sauber angeschlossen sind.
- Erst Ehrlichkeit und Klarheit, dann mehr Komplexitaet.

## Die 5 Phasen

1. Produktfluss vereinfachen
2. Output-Semantik und mathematische Ehrlichkeit sauberziehen
3. Outcome- und Lift-Layer produktiv machen
4. Budgetlogik von Heuristik zu lernender Entscheidung weiterentwickeln
5. Operativen Betrieb haerten

## Phase 1 - Produktfluss vereinfachen

### Ticket VF-WC-01

- ticket id: `VF-WC-01`
- title: `Hauptfluss auf genau vier Nutzerfragen zuschneiden`
- category: `product UX`
- priority: `P0`
- suggested owner role: `product` mit `frontend`
- why it matters:
  Im Moment gibt es einen besseren Live-Hauptfluss, aber im Repo liegen noch aeltere oder doppelte Flaechen. Das erzeugt Reibung im Produktdenken und später oft auch im UI.
- exact root cause:
  Das Repo beschreibt selbst doppelte oder alte Flaechen ausserhalb des Live-Hauptpfads. Dadurch ist noch nicht hart genug entschieden, welche Seite welche Frage beantwortet.
- smallest corrective action:
  Für `/jetzt`, `/regionen`, `/kampagnen`, `/evidenz` je eine Hauptfrage festschreiben und alle Inhalte daran messen.
- acceptance criteria:
  - jede der vier Seiten hat eine klar benannte Hauptfrage
  - jedes Hauptelement auf der Seite beantwortet diese Frage
  - doppelte alte Entscheidungsflaechen sind als Quelle, Archiv oder Rueckbau markiert

### Ticket VF-WC-02

- ticket id: `VF-WC-02`
- title: `Trust-Block auf /jetzt vereinheitlichen`
- category: `product UX`
- priority: `P0`
- suggested owner role: `frontend` mit `product`
- why it matters:
  Nutzer müssen sofort sehen, ob das System nur eine starke Vermutung hat oder ob eine echte Freigabe möglich ist.
- exact root cause:
  Vertrauen, Datenfrische, Forecast-Qualitaet und Business-Gate sind über mehrere Bereiche verteilt. Dadurch fuehlt sich das Produkt schwer lesbar an.
- smallest corrective action:
  Einen festen Vertrauensblock auf `/jetzt` einbauen mit genau drei Ampeln:
  - Forecast belastbar?
  - Daten frisch?
  - Business-Freigabe bereit?
- acceptance criteria:
  - `/jetzt` zeigt einen kompakten Vertrauensblock oberhalb oder direkt neben der Hauptentscheidung
  - jede Ampel hat einen klaren Kurztext in einfacher Sprache
  - der Nutzer kann ohne Evidenzseite erkennen, ob nur Beobachtung oder schon Budgetfreigabe sinnvoll ist

### Ticket VF-WC-03

- ticket id: `VF-WC-03`
- title: `Ein-Button-Logik pro Hauptseite durchsetzen`
- category: `product UX`
- priority: `P1`
- suggested owner role: `frontend`
- why it matters:
  Wenn drei Buttons gleichzeitig gleich wichtig aussehen, weiss ein Nutzer oft nicht, was wirklich als Nächstes kommt.
- exact root cause:
  Mehrere Seiten haben noch mehrere starke Anschlussaktionen statt eines klaren primaren nächsten Schritts.
- smallest corrective action:
  Pro Hauptseite genau einen primaeren CTA festlegen. Weitere Aktionen werden sichtbar, aber schwacher gewichtet.
- acceptance criteria:
  - jede Hauptseite hat genau einen primaeren CTA
  - sekundare Aktionen sind visuell klar nachgeordnet
  - ein neuer Nutzer kann in einem kurzen Test den nächsten Schritt korrekt benennen

### Ticket VF-WC-04

- ticket id: `VF-WC-04`
- title: `Einfache Produktsprache als feste Regel einziehen`
- category: `product UX`
- priority: `P1`
- suggested owner role: `product`
- why it matters:
  Das Tool richtet sich nicht nur an Modellbauer. Wenn Begriffe technisch klingen, fuehlt sich selbst gute Logik komplizierter an als sie ist.
- exact root cause:
  Teile der Sprache kommen aus Modell-, Audit- oder Ops-Denken und nicht aus einer einfachen Operator-Sicht.
- smallest corrective action:
  Eine kleine Copy-Regel definieren:
  - kurze Saetze
  - erst Wirkung, dann Modellbegriff
  - keine mathematischen Begriffe ohne Klartext
- acceptance criteria:
  - zentrale UI-Texte folgen einer dokumentierten Copy-Regel
  - `Probability`, `Confidence`, `Quality Gate`, `Fallback` sind in Alltagssprache erklaert
  - neue Texte können gegen eine kurze Checkliste geprüft werden

## Phase 2 - Output-Semantik und mathematische Ehrlichkeit

### Ticket VF-WC-05

- ticket id: `VF-WC-05`
- title: `Kanonischen Forecast- und Decision-Vertrag definieren`
- category: `math contract`
- priority: `P0`
- suggested owner role: `ml`
- why it matters:
  Weltklasse bedeutet, dass jedes Feld genau eine saubere Bedeutung hat. Sonst sehen zwei Zahlen gleich aus, meinen aber etwas anderes.
- exact root cause:
  Der Forecast-Kern ist relativ stark, aber in späteren Layers werden Score, Probability, Confidence und Readiness noch nicht überall hart genug getrennt.
- smallest corrective action:
  Ein zentrales Contract-Dokument und passende Response-Felder definieren für:
  - `score`
  - `event_probability`
  - `confidence`
  - `readiness`
  - `fallback_used`
  - `probability_source`
- acceptance criteria:
  - jedes genannte Feld hat eine feste Definition
  - keine zwei Felder teilen dieselbe Semantik unter anderem Namen
  - API-Responses können klar als Ranking, Wahrscheinlichkeit oder Policy-Gate eingeordnet werden

### Ticket VF-WC-06

- ticket id: `VF-WC-06`
- title: `Pseudo-Probabilities und Pseudo-Confidence aus der UI entfernen oder umbenennen`
- category: `math honesty`
- priority: `P0`
- suggested owner role: `ml` mit `frontend`
- why it matters:
  Eine Zahl, die wie eine Wahrscheinlichkeit aussieht, aber nur ein Ranking ist, schadet später dem Vertrauen viel mehr als eine ehrlich benannte Kennzahl.
- exact root cause:
  Das Repo benennt selbst mehrere Werte als heuristisch oder nicht belastbar, obwohl sie für Nutzer nach harten Wahrscheinlichkeiten klingen.
- smallest corrective action:
  Alle betroffenen Felder inventarisieren und dann je Feld entscheiden:
  - sauber kalibrieren
  - in `score` umbenennen
  - aus der Hauptansicht entfernen
- acceptance criteria:
  - es gibt keine Nutzerflaeche mehr, in der eine unkalibrierte Kennzahl als Probability erscheint
  - `confidence` ist entweder empirisch begründet oder klar als heuristische Sicherheit bezeichnet
  - ein Feldkatalog dokumentiert den finalen Status je Kennzahl

### Ticket VF-WC-07

- ticket id: `VF-WC-07`
- title: `Fallback-Verhalten für Event-Probability ehrlich und sichtbar machen`
- category: `math honesty`
- priority: `P1`
- suggested owner role: `ml`
- why it matters:
  Ein Fallback kann sinnvoll sein. Gefährlich wird er erst dann, wenn niemand merkt, dass er gerade aktiv ist.
- exact root cause:
  Teile des Decision-Pfads können auf heuristische Ersatzlogik zurückfallen.
- smallest corrective action:
  Fallbacks als normalen Teil des Vertrags behandeln:
  - wann aktiv
  - warum aktiv
  - was das für die Aussagekraft bedeutet
- acceptance criteria:
  - jede Event-Probability traegt `probability_source` und `fallback_used`
  - UI und API können Fallback klar ausweisen
  - bei kritischen Freigaben wird Fallback nicht stillschweigend wie ein vollwertiges Modell behandelt

### Ticket VF-WC-08

- ticket id: `VF-WC-08`
- title: `Champion-Challenger-Betrieb mit echten Benchmark-Grenzen fertigziehen`
- category: `forecast quality`
- priority: `P1`
- suggested owner role: `ml`
- why it matters:
  Weltklasse-Modelle bleiben nicht gut, weil man sie einmal trainiert. Sie bleiben gut, weil neue Kandidaten nur über echte Benchmark-Evidenz live gehen.
- exact root cause:
  Der neue Benchmark-Rahmen ist angelegt, aber operative Befüllung und Live-Entscheidung sind noch nicht komplett durchgezogen.
- smallest corrective action:
  Für jeden Virus/Horizon-Scope feste Promotionsregeln definieren und reale Backtests in die Registry schreiben.
- acceptance criteria:
  - Champion und Challenger sind pro Scope sichtbar
  - Promotion basiert auf echten Benchmark-Ergebnissen statt auf impliziter Handentscheidung
  - ein schlechterer Challenger kann nicht versehentlich live werden

### Ticket VF-WC-09

- ticket id: `VF-WC-09`
- title: `Regionale Forecasts und operative Snapshots dauerhaft speichern`
- category: `ops foundation`
- priority: `P1`
- suggested owner role: `backend`
- why it matters:
  Solange der Live-Pfad stark an Artefakten auf Platte haengt, ist das System schwieriger zu prüfen, zu vergleichen und später zu debuggen.
- exact root cause:
  Der aktuelle regionale Produktionspfad liest stark aus Artefakten und hat noch keine voll ausgebaute Forecast-Persistenz im Datenbankschema.
- smallest corrective action:
  Eine DB-native Persistenz für regionale Forecast-Ausgaben und zugehörige Snapshot-Metadaten einfuehren.
- acceptance criteria:
  - regionale Live-Forecasts können historisch aus der Datenbank nachvollzogen werden
  - für jede Ausgabe sind Modellversion, Horizon, As-of-Date und Qualitaetsmetadaten gespeichert
  - Ops und Evidenzflaechen müssen nicht mehr primaer aus Dateiartefakten erklaert werden

## Phase 3 - Outcome- und Lift-Layer produktiv machen

### Ticket VF-WC-10

- ticket id: `VF-WC-10`
- title: `Outcome-Connector produktiv anschliessen`
- category: `business truth`
- priority: `P0`
- suggested owner role: `data partner` mit `backend`
- why it matters:
  Ohne echte Outcomes bleibt ViralFlux vor allem ein starkes Radar. Mit Outcomes wird daraus ein belastbares Entscheidungssystem.
- exact root cause:
  Der kommerzielle Gate-Teil ist aktuell noch durch fehlende echte Outcome-Daten blockiert.
- smallest corrective action:
  Wiederkehrenden produktiven Import für Spend, Sales, Orders, Revenue, Aktivierungen und Regionen anschliessen.
- acceptance criteria:
  - erste produktive Outcome-Batches laufen stabil
  - Coverage-Weeks wachsen im System sichtbar an
  - Business-Gate nutzt echte Daten statt leeren Platzhaltern

### Ticket VF-WC-11

- ticket id: `VF-WC-11`
- title: `Aktivierungszyklen, Holdouts und Lift-Felder vertraglich festziehen`
- category: `business truth`
- priority: `P0`
- suggested owner role: `product` mit `backend` und `data partner`
- why it matters:
  Echte Wirkung kann man nur messen, wenn klar ist, wann aktiviert wurde und was die Vergleichsgruppe war.
- exact root cause:
  Der Business-Layer verlangt diese Felder logisch bereits, aber ohne verbindlichen Datenvertrag bleibt Commercial GO unerreichbar.
- smallest corrective action:
  Outcome-Contract so erweitern, dass Aktivierungszyklen, Holdout-Gruppen und Lift-relevante Felder verpflichtend und klar beschrieben sind.
- acceptance criteria:
  - Outcome-Datenvertrag nennt Aktivierungs-, Kontroll- und Lift-Felder explizit
  - mindestens zwei Aktivierungszyklen können im System unterschieden werden
  - Holdout-Information ist technisch auswertbar

### Ticket VF-WC-12

- ticket id: `VF-WC-12`
- title: `Erstes echtes Lift-Modell für expected units und expected revenue bauen`
- category: `business math`
- priority: `P1`
- suggested owner role: `ml`
- why it matters:
  Solange `expected_units_lift` und `expected_revenue_lift` leer bleiben, endet die mathematische Geschichte zu früh.
- exact root cause:
  Das Repo hat die Felder und die Idee, aber noch kein produktives Modell für diesen Layer.
- smallest corrective action:
  Ein erstes konservatives Outcome-Modell bauen, das für freigegebene Scopes erwarteten Mehrwert plus Unsicherheitsbereich schaetzt.
- acceptance criteria:
  - `expected_units_lift` und `expected_revenue_lift` sind für geeignete Scopes nicht mehr `None`
  - das Modell liefert einen Unsicherheitsbereich
  - UI und API sagen klar, wann Lift belastbar ist und wann noch nicht

## Phase 4 - Budgetlogik von Heuristik zu lernender Entscheidung

### Ticket VF-WC-13

- ticket id: `VF-WC-13`
- title: `Heuristische Budget-Engine in Shadow-Mode gegen lernenden Challenger antreten lassen`
- category: `allocation`
- priority: `P1`
- suggested owner role: `ml`
- why it matters:
  Die aktuelle Budgetlogik ist als erste Version okay. Weltklasse wird sie aber erst, wenn sie gegen echte Outcomes und Alternativen getestet wird.
- exact root cause:
  Die vorhandene Allokation ist bewusst heuristisch und nicht als echter Mehrwert-Optimierer gebaut.
- smallest corrective action:
  Einen Challenger bauen, der Budgetvorschlaege aus erwartetem Lift, Risiko und Restriktionen ableitet, aber zuerst nur im Shadow-Mode mitläuft.
- acceptance criteria:
  - heuristische und lernende Budgetempfehlung können parallel verglichen werden
  - Unterschiede werden pro Region und Produkt erklaert
  - Live-Freigabe erfolgt erst nach nachgewiesenem Mehrwert

### Ticket VF-WC-14

- ticket id: `VF-WC-14`
- title: `Budgetempfehlungen mit Gegenbegründung erklaeren`
- category: `allocation UX`
- priority: `P2`
- suggested owner role: `frontend` mit `ml`
- why it matters:
  Nutzer vertrauen Budgetentscheidungen mehr, wenn sie sehen, warum Region A mehr bekommt als Region B.
- exact root cause:
  Selbst gute Modelle wirken sonst wie eine Blackbox.
- smallest corrective action:
  Zu jeder Budgetempfehlung eine kurze Erklaerung mit Gegenbeispiel anzeigen:
  - warum diese Region hoch priorisiert ist
  - warum andere Regionen nachgeordnet sind
- acceptance criteria:
  - Budgetkarten enthalten eine kurze, nachvollziehbare Begründung
  - mindestens ein Negativgrund wird genannt, wenn Budget nicht freigegeben wird
  - Budgetentscheidungen können in Alltagssprache weitergegeben werden

## Phase 5 - Operativen Betrieb haerten

### Ticket VF-WC-15

- ticket id: `VF-WC-15`
- title: `Python- und Test-Umgebung auf einen klaren Standard bringen`
- category: `developer experience`
- priority: `P1`
- suggested owner role: `backend`
- why it matters:
  Wenn schon lokal unklar ist, welche Python-Version oder welche Abhaengigkeiten erwartet werden, wird jede Weiterentwicklung langsamer und fehleranfaelliger.
- exact root cause:
  Teile des Codes brauchen klar Python 3.11+, waehrend lokale Aufrufe sonst schnell mit einer aelteren Version laufen.
- smallest corrective action:
  Einen klaren Standard für lokale Entwicklung und CI festziehen.
- acceptance criteria:
  - dokumentierter Python-Standard ist 3.11+
  - schneller Setup-Pfad für neue Entwickler ist dokumentiert
  - wichtige Test-Suites laufen reproduzierbar mit derselben Runtime

### Ticket VF-WC-16

- ticket id: `VF-WC-16`
- title: `Readiness in drei Ebenen trennen: Modell, Daten, Business`
- category: `ops clarity`
- priority: `P1`
- suggested owner role: `backend` mit `product`
- why it matters:
  Heute kann ein Scope fachlich gut sein, aber wegen Datenfrische oder fehlender Commercial Truth trotzdem auf `WATCH` wirken. Das ist für Nutzer oft schwer zu verstehen.
- exact root cause:
  Mehrere Arten von "nicht bereit" liegen nahe beieinander, obwohl sie unterschiedliche Dinge bedeuten.
- smallest corrective action:
  Readiness systematisch in drei Ebenen trennen und in API und UI separat ausgeben.
- acceptance criteria:
  - jede Scope-Sicht trennt Modell-Readiness, Daten-Readiness und Business-Readiness
  - ein Forecast-First-GO kann klar von Commercial-GO unterschieden werden
  - Warnungen werden dem richtigen Layer zugeordnet

### Ticket VF-WC-17

- ticket id: `VF-WC-17`
- title: `Modell-Release-Prozess als festen operativen Pfad durchziehen`
- category: `ml ops`
- priority: `P2`
- suggested owner role: `ml`
- why it matters:
  Weltklasse entsteht nicht nur durch gute Modelle, sondern durch einen Release-Prozess, der saubere Wechsel und schnelle Rueckverfolgbarkeit erlaubt.
- exact root cause:
  Governance-Teile sind angelegt, aber noch nicht als vollstaendig harter Alltagsprozess sichtbar.
- smallest corrective action:
  Training, Benchmarking, Promotion, Rollback und Smoke-Check als festen Ablauf dokumentieren und automatisieren.
- acceptance criteria:
  - jeder Modellwechsel hinterlässt eine nachvollziehbare Spur
  - Rollback ist definiert
  - Smoke-Checks vor und nach Promotion sind Teil des Standardablaufs

## Empfohlene Reihenfolge

1. `VF-WC-01`
   Erst den Produktfluss festziehen, damit wir nicht auf ein verwirrendes Bedienmodell optimieren.

2. `VF-WC-02`
   Dann Vertrauen sichtbar machen. Das bringt sofort mehr Klarheit für Nutzer.

3. `VF-WC-05`
   Danach die Feldbedeutungen hart definieren. Sonst bauen wir weiter auf uneinheitlicher Semantik.

4. `VF-WC-06`
   Alles Unehrliche bereinigen: umbenennen, kalibrieren oder rausnehmen.

5. `VF-WC-10`
   Outcome-Daten produktiv anschliessen. Das ist der größte Hebel für Business-Reife.

6. `VF-WC-11`
   Aktivierungs- und Holdout-Struktur sauber machen.

7. `VF-WC-12`
   Erstes Lift-Modell aufbauen.

8. `VF-WC-08`
   Champion-Challenger-Regime voll in den Alltag bringen.

9. `VF-WC-09`
   Persistenz und Nachvollziehbarkeit haerten.

10. `VF-WC-13`
    Lernende Budget-Engine zunächst im Shadow-Mode evaluieren.

11. `VF-WC-16`
    Readiness für Nutzer sauber entwirren.

12. `VF-WC-15` und `VF-WC-17`
    Entwicklungs- und Release-Prozess stabil machen.

## Was wir bewusst noch nicht tun sollten

- keine neue Score-Familie einfuehren, nur weil sie schlau klingt
- keine neue Budgetautomatik live schalten, bevor Outcome und Lift sauber da sind
- keine grossen UI-Ausbauten starten, bevor der Hauptfluss hart genug vereinfacht ist
- keine Nutzerflaeche mit "Confidence" ausstatten, wenn dahinter nur ein heuristischer Proxy steckt

## Kurzfazit

Der schnellste Weg zu "weltklasse" ist nicht:

- mehr Charts
- mehr Features
- mehr Modellnamen

Der schnellste Weg ist:

- erst Klarheit
- dann Ehrlichkeit
- dann echte Outcome-Lernschleifen
- dann lernende Budgetentscheidung
