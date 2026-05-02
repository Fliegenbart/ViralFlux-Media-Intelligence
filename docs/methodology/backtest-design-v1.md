# GELO Backtest Design v1

**Status:** Diskussionsgrundlage, keine finale Methodik.
**Ziel:** Prüfen, ob ein Media-Shift nach AMELAG-/FluxEngine-Signal historisch mit höherem GELO-Sales-Outcome verbunden gewesen wäre.
**Wichtig:** Ein hoher AMELAG-Wert plus hohe GELO-Sales in Hamburg ist noch kein Kausalbeweis. Beides kann durch Größe, Distribution, Basisnachfrage oder Media-Druck erklärt werden.

## 1. Was wir kontrollieren müssen

Der Backtest darf nicht Hamburg gegen Schleswig-Holstein lesen, als wären beide Regionen gleich. Wir brauchen ein Wochen-Panel pro `Produkt × Bundesland × Woche` und kontrollieren mindestens:

| Konfundierer | Warum er gefährlich ist | Mindestkontrolle |
| --- | --- | --- |
| Bevölkerung | Große Regionen haben fast immer mehr Abwasser-Signal und mehr Sales. | Sales pro Kopf oder `region fixed effects`; AMELAG nicht als absolutes Level allein verwenden. |
| Distribution | Wo GELO besser gelistet ist, werden mehr Packungen verkauft, egal ob die Welle steigt. | numerische/gewichtete Distribution, Out-of-stock, Apotheken-/Handelsabdeckung je Region/Woche. |
| Historischer Media-Spend | Media erhöht Nachfrage und wird oft dort geplant, wo Nachfrage ohnehin erwartet wird. | Spend, Impressions, Kanal, Kampagnen-ID; ideal mit Lag/Adstock, nicht nur Wochenbetrag. |
| Saisonalität | Erkältungsprodukte steigen im Winter auch ohne regionales Signal. | Kalenderwoche, Saison-Fixed-Effects, Feiertage/Ferien, nationale Woche-Fixed-Effects. |
| Wettereffekte | Kälte, Feuchte, Wetterwechsel können AMELAG und Sales gleichzeitig bewegen. | regionale Wetterfeatures pro Woche; mindestens Temperatur/Feuchte/Extremwechsel. |

Zusätzlich sinnvoll: Preis/Promo, Großhandels-Sell-in vs. POS-Sell-out, Lieferfähigkeit, nationale Kampagnen, Produktmix, Feiertage und Schulferien.

## 2. Methodenoptionen

### A. Within-region fixed effects

**Idee:** Wir vergleichen Hamburg mit Hamburg: Wie verändern sich Sales in derselben Region, wenn dort ein AMELAG-/FluxEngine-Signal kommt?

**Datenanforderung:** Wöchentliches Panel über alle 16 Bundesländer, mindestens Sales, Spend, Distribution, Preis/Promo, Wetter und Signal-Vintages. Besser 52+ Wochen, damit jede Region ruhige und aktive Phasen hat.

**Stärken:** Kontrolliert stabile regionale Unterschiede automatisch: Bevölkerung, historisch starke Distribution, regionale Basisnachfrage. Gut als erste Schutzschicht gegen den Hamburg-Effekt.

**Schwächen:** Reicht allein nicht für Kausalität. Wenn GELO Media genau dann hochfährt, wenn Nachfrage ohnehin steigt, bleibt ein zeitvariabler Konfundierer. Nationale Wellen und Kampagnen müssen extra kontrolliert werden.

**Einordnung:** Gute Basis, aber nicht der Endbeweis.

### B. Difference-in-differences gegen Kontrollregionen

**Idee:** Wir vergleichen die Veränderung in Signal-/Shift-Regionen mit ähnlichen Kontrollregionen ohne Shift. Nicht „Hamburg ist höher“, sondern „Hamburg steigt nach dem Signal stärker als vergleichbare Regionen im gleichen Zeitraum“.

**Datenanforderung:** Vorher-/Nachher-Fenster, klare Treatment-Definition, Kontrollregionen, identische Wochenabdeckung, echte Spend-/Outcome-Daten. Wichtig ist ein Pre-Trend-Check: Treatment und Kontrolle müssen vor dem Signal ähnlich laufen.

**Stärken:** Am besten anschlussfähig an die Business-Frage: Hat eine Shift-Entscheidung zusätzlich Sales bewegt? Mit Region- und Woche-Fixed-Effects kontrolliert sie stabile Regionsunterschiede und nationale Saisoneffekte.

**Schwächen:** Bricht, wenn Kontrollregionen nicht wirklich vergleichbar sind, wenn Spillover auftreten, oder wenn alle Regionen gleichzeitig Media bekommen. Bei nur 16 Bundesländern sind Konfidenzintervalle breit; Inferenz sollte mit Wild-Cluster-Bootstrap oder Randomization Inference validiert werden.

**Einordnung:** Für unsere Lage der robusteste Hauptansatz, wenn GELO historische Spend-/Sales-Daten und echte oder saubere „nicht geschiftete“ Kontrollregionen liefern kann.

### C. Synthetic Control Method

**Idee:** Für eine behandelte Region bauen wir aus anderen Regionen eine künstliche Vergleichsregion, die vor dem Signal möglichst ähnlich aussah.

**Datenanforderung:** Lange Vorhistorie, viele Pre-Signal-Wochen, stabile Donor-Regionen, kein gleichzeitiger Treatment-Schock im Donor-Pool.

**Stärken:** Sehr gut für einzelne auffällige Fälle, z. B. „Was wäre in Hamburg ohne Shift passiert?“. Liefert anschauliche Fallstudien.

