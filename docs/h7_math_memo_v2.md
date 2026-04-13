# H7 Mathe-Memo v2

Stand: 2026-04-12

## Kurzurteil

Der H7-Stack ist deutlich sauberer als vorher, aber mathematisch noch nicht champion-reif.

Die wichtigste neue Klarheit nach dem frischen GPU-Rerun ist:

1. Der `Forecast-Kern` ist gegen `Climatology` klar besser.
2. Der `Forecast-Kern` ist gegen `Persistence` noch nicht besser.
3. Der separate `Event-Layer` ist bei `Influenza A / h7` und `Influenza B / h7` deutlich besser als `Persistence`.
4. `RSV A / h7` bleibt trotz einzelner Event-Signale wegen kollabierter Folds und schwachem Forecast-Kern kein Champion-Scope.

Das Problem ist also nicht nur Kalibrierung. Es bleibt ein Dreiklang aus:

- `Event-Label-Design`
- `Signalqualität vor Kalibrierung`
- `Kalibrierung`

## Frischer Evidenzstand

Die H7-Artefakte wurden am `2026-04-12` frisch neu gerechnet.

Damit sind die neuen Pflichtfelder jetzt wirklich in den produktiven `backtest.json`-Artefakten vorhanden, unter anderem:

- `forecast_baselines`
- `forecast_core_deltas`
- `event_benchmark_paths`
- `reliability_curve_bins`
- `brier_reliability`
- `brier_resolution`
- `brier_uncertainty`
- `fold_diagnostics`
- `fold_metric_deltas`
- `delta_ci_95`

Das Memo beschreibt deshalb nicht mehr nur einen Soll-Zustand im Code, sondern den jetzt tatsächlich geschriebenen Evidenzstand.

## Scope-Matrix

| Scope | Forecast-Kern vs Persistence | Event-Layer vs Persistence | Fold-Stabilität | Urteil |
| --- | --- | --- | --- | --- |
| `Influenza A / h7` | schlechter: `WIS 11.893865` vs `9.907523`, `CRPS 4.757546` vs `3.963009` | klar besser: `PR-AUC 0.769943` vs `0.318005`, `Brier 0.057636` vs `0.108583` | `1/5` Fold degeneriert | echter Event-Kandidat, aber Forecast-Kern noch nicht champion-reif |
| `Influenza B / h7` | schlechter: `WIS 11.721630` vs `9.927570`, `CRPS 4.688652` vs `3.971028` | klar besser: `PR-AUC 0.773415` vs `0.323534`, `Brier 0.065444` vs `0.114936` | `1/5` Fold degeneriert | ähnliches Bild wie Influenza A, aber noch ohne Forecast-Kern-Sieg |
| `RSV A / h7` | deutlich schlechter: `WIS 1.642180` vs `0.868976`, `CRPS 0.656872` vs `0.347591` | punktuell besser, aber auf instabiler Basis | `3/4` Folds problematisch | kein Champion-Scope, bleibt `WATCH / Shadow` |

## Vier Pflichtblöcke

### 1. Forecast-Kern `WIS / CRPS`

Der Forecast-Kern ist das Modell für die ganze Zielverteilung von `Y_(t+7)`, nicht nur für das Event.

Hier ist die aktuelle Lage klar:

#### Influenza A / h7

- Modell: `WIS 11.893865`, `CRPS 4.757546`
- Persistence: `WIS 9.907523`, `CRPS 3.963009`
- Delta gegen Persistence: `WIS -1.986342`, `CRPS -0.794537`
- Gegen Climatology dagegen klar besser: `WIS +35.326669`, `CRPS +7.047587`

#### Influenza B / h7

- Modell: `WIS 11.721630`, `CRPS 4.688652`
- Persistence: `WIS 9.927570`, `CRPS 3.971028`
- Delta gegen Persistence: `WIS -1.794060`, `CRPS -0.717624`
- Gegen Climatology klar besser: `WIS +35.596604`, `CRPS +7.140907`

#### RSV A / h7

- Modell: `WIS 1.642180`, `CRPS 0.656872`
- Persistence: `WIS 0.868976`, `CRPS 0.347591`
- Delta gegen Persistence: `WIS -0.773204`, `CRPS -0.309281`
- Gegen Climatology nur teilweise besser: `WIS +0.434633`, `CRPS -0.137669`

Kernaussage:

