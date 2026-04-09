# Sale Cleanup Scope

## Ziel

Dieses Verzeichnis beschreibt, welche Teile des Repos fuer Kaeufer sichtbar bleiben sollen und welche internen Artefakte nicht in einen Buyer-Facing Branch gehoeren.

## Buyer-Facing behalten

- Forecast- und Backtest-Kern
- aktuelle Media-UI
- schlanke Betriebsdoku

## Buyer-Facing entfernen

- interne Agenten-/Superpowers-Artefakte
- veraltete Projektlisten
- interne Audit-, Blocker- und Pitch-Dokumente

## Nicht loeschen, sondern spaeter umbauen

- Auth
- Runtime-Schema-Updates
- Startup-Seiteneffekte
- KI-Planer-Pfad
