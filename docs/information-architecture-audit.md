# Informationsarchitektur Audit

## Ziel

Diese Matrix beschreibt fuer die aktiven Live-Seiten:

- welches Element welche Frage beantwortet
- welche Funktion es im Ablauf hat
- was passieren wuerde, wenn es fehlt
- ob es behalten, vereinfacht, verschoben, entfernt oder neu ergaenzt werden soll

## Hauptfluss

`Login -> /jetzt -> /regionen -> /kampagnen -> /evidenz`

## Live-Seiten

| Seite | Element | Beantwortete Frage | Funktion | Wenn es fehlt | Entscheidung |
| --- | --- | --- | --- | --- | --- |
| `/jetzt` | Proof-Graph "Verlauf der Welle" | Warum hat ViralFlux hier einen echten Vorteil? | Sichtbarer Beweis fuer zeitlichen Vorsprung | Die Seite wirkt wie eine Behauptung ohne klaren Beleg | Neu ergaenzt |
| `/jetzt` | Hauptentscheidung | Was tun wir jetzt? | Leitet aus dem Verlauf den naechsten Schritt ab | Der Nutzer sieht Daten, aber keine klare Handlung | Behalten |
| `/jetzt` | Vertrauensblock "Wie sicher ist das?" | Kann ich der Entscheidung trauen? | Kompakter Sicherheitscheck | Die Entscheidung wirkt zu hart oder zu unsicher | Behalten |
| `/jetzt` | Als Naechstes pruefen | Wohin gehe ich nach dem ersten Blick? | Bruecke zu Regionenarbeit | Der Fluss endet nach dem ersten Lesen | Behalten |
| `/jetzt` | Was wir noch pruefen | Was bremst noch? | Zeigt Restunsicherheit ohne den Fokus zu zerstoeren | Offene Risiken verschwinden aus dem Blick | Vereinfachen |
| `/jetzt` | Weitere Details | Was ist fuer den zweiten Blick relevant? | Lagert Tiefeninfos nach unten aus | Die Seite wird oben zu dicht | Behalten |
| `/regionen` | Fokusregion | Welche Region ist zuerst wichtig? | Verdichtet die Regionsauswahl auf einen klaren Fall | Die Kartenansicht bleibt zu abstrakt | Behalten |
| `/regionen` | Karte | Wo sehe ich die Alternativen? | Ermoeglicht Auswahl und Orientierung | Regionenvergleich wird unklar | Behalten |
| `/regionen` | Warum diese Region | Warum genau diese Region? | Erklaert Treiber und Kontext | Region wirkt willkuerlich | Behalten |
| `/regionen` | Weitere Regionen | Was kommt nach der Fokusregion? | Haltet die Arbeit in Bewegung | Nach Auswahl einer Region endet der Pfad | Behalten |
| `/regionen` | Treiber und Rohdetails | Welche Details stuetzen die Wahl? | Zweite Ebene fuer spaeteres Nachpruefen | Details fehlen im Zweifel | Vereinfachen |
| `/kampagnen` | Fokusfall | Welchen konkreten Fall pruefen wir zuerst? | Macht aus vielen Vorschlaegen genau eine klare Startarbeit | Der Nutzer steht vor einer Liste statt vor einer Aufgabe | Behalten |
| `/kampagnen` | Phasen-Spalten | Wo steckt die Arbeit gerade? | Ordnet Faelle in Vorbereitung, Freigabe und Aktiv | Der Status der Arbeit wird unklar | Behalten |
| `/kampagnen` | Weitere Vorschlaege erstellen | Wie entstehen neue Entwuerfe? | Erzeugung bleibt bewusst nachgeordnet | Das Team erzeugt zu frueh neue Faelle | Behalten |
| `/kampagnen` | Arbeitskontext | Wie ordne ich die Vorschlaege ein? | Zeigt Virus, Lernstand und Zusatzkontext | Vorschlaege wirken losgeloest | Vereinfachen |
| `/evidenz` | Vier schnelle Fragen | Ist die Vorhersage belastbar? | Verdichtet die Vertrauenspruefung | Die Evidenzseite startet zu technisch | Behalten |
| `/evidenz` | Offene Punkte | Was blockiert noch? | Macht Risiken zuerst sichtbar | Risiken werden uebersehen | Behalten |
| `/evidenz` | 4 Pruefbereiche | Wo genau liegt ein Problem? | Struktur fuer Forecast, Kundendaten, Quellen, Import | Tiefenpruefung wird unsystematisch | Behalten |
| `/evidenz` | Technischer Blick | Welche Rohhinweise brauche ich bei Bedarf? | Reserve fuer tiefere Analyse | Technische Spur fehlt im Problemfall | Behalten |
| `/welcome` | Hero + Nutzenversprechen | Was ist ViralFlux? | Einstieg fuer Aussenblick und Produktkontext | Die App startet kalt ohne Produktverstaendnis | Behalten |
| `/welcome` | Deutschland-Vorschau | Was zeigt das System grundsaetzlich? | Leichte Vorschau auf Wochenlage | Der Einstieg bleibt zu abstrakt | Behalten |
| `/welcome` | CTA zur Arbeitsansicht | Wie komme ich in die eigentliche Arbeit? | Fuehrt in den Hauptfluss | Welcome bleibt Sackgasse | Behalten |

## Doppelte oder alte Flaechen

| Flaeche | Beobachtung | Rolle | Entscheidung |
| --- | --- | --- | --- |
| `DecisionPage` / `DecisionView` | Enthalten den vorhandenen Verlaufsgrafen und weitere Logik, sind aber nicht im Live-Hauptpfad | Quellflaeche fuer die Proof-Integration | Inhalt uebernehmen, danach bereinigen |
| `OperationalDashboardPage` / `OperationalDashboard` | Aeltere alternative Darstellung der Wochenlage | Historischer Zwischenstand | Spaeter archivieren oder loeschen |
| `PilotPage` / `PilotSurface` | Eigene Analyseflaeche ausserhalb des Live-Hauptpfads | Spezial- oder Altansicht | Vorerst ausser Hauptmodell halten |
| `MediaCockpit` / `WeeklyReport` | Nicht Teil der aktiven Hauptrouten | Altbestand | Spaeter getrennt bewerten |

## Bewertungsregeln

- `Behalten`: Das Element beantwortet eine klare Nutzerfrage und traegt direkt zum naechsten Schritt bei.
- `Vereinfachen`: Die Funktion ist richtig, aber die Darstellung ist zu lang, doppelt oder zu tief.
- `Verschieben`: Das Element ist wichtig, sitzt aber auf der falschen Hoehe im Ablauf.
- `Entfernen`: Das Element beantwortet keine klare Nutzerfrage mehr.
- `Neu ergaenzen`: Eine wichtige Nutzerfrage bleibt aktuell unbeantwortet.