- Der Forecast-Unterbau ist nicht nutzlos.
- Aber er schlägt auf H7 im Moment noch nicht die starke naive Basis `Persistence`.
- Genau das verhindert heute einen ehrlichen Champion-Status.

### 2. Event-Qualität `PR-AUC / Brier / ECE`

Hier liegt der spannendste Fortschritt.

Der separate Event-Layer ist jetzt nicht mehr nur ein Bauchgefühl, sondern in den frischen Artefakten messbar stark.

#### Influenza A / h7

- Event-Modell: `PR-AUC 0.769943`, `Brier 0.057636`, `ECE 0.019538`, `precision@top3 0.772549`
- Persistence: `PR-AUC 0.318005`, `Brier 0.108583`, `ECE 0.031364`, `precision@top3 0.705882`
- 95%-CI für Delta gegen Persistence:
  - `PR-AUC`: `[0.408255, 0.498266]`
  - `Brier`: `[0.043309, 0.058918]`
  - `ECE`: `[-0.008444, 0.020235]`
  - `precision@top3`: `[0.004975, 0.099503]`

Lesart:

- Ranking und Brier-Güte sind robust besser als Persistence.
- `ECE` ist punktuell besser, aber das Intervall schneidet noch `0`.
- Also: echtes Signal, aber Kalibrierungsüberlegenheit noch nicht komplett “zugenagelt”.

#### Influenza B / h7

- Event-Modell: `PR-AUC 0.773415`, `Brier 0.065444`, `ECE 0.024734`, `precision@top3 0.790780`
- Persistence: `PR-AUC 0.323534`, `Brier 0.114936`, `ECE 0.038453`, `precision@top3 0.698582`
- 95%-CI für Delta gegen Persistence:
  - `PR-AUC`: `[0.406787, 0.492351]`
  - `Brier`: `[0.041552, 0.057590]`
  - `ECE`: `[-0.007055, 0.024460]`
  - `precision@top3`: `[0.022222, 0.113924]`

Lesart:

- Influenza B ist mit den frischen Artefakten nicht mehr fair als “nur Top-k-Spezialfall” zu beschreiben.
- Der Event-Layer ist gegen Persistence auch global stark.
- Aber derselbe Scope scheitert weiterhin am Forecast-Kern und an der Fold-Stabilität.

#### RSV A / h7

- Event-Modell: `PR-AUC 0.461107`, `Brier 0.033040`, `ECE 0.022808`, `precision@top3 0.438596`
- Persistence: `PR-AUC 0.132685`, `Brier 0.044304`, `ECE 0.079598`, `precision@top3 0.350877`
- 95%-CI für Delta gegen Persistence:
  - `PR-AUC`: `[0.194052, 0.479403]`
  - `Brier`: `[0.005022, 0.017608]`
  - `ECE`: `[0.039675, 0.069379]`
  - `precision@top3`: `[-0.071429, 0.233334]`

Lesart:

- Der Event-Layer sieht auf den Punktmetriken besser aus.
- Aber diese Scope-Evidenz ist nicht stabil genug, weil die Folds zu oft praktisch zusammenbrechen.
- Darum ist RSV A trotz positiver Punktmetriken noch kein ehrlicher Champion-Kandidat.

### 3. Fold-Stabilität und Identifizierbarkeit

Hier liegt weiterhin die größte wissenschaftliche Warnlampe.

#### Influenza A / h7

- Fold 0: `97` Positive, `15` Regionen
- Fold 1: `12` Positive, `7` Regionen
- Fold 2: `0` Positive, `0` Regionen, `degeneration_flag = true`
- Fold 3: `73` Positive, `16` Regionen
- Fold 4: `112` Positive, `14` Regionen

#### Influenza B / h7

- Fold 0: `107` Positive, `15` Regionen
- Fold 1: `34` Positive, `11` Regionen
- Fold 2: `0` Positive, `0` Regionen, `degeneration_flag = true`
- Fold 3: `57` Positive, `14` Regionen
- Fold 4: `112` Positive, `14` Regionen

#### RSV A / h7

- Fold 1: `0` Positive, `0` Regionen, `degeneration_flag = true`
- Fold 2: `0` Positive, `0` Regionen, `degeneration_flag = true`
- Fold 3: `2` Positive, `1` Region, `degeneration_flag = true`, `low_information_flag = true`
- Fold 4: `37` Positive, `11` Regionen

