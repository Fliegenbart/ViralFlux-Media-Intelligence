# ViralFlux Media Intelligence

ViralFlux ist eine Plattform für regionale Virus-Frühwarnung und daraus abgeleitete operative Media-Entscheidungen.

ViralFlux erkennt früh, in welchen Bundesländern respiratorische Dynamiken an Relevanz gewinnen.  
Die Plattform übersetzt diese Signale in priorisierte Regionen, prüfbare Maßnahmen und sichtbare Freigabe-Status.  
So wird aus Frühwarnung ein klarer Arbeitsfluss von Einordnung über Entscheidung bis zur operativen Freigabe.

Live-Instanz: [https://fluxengine.labpulse.ai/](https://fluxengine.labpulse.ai/)

```text
┌──────────────────────────────────────────────┐
│ Filter │ Karte Deutschland │ Fokusfall      │
├─────────────────────────────┬────────────────┤
│ Regionen nach Stage         │ NRW · Activate │
│ Activate / Prepare / Watch  │ Event-Wkt 72%  │
│ Klick = Fokus wechseln      │ Freigabe offen │
├──────────────────────────────────────────────┤
│ Regionen-Ticker │ Evidenz │ Kampagnen │ Trace│
└──────────────────────────────────────────────┘
```

Tech-Stack: React, FastAPI, Prophet, PostgreSQL, Docker

Weiterlesen:
- [QUICKSTART.md](QUICKSTART.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [docs/OPERATORS_GUIDE.md](docs/OPERATORS_GUIDE.md)
- [DEPLOY.md](DEPLOY.md)
