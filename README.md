# ViralFlux Media Intelligence

## Produktproblem
ViralFlux hilft dabei, regionale Viruslage, Forecast und die naechste operative Entscheidung schnell zu verstehen.

## Kernoberflaechen
- `/welcome` als kurzer Einstieg ins Produkt
- `/virus-radar` als Hauptansicht fuer Lage, Trend und Priorisierung
- `/evidenz` als Pruefung, ob die Vorhersage belastbar ist

## Technischer Kern
- React-Frontend fuer die Oberflaechen
- FastAPI-Backend fuer die API
- PostgreSQL als Datenbasis
- Die Seiten trennen Einstieg, Arbeitsansicht und Evidenz bewusst klar

## Startbefehle
```bash
docker compose up -d db redis backend

cd frontend
npm install
npm start
```

## Testbefehle
```bash
cd frontend && npm run build
```

```bash
POSTGRES_USER=test POSTGRES_PASSWORD=test POSTGRES_DB=test OPENWEATHER_API_KEY=test SECRET_KEY=ci-test-secret-key-minimum-32-chars ADMIN_EMAIL=ci@test.de ADMIN_PASSWORD=ci-test-password-12chars ENVIRONMENT=test PYTHONPATH=backend /Users/davidwegener/Desktop/viralflux/.venv-backend311/bin/python -m pytest backend/app/tests/test_ai_campaign_planner.py backend/app/tests/test_startup_singleton.py -q --tb=short
```
