# Outcome Data Contract

## Zweck

`OutcomeObservation` ist das generische Datenformat fuer optionale kommerzielle Truth-/Outcome-Daten. Es ist absichtlich getrennt von allen epidemiologischen Forecast-Targets.

## Persistenz

Tabelle: `outcome_observations`

Implementierung:

- [backend/app/models/database.py](/Users/davidwegener/Desktop/viralflux/backend/app/models/database.py)
- [backend/alembic/versions/d7e4c9a1b2f3_add_outcome_observations.py](/Users/davidwegener/Desktop/viralflux/backend/alembic/versions/d7e4c9a1b2f3_add_outcome_observations.py)

## Pflichtfelder

| Feld | Typ | Beschreibung |
| --- | --- | --- |
| `brand` | string | Brand-/Mandantenkennung, aktuell typischerweise `gelo` |
| `product` | string | Produktname oder SKU-nahe Produktkennung |
| `region_code` | string | Region, aktuell z. B. Bundeslandcode |
| `window_start` | datetime | Start des Beobachtungsfensters |
| `window_end` | datetime | Ende des Beobachtungsfensters |
| `metric_name` | string | Typ der Outcome-Metrik |
| `metric_value` | float | Beobachteter Wert |
| `source_label` | string | Quelle oder Importlabel |

## Optionale Felder

| Feld | Typ | Beschreibung |
| --- | --- | --- |
| `metric_unit` | string | z. B. `EUR`, `units`, `index` |
| `channel` | string | Marketingkanal, falls vorhanden |
| `campaign_id` | string | Aktivierungs- oder Kampagnenkennung |
| `holdout_group` | string | z. B. `test`, `control` |
| `confidence_hint` | float | optionale Quellenschaetzung 0-1 |
| `metadata` | json | weitere nicht-kritische Zusatzdaten |

## Unterstuetzte `metric_name`-Werte in V1

- `media_spend`
- `impressions`
- `clicks`
- `qualified_visits`
- `search_demand`
- `sales`
- `orders`
- `revenue`
- `campaign_response`

## Normalisierung aus bestehenden MediaOutcomeRecord-Daten

Wenn `outcome_observations` leer ist, normalisiert der Truth-Layer lesend bestehende `MediaOutcomeRecord`-Felder auf folgende Namen:

| MediaOutcomeRecord | OutcomeObservation.metric_name |
| --- | --- |
| `media_spend_eur` | `media_spend` |
| `impressions` | `impressions` |
| `clicks` | `clicks` |
| `qualified_visits` | `qualified_visits` |
| `search_lift_index` | `search_demand` |
| `sales_units` | `sales` |
| `order_count` | `orders` |
| `revenue_eur` | `revenue` |

## Beispielpayload fuer `OutcomeObservationInput`

```json
{
  "brand": "gelo",
  "product": "GeloMyrtol forte",
  "region_code": "BY",
  "metric_name": "sales",
  "metric_value": 184.0,
  "window_start": "2026-02-02T00:00:00",
  "window_end": "2026-02-08T00:00:00",
  "source_label": "crm_export",
  "channel": "search",
  "campaign_id": "gelo-by-wave-02",
  "holdout_group": "test",
  "metadata": {
    "incremental_lift_pct": 7.4
  }
}
```

## Semantische Regeln

- Outcome-Daten bleiben kommerzielle Beobachtungen und werden nicht in Forecast-Truth umgeschrieben.
- Mehrere Metriken fuer dasselbe Zeitfenster sind erlaubt und sollen als separate Zeilen gespeichert werden.
- `holdout_group` gehoert zum Outcome-Layer, nicht zum Forecast-Layer.
- `metadata` darf angereichert werden, aber die Kernlogik des Truth-Layers darf sich nicht auf frei geformte Felder verlassen, ausser fuer optionale Lift-/Holdout-Hinweise.

## Scope fuer V1

- Wochen- oder Fensterebene
- Region- und Produkt-spezifisch
- GELO als Start-Brand
- lesender Fallback auf bestehende `MediaOutcomeRecord`-Imports
