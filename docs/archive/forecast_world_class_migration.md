# Forecast World-Class Migration

## Was sich geändert hat

- probabilistische Benchmark-Metriken sind jetzt im Code vorhanden
- Promotion ist nicht mehr nur MAPE/RMSE-orientiert
- regionale Artefakte tragen mehr probabilistische und operative Metadaten
- Revisions-Policies können jetzt als `raw`, `adjusted` oder `adaptive` beschrieben werden

## Warum das wichtig ist

Das System kann nun nachvollziehbarer entscheiden, welches Modell Champion ist, und es kann probabilistische Qualität getrennt von reinen Punktfehlern bewerten.

## Migrationsprinzip

- keine Breaking Changes in den öffentlichen Forecast-Responses
- alte Pfade bleiben als Fallback bestehen
- neue Felder sind additiv
- Champion-Wechsel soll über Benchmark-Evidenz laufen

## Offene operative Risiken

- reale Benchmark-Läufe hängen von einer verfügbaren Datenbank und echten Vintage-Daten ab
- TSFM-Challenger sind nur als optionaler Adapter vorbereitet
- adaptive Revisions-Policy ist zunächst konservativ und fällt auf `raw` zurück
