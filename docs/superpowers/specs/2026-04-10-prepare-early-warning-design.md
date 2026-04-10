# Prepare Early Warning Design

## Goal

ViralFlux soll eine echte fruehe Warnstufe bekommen, die nuetzlich ist, auch wenn noch kein harter Ausbruch und keine Budgetfreigabe vorliegen.

Das neue `Prepare` soll sagen:

- Diese Region sieht frueh interessant aus
- Operative Vorbereitung lohnt sich
- Es wird noch kein Mediabudget freigegeben

## Problem Today

Im Live-Betrieb bleibt das Produkt fast immer bei `Watch`.

Die Ursachen sind kombiniert:

1. Das Business-Gate blockiert Budgetfreigabe, solange noch keine echte GELO-Truth-Validierung vorliegt.
2. Das Quality-Gate faellt aktuell knapp durch, weil `ece` knapp ueber der Schwelle liegt.
3. Die heutige `Prepare`-Logik ist fast genauso hart wie die Aktivierungslogik.
4. Die live gemessenen Event-Wahrscheinlichkeiten liegen in ruhigen Phasen oft nur bei etwa `0.001` bis `0.004`.

Das fuehrt dazu, dass `Prepare` als produktive Zwischenstufe fast keinen praktischen Wert hat.

## Product Decision

`Prepare` wird kuenftig als frueher interner Hinweis behandelt.

Das bedeutet:

- `Prepare` ist kein Budgetsignal
- `Prepare` ist kein kommerzielles Freigabesignal
- `Prepare` ist ein operativer Vorbereitungshinweis

Die Stufen sollen fachlich so verstanden werden:

- `Watch`: weiter beobachten, noch keine aktive Vorbereitung
- `Prepare`: fruehes Signal, intern vorbereiten, aber kein Budget
- `Activate`: starkes Signal, mit Budget nur wenn Business- und Quality-Gates offen sind

## Non-Goals

Dieses Vorhaben soll ausdruecklich nicht:

- `Activate` lockerer machen
- das Business-Gate aushebeln
- das Quality-Gate aushebeln
- kuenstlich Budget freigeben, obwohl Truth-Validierung fehlt
- das Event-Training oder die Event-Label-Definition in dieser Runde neu bauen

## Recommended Approach

Es wird eine neue fruehe `Prepare`-Regel eingefuehrt, die nicht an der heutigen harten Event-Wahrscheinlichkeit haengt.

`Activate` bleibt wie heute streng.

Die neue fruehe `Prepare`-Stufe soll auf Fruehsignal-Merkmalen beruhen:

- positiver oder beschleunigter Trend
- frische Daten
- brauchbare Forecast-Confidence
- ordentlicher Decision-Score
- mindestens etwas Unterstuetzung durch Quellen oder Nebensignale

Die vorhandene harte `Prepare`-Stufe wird nicht einfach ein wenig gelockert. Stattdessen kommt eine eigene, schwachere Fruehwarnlogik dazu.

## Rule Shape

Die neue `Prepare`-Stufe soll erreicht werden, wenn eine Region ein konsistentes Fruehsignal zeigt, auch wenn die Event-Wahrscheinlichkeit noch weit unter der Aktivierungsschwelle liegt.

Geplante Logik:

1. `Activate` wird zuerst wie heute berechnet.
2. Wenn `Activate` nicht erreicht ist, wird die neue fruehe `Prepare`-Regel geprueft.
3. Diese Regel bewertet Fruehsignal-Kriterien statt harter Aktivierungskriterien.
4. Wenn die Fruehsignal-Regel greift, wird die Region als `Prepare` markiert.
5. Budget bleibt trotzdem `0`, solange die harten Freigabebedingungen nicht erfuellt sind.

Die fruehe `Prepare`-Regel soll absichtlich konservativ genug sein, damit nicht jede kleine Schwankung als Vorbereitungssignal endet.

## Operational Semantics

Wenn eine Region `Prepare` bekommt, soll das Produkt konkret Folgendes meinen:

- Das Team sollte die Region enger beobachten
- Kreative oder Botschaften koennen vorbereitet werden
- Keywords, Zielgruppen oder regionale Varianten koennen geprueft werden
- Es wird noch keine bezahlte Aktivierung empfohlen

Die Produkttexte sollen das klar sagen, damit kein Nutzer `Prepare` mit einer Budgetfreigabe verwechselt.

## API And Output Changes

Die bestehende Stufenlogik bleibt erhalten, aber `Prepare` bekommt eine neue Bedeutung.

Der Output soll deshalb klar transportieren:

- `decision.stage = prepare`
- Budgetempfehlung bleibt `0`, wenn das Business-Gate nicht offen ist
- Begruendung nennt ausdruecklich, dass es sich um ein Fruehsignal handelt
- Next Steps nennen Vorbereitung statt Ausspielung

Die vorhandenen Antwortstrukturen sollen moeglichst erhalten bleiben. Die Aenderung soll primar in Regelwerk, Begruendung und operativer Semantik stattfinden.

## UX Expectations

Im Produkt soll `Prepare` sichtbar wertvoller sein als `Watch`, aber deutlich schwacher als `Activate`.

Das UI soll fuer `Prepare` sinngemaess erklaeren:

- Warum die Region auffaellt
- Warum noch kein Budget freigegeben wird
- Was jetzt vorbereitet werden kann

Wichtig ist, dass `Prepare` nicht wie ein verstecktes `Activate` aussieht.

## Safety Constraints

Die neue Logik muss diese Grenzen einhalten:

- Kein Budget nur wegen `Prepare`
- Kein Umgehen des Business-Gates
- Kein Umgehen des Quality-Gates fuer echte Aktivierung
- Keine Aenderung an der Bedeutung von `Activate`
- Keine stillen Semantikwechsel ohne klare Begruendung im Output

## Testing Strategy

Die Umsetzung soll mit direkten Vertrags- und Guard-Tests abgesichert werden.

Mindestens noetig sind:

- Tests fuer die neue fruehe `Prepare`-Regel
- Tests dafuer, dass `Prepare` kein Budget freigibt
- Tests dafuer, dass `Activate` unveraendert streng bleibt
- Tests fuer die Begruendungen und Next Steps
- mindestens ein Integrationspfad fuer Forecast, Media Allocation und Campaign Recommendations

## Expected Outcome

Nach der Umsetzung soll ViralFlux in ruhigen oder fruehen Signalphasen nicht mehr nur stumpf `Watch` ausgeben.

Stattdessen soll das Produkt frueher nuetzliche operative Hinweise geben:

- welche Regionen frueh interessant werden
- warum sie auffallen
- was vorbereitet werden kann

Gleichzeitig bleibt die harte Budget- und Aktivierungslogik sauber geschuetzt.
