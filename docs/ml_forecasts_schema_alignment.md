# MLForecast Schema Alignment

## Ausgangslage

`ml_forecasts` ist der persistierte Forecast-Store für den nationalen Forecast-first-Pfad.
Seit der Mehr-Horizont- und Scope-Erweiterung gehoeren zwei Felder zum Pflichtvertrag:

- `region`
- `horizon_days`

Zusätzlich werden diese Scopes über eigene Indizes adressiert:

- `ix_ml_forecasts_region`
- `ix_ml_forecasts_horizon_days`
- `idx_forecast_scope_date`
- `idx_forecast_scope_created`

Die dazugehörige Alembic-Migration ist:

- `f1a2b3c4d5e6_add_mlforecast_region_horizon_scope.py`

## Eindeutige Ursache des Live-Problems

Der Produktionsfehler `ml_forecasts.region does not exist` entsteht nicht durch ein falsches ORM-Modell,
sondern durch eine Datenbank, die hinter dem Repo-Migrationsstand liegt.

Der aktuelle ORM-Vertrag in [database.py](../backend/app/models/database.py)
enthält `region` und `horizon_days` auf `MLForecast`.
Wenn diese Spalten in der DB fehlen, generiert SQLAlchemy bereits beim normalen Query-Load ein fehlerhaftes `SELECT`.

## Finaler Zielzustand

- Code und Datenbank benutzen denselben `MLForecast`-Vertrag.
- Nationale Monitoring-/Cockpit-Pfade lesen `MLForecast` explizit mit:
  - `region = "DE"`
  - `horizon_days = 7`
- Fehlende Pflichtmigrationen werden explizit erkannt statt implizit toleriert.
- Schema-Mismatches laufen nicht mehr als generischer `500`, sondern als klarer Betriebsfehler.

## Implementierte Absicherung

### 1. Expliziter Schema-Contract

`backend/app/db/schema_contracts.py` definiert den migration-managed Pflichtvertrag für `ml_forecasts`.

Wichtige Funktionen:

- `get_required_schema_contract_gaps(...)`
- `get_ml_forecast_schema_gaps(...)`
- `ensure_ml_forecast_schema_aligned(...)`

Wenn `region`, `horizon_days` oder die Scope-Indizes fehlen, wird
`MLForecastSchemaMismatchError` geworfen.

### 2. Startup-/Schema-Check

`backend/app/db/session.py` prüft jetzt nicht mehr nur optionale Runtime-Gaps,
sondern auch Pflichtfelder, die ausschliesslich per Migration bereitgestellt werden müssen.

Wichtig:

- `ml_forecasts.region` und `ml_forecasts.horizon_days` werden **nicht** als Runtime-Patch still nachgezogen
- fehlende Pflichtmigrationen markieren den DB-Stand explizit als kritisch

### 3. Nationaler Scope für Legacy-/Monitoring-Reader

Folgende Services lesen nationale `MLForecast`-Daten jetzt explizit mit `DE/h7`:

- [forecast_decision_service.py](../backend/app/services/ml/forecast_decision_service.py)
- [peix_score_service.py](../backend/app/services/media/peix_score_service.py)

Damit werden regionale Forecasts oder alternative Horizonte nicht versehentlich in nationale Monitoring- oder PEIX-Signale gemischt.

### 4. API-Verhalten bei Schema-Mismatch

Betroffene Endpunkte mappen `MLForecastSchemaMismatchError` jetzt auf `503` statt auf einen generischen `500`.

Betroffen:

- `/api/v1/forecast/monitoring/{virus_typ}`
- `/api/v1/forecast/monitoring`
- `/api/v1/media/cockpit`

Das ist absichtlich kein stiller Fallback.
Der Fehler bleibt sichtbar, aber als klarer Betriebs-/Schemafehler statt als opaque Internal Error.

## Migration und Rollout

Das Repo hatte zuvor zwei Alembic-Heads.
Für einen sauberen Deployment-Pfad wurde eine Merge-Revision hinzugefuegt:

- `9695cafe1234_merge_truth_and_mlforecast_heads.py`

Damit kann der DB-Stand eindeutig mit einem einzelnen Upgrade-Befehl angehoben werden:

```bash
cd backend
alembic upgrade head
```

## Erwartetes Verhalten nach dem Upgrade

Nach Anwendung der Migrationen gilt:

- `ml_forecasts` besitzt `region` und `horizon_days`
- Cockpit-/Monitoring-Pfade laufen wieder ohne den bisherigen Column-Error
- Readiness meldet echte fachliche Blocker, aber keinen impliziten Schema-Mismatch mehr

## Was dieser Fix bewusst nicht tut

- keine automatische stille Reparatur von `ml_forecasts` in Produktion
- kein Verdecken fehlender Migrationen hinter Defaultwerten
- kein breiter Refactor aller historischen `MLForecast`-Reader ausserhalb des unmittelbar betroffenen Monitoring-/Cockpit-Pfads