Kernaussage:

- `Influenza A` und `Influenza B` haben jeweils genau einen wirklich kollabierten Fold.
- `RSV A` hat dagegen eine massiv unteridentifizierte Event-Lernaufgabe.
- Das ist der Hauptgrund, warum RSV A nicht promoted werden sollte, selbst wenn einzelne Event-Metriken nett aussehen.

### 4. Baseline-Deltas mit Konfidenzintervallen

Die neuen Bootstrap-Intervalle sind jetzt da und machen die Aussage wesentlich ehrlicher.

Besonders wichtig:

- Für `Influenza A` und `Influenza B` sind die `PR-AUC`- und `Brier`-Verbesserungen des Event-Modells gegen Persistence klar positiv.
- Für `ECE` ist die Richtung bei A und B zwar punktuell besser, aber das Intervall schließt `0` noch nicht sicher aus.
- Für `RSV A` sind `PR-AUC`, `Brier` und `ECE` punktuell besser, aber die Fold-Struktur ist zu schwach, um daraus einen Champion-Satz zu bauen.

Das ist genau die Art von Evidenz, die vorher fehlte:

- nicht nur Punktwerte
- sondern Unsicherheiten
- plus rohe Fold-Deltas
- plus Degenerationsflags

## Forecast-implied Gegenbenchmark

Die neue `forecast-implied`-Spur beantwortet die zentrale Frage:

Kann man das Event schon direkt aus dem Quantil-Forecast ableiten, oder braucht man wirklich einen separaten Klassifikator?

### Influenza A / h7

- `forecast_implied`: `PR-AUC 0.641633`, `Brier 0.085442`, `ECE 0.067885`
- `event_model`: `PR-AUC 0.769943`, `Brier 0.057636`, `ECE 0.019538`

### Influenza B / h7

- `forecast_implied`: `PR-AUC 0.620017`, `Brier 0.091564`, `ECE 0.061081`
- `event_model`: `PR-AUC 0.773415`, `Brier 0.065444`, `ECE 0.024734`

### RSV A / h7

- `forecast_implied`: `PR-AUC 0.194282`, `Brier 0.049106`, `ECE 0.088722`
- `event_model`: `PR-AUC 0.461107`, `Brier 0.033040`, `ECE 0.022808`

Kernaussage:

- Der separate Event-Layer schlägt die forecast-abgeleitete Wahrscheinlichkeit in allen drei Scopes klar.
- Das heißt: der Event-Layer ist kein bloßes kosmetisches Add-on.
- Aber er kompensiert den schwachen Forecast-Kern noch nicht vollständig.

## Was jetzt wissenschaftlich fair zu sagen ist

- `Influenza A / h7` ist derzeit der sauberste Champion-Kandidat.
- `Influenza B / h7` hat jetzt ebenfalls einen starken Event-Layer, aber der Forecast-Kern verliert noch gegen Persistence.
- `RSV A / h7` bleibt `WATCH / Shadow`, weil die Fold-Positivität in mehreren Zeitfenstern kollabiert.

Die größte offene Stelle ist nicht mehr “gibt es überhaupt Event-Signal?”.
Die Antwort darauf ist für A und B jetzt klarer: ja.

Die offene Stelle ist jetzt:

1. Warum verliert der volle Quantil-Forecast noch gegen Persistence?
2. Kann die Forecast-Seite so verbessert werden, dass nicht nur das Event, sondern auch die ganze Zielverteilung gewinnt?
3. Kann RSV A überhaupt stabil genug gelabelt werden, um auf H7 eine ernsthafte Lernaufgabe zu sein?

## Endurteil

Der H7-Stack ist kein Heuristik-Matsch mehr.

Aber die ehrliche mathematische Lage ist:

- `Event-Layer`: deutlich gereift, bei `Influenza A` und `Influenza B` klar nützlich
- `Forecast-Kern`: noch nicht stark genug gegen `Persistence`
- `RSV A`: noch nicht identifizierbar genug für Champion-Status

Damit ist der richtige nächste Schritt nicht “noch ein Kalibrierer”, sondern:

1. den Forecast-Kern gezielt gegen Persistence verbessern
2. die Event-Stabilität pro Fold weiter überwachen
3. RSV A nur dann weiter promoten, wenn die Positivitätsstruktur nicht mehr kollabiert
