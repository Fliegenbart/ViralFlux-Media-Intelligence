# Contributing

Diese Datei ist für Entwickler gedacht, die am Projekt mitarbeiten.

## Für neue Entwickler wichtig

1. Nicht von alten README-Annahmen ausgehen.  
   Der heutige Live-Deploy läuft über den Clean-Checkout auf dem Server.

2. Nicht `Event-Wahrscheinlichkeit`, `Ranking-Signal` und `Priorität` vermischen.  
   Diese Trennung ist fachlich wichtig und bewusst im UI sichtbar.

3. Bei Frontend-Änderungen immer Build und die betroffenen Tests ausführen.  
   Vor allem bei Cockpit-Komponenten und Auth-Flows.

4. Live nie direkt aus lokalen Sonderständen denken.  
   Erst committen, pushen und danach über den dokumentierten Deploy-Weg ausrollen.

## Entwicklungsfluss

1. Branch anlegen
2. Kleine, zusammenhängende Änderung umsetzen
3. Gezielt validieren
4. Committen und pushen
5. Pull Request erstellen und mergen

## Nützliche Befehle

### Git-Status prüfen

```bash
git status --short --branch
```

### Frontend-Build prüfen

```bash
cd frontend
npm run build
```

### Einzelnen Frontend-Test ausführen

```bash
cd frontend
npm test -- --runInBand src/components/cockpit/OperationalDashboard.test.tsx
```

### Produktive Health-Checks prüfen

```bash
curl https://fluxengine.labpulse.ai/health/live
curl https://fluxengine.labpulse.ai/health/ready
```

## Weitere Dokumente

- [QUICKSTART.md](QUICKSTART.md)
- [DEPLOY.md](DEPLOY.md)
- [docs/README.md](docs/README.md)