**Schwächen:** Deutschland hat nur 15 mögliche Donor-Regionen pro behandelte Region. Bei nationalen Wellen oder breitem Media-Druck wird der Donor-Pool schnell kontaminiert. Für viele parallele Regionen weniger elegant.

**Einordnung:** Stark als Robustheitscheck und Story pro Region, nicht als alleiniger Hauptbeweis.

**Vorschlag für v1:** Difference-in-differences als Hauptmethode, immer mit Within-region fixed effects. Synthetic Control nur für 1-3 starke Einzelfälle als Zusatzcheck. Diese Festlegung bleibt offen, bis Szilárd/statistische Prüfung bestätigt, dass Datenlage und Pre-Trends reichen.

## 3. Mindestdaten, realistisch und ehrlich

Ohne echte Outcome- und Spend-Daten bleibt der Backtest ein Forecast-/Ranking-Test, kein Sales-Wirkungsnachweis.

**Mindestfelder pro Woche × Bundesland × Produkt:**

- `week_start`, `region_code`, `product`
- `sales_units` und/oder `revenue_eur`
- `media_spend_eur`, Kanal, Impressions oder GRP, Kampagnen-ID
- Distribution oder ein brauchbarer Proxy, plus Out-of-stock falls vorhanden
- Preis-/Promo-Signal
- AMELAG-/FluxEngine-Signal so, wie es damals verfügbar war, nicht nachträglich geglättet

**Mindestmenge nach Aussagekraft:**

| Datenlage | Was reicht statistisch ungefähr? | Was wir damit ehrlich sagen können |
| --- | --- | --- |
| Aktuell: 2 Sales-Zeilen | Reicht nicht. | Kein Sales-Lift, kein ROI, kein Kausalclaim. |
| Klein: 16 BL × 26 Wochen | Nur für große Effekte, grob >20-30 %, wenn Sales nach Kontrollen wenig rauschen. | Plausibilitätscheck, keine harte Pilot-Aussage. |
| Brauchbar: 16 BL × 52 Wochen | Für mittlere Effekte ca. 10-20 %, wenn Spend/Distribution/Promo sauber sind und es genug Signalwochen gibt. | Retrospektiver DiD-Backtest mit breiten Intervallen. |
| Stark: 16 BL × 104 Wochen oder mehrere Wellen | Für kleinere Effekte ca. 5-10 %, wenn Pre-Trends stabil sind und Kontrollen passen. | Belastbarere Business-Evidenz, aber noch kein Autopilot-Beweis. |
| Prospektiver Holdout: 6-12 Wochen, bewusst 8/8 oder ähnlich balanciert | Für ca. 10-15 % Lift eher realistisch; 5 % braucht längere Laufzeit oder feinere Regionen als Bundesland. | Sauberster Pilot-Claim mit Konfidenzintervall. |

Die genaue Mindest-Effektgröße hängt an der Reststreuung der Sales nach Kontrollen. Vor Code brauchen wir eine Power-/MDE-Rechnung auf echten GELO-Daten: Wie viel Prozent Sales-Lift könnten wir überhaupt erkennen?

## 4. Was wir am Ende ehrlich sagen können

**Sagbar, wenn Daten und Tests passen:**

- „In historischen Wochen mit vergleichbarem Pre-Trend lagen Regionen nach AMELAG-/FluxEngine-Signal und Media-Shift um X % über passenden Kontrollregionen.“
- „Das Konfidenzintervall reicht von A % bis B %; wenn es Null schneidet, sehen wir keinen belastbaren Effekt.“
- „Der Effekt ist bedingt auf Sales, Spend, Distribution, Promo, Saison und Wetter kontrolliert.“
- „Das ist ein kontrollierter Pilot-Backtest, kein Beweis für jede Region und jede Woche.“

**Nicht sagbar:**

- „AMELAG verursacht GELO-Sales.“
- „Hamburg verkauft mehr, weil Hamburg ein höheres AMELAG-Signal hat.“
- „Das Modell optimiert ROI automatisch.“
- „Jeder empfohlene Shift erzeugt sicher Mehrumsatz.“
- „Wir können aus zwei Sales-Zeilen einen Sales-Uplift ableiten.“

## Offene Fragen für Szilárd / Statistik

1. Ist DiD mit 16 Bundesland-Clustern inferenzseitig akzeptabel, und welche Bootstrap-/Randomization-Methode nehmen wir?
2. Welches Outcome ist primär: `log(sales_units)`, Umsatz, Sales pro Kopf oder residualisierte Sales?
3. Wie definieren wir Treatment: tatsächlicher Media-Shift, hypothetischer Signal-Shift oder beides getrennt?
4. Welches Lag-Fenster ist fachlich plausibel: Signalwoche, +1 Woche, +2 Wochen?
5. Wie modellieren wir Media Carryover/Adstock, ohne Overfitting zu bauen?
6. Welche Pre-Trend-Regel entscheidet, ob eine Kontrollregion zulässig ist?
7. Wie behandeln wir Hamburg-Ausreißer: ausschließen, winsorisieren oder nur über fixed effects/residualisierte Werte?
8. Ab welcher Mindest-Effektgröße ist der Backtest für GELO kommerziell relevant?
9. Reicht Bundesland-Ebene oder brauchen wir PLZ-/Gebietscluster, um 5-10 % Effekte sauber zu erkennen?

Bis diese Punkte geklärt sind, schreiben wir keinen Backtest-Code und verwenden keine ROI- oder Kausalclaims im Produkttext.
