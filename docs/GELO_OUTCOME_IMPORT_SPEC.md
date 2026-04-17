# GELO Outcome-Import-Spezifikation

**Version:** 1.0 (2026-04-17)
**Empfänger:** GELO BI-/Data-Team
**Absender:** peix healthcare media · ViralFlux Media Intelligence
**Zweck:** Dieses Dokument beschreibt, welche Daten wir von GELO pro Woche benötigen, um den Feedback-Loop im Cockpit („Wirkung"-Tab) zu aktivieren, damit unser Modell aus tatsächlichen Verkaufszahlen lernt und zunehmend präzisere Media-Empfehlungen liefert.

---

## 1. Was passiert mit den Daten

Die gelieferten Zeilen landen in `media_outcome_records` und werden für drei Zwecke genutzt:

1. **Truth-Layer** — wir wissen, was tatsächlich an Umsatz und Absatz entstanden ist, pro Woche × Bundesland × Produkt.
2. **Kalibrierung** — unser Forecast-Modell lernt daraus, wie gut Ranking und Signalstärke mit echten Verkaufsbewegungen korrelieren.
3. **Attribution (optional, nur mit `holdout_group`)** — wenn GELO bewusst Kontroll-Gruppen-Wellen fährt (z. B. ein Bundesland ohne Shift lässt), können wir den Lift sauber ausrechnen. Ohne Holdout bleibt es bei Korrelation, keine Kausalität.

**Was die Daten NICHT sind**:
- Keine Einzelkunden-Daten. Rezepte, Kaufhistorien auf Person, IMEI-/IP-Tracking etc. **niemals** liefern.
- Keine rohen POS-Transaktionen. Nur aggregierte Summen auf BL-Ebene oder gröber.
- Keine Medizin-/Gesundheits-Daten im DSGVO-Sinn. Verkäufe eines OTC-Produkts sind Handelsdaten, keine Gesundheitsdaten.

---

## 2. Dateiformat

- **CSV**, UTF-8, Semikolon als Trennzeichen (`;`). Alternativ Tab oder Komma — der Importer erkennt automatisch.
- Dezimaltrennzeichen: **Punkt** (`.`), nicht Komma. `12345.67`, nicht `12345,67`.
- Datum: **ISO 8601** (`YYYY-MM-DD`), Wochen jeweils als Montag der entsprechenden ISO-Woche.
- Kopfzeile mit Spaltennamen exakt wie unten, nicht umbenennen.
- Eine Datei pro Export, max. 50 MB pro Batch; mehrere Wochen in einer Datei sind OK.

### Dateibenennung (Konvention, nicht technisch zwingend)

```
gelo_outcomes_<jahr>w<kw>_<produkt>_<datumstempel>.csv
```

Beispiel:

```
gelo_outcomes_2026w14_gelomyrtol_20260410.csv
```

---

## 3. Pflichtfelder

| Feld | Typ | Beispiel | Kommentar |
|---|---|---|---|
| `week_start` | Date (ISO) | `2026-04-06` | Montag der ISO-Woche. |
| `brand` | String | `GELO` | Frei, aber konsistent. Wir pinnen per `brand`-Index. |
| `product` | String | `GeloMyrtol forte 100 Stk.` | SKU-Ebene idealerweise. |
| `region_code` | String (2 Zeichen) | `BY` | Bundesland-Code (siehe §6). |
| `source_label` | String | `gelo_pos_wholesale_v1` | Identifiziert den Export-Typ und die Version. |

## 4. Optionale Outcome-Felder (alles, was wir lernen können)

Je mehr davon, desto präziser unser Modell. Alles als `double` (Fließkomma).

| Feld | Einheit | Beispiel | Was wir lernen |
|---|---|---|---|
| `media_spend_eur` | EUR | `125000.00` | Investitions-Seite. Wichtig für ROAS-Ableitung. |
| `impressions` | Stück | `3400000` | Reichweiten-Volumen. |
| `clicks` | Stück | `18700` | Interaktions-Volumen. |
| `qualified_visits` | Stück | `4200` | Gemeinten Traffic auf Landing-Page. |
| `search_lift_index` | Index 0-10 | `2.3` | Such-Aufmerksamkeit (eigener Proxy, falls GELO einen hat). |
| **`sales_units`** | Stück | `8420` | **Kernmetrik**. Verkaufte Einheiten in der Woche. |
| `order_count` | Stück | `7120` | Anzahl Transaktionen (optional). |
| `revenue_eur` | EUR | `142300.00` | Umsatz netto. |

Mindestens `sales_units` oder `revenue_eur` sollte gefüllt sein. Idealerweise beide — dann können wir auch Preisdynamik modellieren.

## 5. Optionale Attribution-Felder (nur wenn GELO es sauber tracken kann)

| Feld | Typ | Beispiel | Kommentar |
|---|---|---|---|
| `campaign_id` | String | `GM_H1_2026_NORD` | Wenn mehrere Kampagnen parallel laufen. |
| `channel` | String | `tv` / `digital` / `print` / `ooh` | Kanal-spezifisch. |
| `holdout_group` | String | `treatment` / `control` / `shadow` | **Wichtig für Attribution.** Siehe §5.1. |
| `extra_data` | JSON-String | `{"creative_variant": "A"}` | Beliebige Metadaten. |

### 5.1 Holdout-Gruppen — warum das wichtig ist

Ohne Holdout: wir können sehen, dass Sales in Bayern gestiegen sind — aber wir wissen nicht, ob *unser* Media-Shift die Ursache war oder ob die Welle einfach von selbst kam. Das ist **Korrelation ohne Kausalität**.

Mit Holdout:
- **treatment**: die Bundesländer, die den empfohlenen Shift bekommen haben
- **control**: vergleichbare Bundesländer, die bewusst nicht verändert wurden
- **shadow**: Bundesländer, für die eine Empfehlung existierte, aber nicht umgesetzt wurde

Wenn treatment-BLs mehr Sales-Lift zeigen als control-BLs, können wir die Wirkung unseres Modells **mit Konfidenzintervall** quantifizieren. Das ist der Unterschied zwischen „wir glauben, wir helfen" und „wir können es belegen".

**Empfehlung**: In 1-2 Wellen pro Jahr bewusst Holdout fahren. Der Informationsgewinn übertrifft den vermeintlichen Opportunity-Verlust bei Weitem.

---

## 6. Region-Codes (exakt diese, nichts anderes)

| Code | Bundesland |
|---|---|
| `SH` | Schleswig-Holstein |
| `HH` | Hamburg |
| `NI` | Niedersachsen |
| `HB` | Bremen |
| `NW` | Nordrhein-Westfalen |
| `HE` | Hessen |
| `RP` | Rheinland-Pfalz |
| `SL` | Saarland |
| `BW` | Baden-Württemberg |
| `BY` | Bayern |
| `BE` | Berlin |
| `BB` | Brandenburg |
| `MV` | Mecklenburg-Vorpommern |
| `SN` | Sachsen |
| `ST` | Sachsen-Anhalt |
| `TH` | Thüringen |

Wenn GELO auf PLZ-Ebene aggregiert: bitte selbst auf BL mappen **bevor** der Export entsteht, wir haben keinen internen Mapper.

---

## 7. Beispiel-Zeilen

```csv
week_start;brand;product;region_code;source_label;media_spend_eur;impressions;clicks;qualified_visits;search_lift_index;sales_units;order_count;revenue_eur;campaign_id;channel;holdout_group
2026-04-06;GELO;GeloMyrtol forte 100 Stk.;BY;gelo_pos_wholesale_v1;125000.00;3400000;18700;4200;2.3;8420;7120;142300.00;GM_H1_2026_BY;digital;treatment
2026-04-06;GELO;GeloMyrtol forte 100 Stk.;NW;gelo_pos_wholesale_v1;180000.00;5100000;21300;4900;1.8;7150;6050;120900.00;GM_H1_2026_NW;digital;treatment
2026-04-06;GELO;GeloMyrtol forte 100 Stk.;BW;gelo_pos_wholesale_v1;0.00;0;0;0;1.1;6380;5390;107900.00;;;control
2026-04-06;GELO;GeloMyrtol forte 100 Stk.;HE;gelo_pos_wholesale_v1;0.00;0;0;0;0.9;4210;3560;71200.00;;;control
```

Vier Zeilen für eine Woche mit zwei Treatment-BLs (BY, NW mit Media-Spend) und zwei Control-BLs (BW, HE ohne Spend aber mit Sales-Messung).

---

## 8. Einspiel-Wege

### 8.1 Empfohlen: REST-Endpoint

**URL:** `POST https://fluxengine.labpulse.ai/api/v1/media/outcomes/import`
**Auth:** Header `X-API-Key: <M2M-Secret>` (der Key wird separat via sicheren Kanal ausgetauscht)
**Content-Type:** `multipart/form-data` mit Feld `file=<csv>`
**Response:** JSON mit `batch_id`, `rows_total`, `rows_valid`, `rows_rejected`, `rows_duplicate`, Liste der Import-Issues bei Fehlern.

Wir empfehlen dies als wöchentlichen Cron-Job im GELO-BI-System. Der Endpoint ist idempotent: derselbe `week_start × region_code × product × source_label` überschreibt keine historischen Zeilen, sondern führt sie in ein Update zusammen.

### 8.2 Alternativ: Backoffice-Upload

Manuelle CSV-Upload-Maske im peix-Backoffice. Geeignet für monatliche Batch-Lieferungen. URL und Zugang wird separat kommuniziert.

### 8.3 Alternativ: S3-/SFTP-Drop

Wenn GELO keinen Outbound-HTTP-Weg hat, können wir einen S3-Bucket oder SFTP-Zielordner einrichten. Dateien dort landen, unser Ingestion-Worker zieht sie alle 4h. Setup-Aufwand: 1 Tag.

---

## 9. Fehlerbehandlung und Qualitätsberichte

Nach jedem Import schreibt unser System in `media_outcome_import_batches` den Batch-Status und in `media_outcome_import_issues` jede abgelehnte Zeile mit Begründung. Typische Probleme:

| Issue-Code | Bedeutung | Was tun |
|---|---|---|
| `invalid_region_code` | `region_code` nicht in der Liste aus §6 | Export-Mapping korrigieren |
| `week_not_monday` | `week_start` ist nicht Montag | Auf ISO-Woche-Montag runden |
| `duplicate_row` | `week × region × product × source_label` gab es schon | Entweder OK (Update) oder Source-Label versionieren |
| `negative_metric` | `sales_units < 0` etc. | Datenfehler; GELO-seitig klären |
| `unknown_brand` | Brand noch nicht in unserem Stamm | Einmalig freischalten, dann OK |

Wir liefern auf Wunsch einen Wochen-Report per E-Mail mit Import-Zusammenfassung.

---

## 10. Datenschutz und Verträge

- Aggregatebene ist Handelsdaten, keine Gesundheitsdaten. DSGVO Art. 9 greift **nicht**.
- GELO bleibt Dateneigentümer. Wir verarbeiten im Auftrag, AVV (Art. 28 DSGVO) erforderlich — Entwurf liegt separat vor.
- Speicherort: Hetzner Cloud Deutschland, Finkenwerder (Hamburg).
- Aufbewahrung: 36 Monate rollierend, dann automatische Anonymisierung (Aggregation auf Nord/Süd/Ost/West).
- Löschung auf Anforderung jederzeit möglich, max. 14 Tage Umsetzungsfrist.

---

## 11. Häufige Fragen

**„Wie oft liefern?"** — Wöchentlich ist ideal, monatlich funktioniert auch, aber verlangsamt den Lern-Loop. Tägliche Daten nutzen wir nicht direkt (wir aggregieren intern auf Wochen), also kein Overkill.

**„Wie lange zurück?"** — Je mehr historische Daten (2-3 volle Saisons), desto besser kann unser Modell saisonale Muster lernen. Mindestens 12 Monate zurück.

**„Können wir auch Großhandels-Sell-In liefern?"** — Ja, als zusätzlicher `source_label`-Kanal (z. B. `gelo_wholesale_sellin_v1`). Sell-In ist dann als getrennter Stream sichtbar.

**„Was, wenn wir nur einige Produkte tracken können?"** — Dann auf diese Produkte beschränken. Das Modell lernt pro Produkt separat — was wir nicht sehen, prognostizieren wir nicht.

**„Wann sehen wir Ergebnisse?"** — Die Truth-Anzeige im Cockpit-Tab „Wirkung" wird sofort sichtbar. Die Modell-Kalibrierung braucht mindestens 4-6 Wellen-Wochen, um stabil zu werden.

---

## 12. Ansprechpartner

- **Fachlich / Schema-Fragen:** peix · David Wegener · mail@davidwegener.de
- **Technisch / API-Credentials:** separater Security-Kanal nach NDA-Unterzeichnung

---

**Anhang A: JSON-Schema (maschinenlesbar)**

Ein machine-readable JSON-Schema dieser Spezifikation kann auf Wunsch separat geliefert werden, um GELOs Export-Pipeline direkt zu validieren.
