# Security Hardening Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die kritischsten Sicherheitslücken ohne breiten Produktumbau schließen: offene Legacy-APIs serverseitig absichern, Login härten, Uploads besser validieren und interne Fehlerdetails nicht mehr an Clients leaken.

**Architecture:** Wir machen einen kleinen, risikoarmen Security-Schnitt. Statt die komplette Auth-Architektur sofort umzubauen, ziehen wir zuerst den serverseitigen Schutz an den offenen Routen hoch, härten den Login-Endpunkt und machen Uploads sowie Fehlerantworten sicherer. Die spätere Umstellung von Browser-Storage auf `httpOnly` Cookies bleibt bewusst in einer eigenen Phase.

**Tech Stack:** FastAPI, SlowAPI, Pydantic, SQLAlchemy, React/TypeScript, Docker Compose

---

### Task 1: Offene Legacy-API-Router absichern

**Files:**
- Modify: `backend/app/api/dashboard.py`
- Modify: `backend/app/api/inventory.py`
- Modify: `backend/app/api/outbreak_score.py`
- Modify: `backend/app/api/recommendations.py`
- Modify: `backend/app/api/data_import.py`
- Modify: `backend/app/main.py`
- Test: `backend/app/tests/` (gezielte neue Auth-Tests)

- [ ] **Step 1: Offene Router mit bestehender Auth-Strategie abgleichen**

Prüfen, welche Endpunkte im Media-/Forecast-Bereich bereits `Depends(get_current_user)` oder `Depends(get_current_admin)` verwenden und denselben Schutz auf die offenen Legacy-Router übertragen.

- [ ] **Step 2: Router- oder Route-Level Auth ergänzen**

Minimaler Ansatz:

```python
from app.api.deps import get_current_user, get_current_admin

router = APIRouter(dependencies=[Depends(get_current_user)])
```

Oder für mutierende Admin-Endpunkte:

```python
@router.post("/update", dependencies=[Depends(get_current_admin)])
async def update_inventory(...):
    ...
```

- [ ] **Step 3: Öffentliche Ausnahmen bewusst dokumentieren**

Nur Endpunkte unter `/api/v1/public/*`, Gesundheitschecks und M2M-Webhook-Routen bleiben bewusst offen oder separat geschützt.

- [ ] **Step 4: Gezielt testen**

Run: `cd backend && pytest app/tests -k "auth or public or admin" -q`

Expected: geschützte Legacy-Routen liefern ohne Token `401` oder `403`, öffentliche Routen bleiben erreichbar.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/dashboard.py backend/app/api/inventory.py backend/app/api/outbreak_score.py backend/app/api/recommendations.py backend/app/api/data_import.py backend/app/main.py backend/app/tests
git commit -m "fix: secure legacy api routes server-side"
```

### Task 2: Login-Schutz härten

**Files:**
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/core/rate_limit.py`
- Test: `backend/app/tests/` (neue Login-Rate-Limit-/Lockout-Tests)

- [ ] **Step 1: Bestehendes Login-Limit präzisieren**

Den Login-Endpunkt gezielt enger absichern und fehlgeschlagene Logins pro Benutzer/IP mitzählen.

- [ ] **Step 2: Einfachen Lockout nach wiederholtem Fehlversuch einbauen**

Minimaler Ansatz für Phase 1:

```python
FAILED_LOGINS: dict[str, list[float]] = {}
LOCKED_UNTIL: dict[str, float] = {}
```

Verhalten:
- Nach 5 Fehlversuchen innerhalb kurzer Zeit: temporärer Lockout
- Erfolgreiches Login löscht Fehlversuchszähler

- [ ] **Step 3: Fehlermeldungen generisch halten**

Nicht zwischen „Benutzer unbekannt“ und „Passwort falsch“ unterscheiden.

- [ ] **Step 4: Gezielt testen**

Run: `cd backend && pytest app/tests -k "login or auth" -q`

Expected: nach mehreren Fehlversuchen wird der Login temporär blockiert; bei Erfolg wird der Zähler zurückgesetzt.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/auth.py backend/app/core/rate_limit.py backend/app/tests
git commit -m "fix: harden login throttling and lockout behavior"
```

### Task 3: Upload-Validierung und Fehlerantworten härten

**Files:**
- Modify: `backend/app/api/data_import.py`
- Modify: `backend/app/api/drug_shortage.py`
- Modify: `backend/app/api/ingest.py`
- Modify: `backend/app/api/calibration.py` (wenn Uploads dort dieselbe Schwäche haben)
- Modify: `backend/app/api/outbreak_score.py` (wenn Uploads dort dieselbe Schwäche haben)
- Test: `backend/app/tests/`

- [ ] **Step 1: Gemeinsame Upload-Regeln definieren**

Regeln für Phase 1:
- Dateiendung prüfen
- MIME-Type prüfen, wenn von FastAPI verfügbar
- Dateigröße prüfen
- Parser-Fehler nur serverseitig loggen
- Client bekommt generische Fehlermeldung

- [ ] **Step 2: Fehlerdetails nicht mehr direkt an Clients zurückgeben**

Statt:

```python
raise HTTPException(500, f"Import fehlgeschlagen: {e}")
```

Neu:

```python
logger.error("Lab results import failed: %s", e)
raise HTTPException(500, "Import fehlgeschlagen.")
```

- [ ] **Step 3: MIME-Type-Check ergänzen**

Minimaler Ansatz:

```python
allowed_types = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
```

- [ ] **Step 4: Gezielt testen**

Run: `cd backend && pytest app/tests -k "upload or import" -q`

Expected: ungültige Typen werden abgelehnt, interne Parserdetails werden nicht an den Client geleakt.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/data_import.py backend/app/api/drug_shortage.py backend/app/api/ingest.py backend/app/api/calibration.py backend/app/api/outbreak_score.py backend/app/tests
git commit -m "fix: harden upload validation and error handling"
```

### Task 4: Verifikation und Handoff

**Files:**
- Modify: `README.md` / `DEPLOY.md` nur wenn Verhalten sichtbar geändert wurde

- [ ] **Step 1: Backend-Tests gezielt laufen lassen**

Run: `cd backend && pytest app/tests -k "auth or upload or public or admin" -q`

Expected: PASS

- [ ] **Step 2: Frontend-Typprüfung absichern**

Run: `cd frontend && npx tsc --noEmit`

Expected: PASS

- [ ] **Step 3: Docker-Config prüfen, falls Compose geändert wurde**

Run: `docker compose -f docker-compose.prod.yml config`

Expected: gültige Compose-Konfiguration

- [ ] **Step 4: Change Summary vorbereiten**

Dokumentieren:
- welche Legacy-Routen jetzt geschützt sind
- wie der Login-Lockout funktioniert
- welche Upload-Regeln jetzt gelten
- welche Risiken bewusst auf Phase 2 verschoben wurden (`httpOnly` Cookie Migration)

