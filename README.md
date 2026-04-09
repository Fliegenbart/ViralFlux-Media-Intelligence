# ViralFlux Media Intelligence

## Produktproblem
ViralFlux hilft dabei, regionale Viruslage, Forecast und die naechste operative Entscheidung schnell zu verstehen.

## Kernoberflaechen
- `/welcome` als Einstiegspfad
- `/virus-radar` als Hauptansicht fuer Lage und Priorisierung
- `/jetzt` als aktueller Arbeitsblick
- `/zeitgraph` als Verlaufssicht
- `/regionen` als Regionenvergleich
- `/kampagnen` als Kampagnenarbeit
- `/evidenz` als Pruefung, ob die Vorhersage belastbar ist

## Technischer Kern
- React-Frontend fuer die Oberflaechen
- FastAPI-Backend fuer die API
- PostgreSQL als Datenbasis

## Startbefehle
Frischer Checkout:
1. `.env.example` nach `.env` kopieren
2. die Pflichtwerte in `.env` setzen

```bash
docker compose up -d db redis backend

cd frontend
npm install
npm start
```

## Testbefehle
Frontend:
```bash
cd frontend && npm run build
```

Backend:

Hinweis: der Backend-Testlauf braucht eine aktive Python-3.11-Umgebung.

```bash
POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test PYTHONPATH=backend python -m pytest backend/app/tests/test_ai_campaign_planner.py backend/app/tests/test_startup_singleton.py -q --tb=short
```
