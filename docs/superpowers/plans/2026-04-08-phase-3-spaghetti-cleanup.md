# Phase 3 Spaghetti Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die gewachsenen Großdateien `frontend/src/features/media/useMediaData.ts` und `backend/app/services/marketing_engine/opportunity_engine.py` in kleinere, klarere Module aufteilen, ohne bestehende API- oder UI-Verhalten zu brechen.

**Architecture:** Im Frontend bleibt `useMediaData.ts` als dünne Kompatibilitäts-Schicht bestehen und re-exportiert neue, kleinere Hook-Dateien. Im Backend bleibt `MarketingOpportunityEngine` die öffentliche Einstiegsklasse, delegiert aber klar getrennte Verantwortungsblöcke an Hilfsmodule, damit Importe und Aufrufer stabil bleiben.

**Tech Stack:** React, TypeScript, Jest, FastAPI, SQLAlchemy, Pytest

---

### Task 1: Frontend-Schnitt festziehen

**Files:**
- Modify: `frontend/src/features/media/useMediaData.test.tsx`
- Modify: `frontend/src/features/media/useMediaData.ts`
- Test: `frontend/src/features/media/useMediaData.test.tsx`

- [ ] **Step 1: Die aktuellen öffentlichen Exporte absichern**

Erweitere `frontend/src/features/media/useMediaData.test.tsx` um einen kleinen Export-Schutz, damit die Aufteilung die bestehende Import-Oberfläche nicht still verändert. Prüfe mindestens:
- `buildNowPageViewModel`
- `buildWorkspaceStatus`
- `useNowPageData`
- `useTimegraphPageData`
- `useDecisionPageData`
- `useRegionsPageData`
- `useCampaignsPageData`
- `useEvidencePageData`
- `useOperationalDashboardData`

- [ ] **Step 2: Test gezielt laufen lassen**

Run: `cd frontend && CI=true npm test -- --watch=false src/features/media/useMediaData.test.tsx`

Expected: PASS, damit wir vor dem Refactor einen festen Sicherheitsgurt haben.

- [ ] **Step 3: `useMediaData.ts` auf echte Verantwortungsblöcke kartieren**

Dokumentiere im Code kurz mit Gruppierungskommentaren, welche Blöcke in Shared Helpers, Now/Timegraph Hooks und übrige Page Hooks wandern. Keine Logik ändern, nur die Trennlinie sichtbar machen.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/media/useMediaData.test.tsx frontend/src/features/media/useMediaData.ts
git commit -m "test: lock public media data hook exports"
```

### Task 2: Shared Frontend-Helfer extrahieren

**Files:**
- Create: `frontend/src/features/media/useMediaData.shared.ts`
- Modify: `frontend/src/features/media/useMediaData.ts`
- Test: `frontend/src/features/media/useMediaData.test.tsx`

- [ ] **Step 1: Failing test oder Snapshot-Schutz für Shared-abhängige Now-Logik ergänzen**

Nutze den bestehenden `buildNowPageViewModel`-Testpfad und ergänze einen klaren Fall für die fokussierte Region und Summary, damit der Shared-Extract nicht versehentlich Verhalten kippt.

- [ ] **Step 2: Shared-Modul anlegen**

Verschiebe in `frontend/src/features/media/useMediaData.shared.ts` nur die rein funktionalen, mehrfach genutzten Bausteine:
- `noop`
- `ToastLike`
- `NowPage*`-Typen
- `TimegraphRegionOption`
- `sortRegionalPredictions`
- `deriveNowFocusRegionCode`
- `buildWorkspaceStatus`
- `buildNowPageViewModel`
- kleinere Formatter-/Mapper-Helfer, die keine React Hooks nutzen

`frontend/src/features/media/useMediaData.ts` soll diese Dinge danach nur noch re-exportieren.

- [ ] **Step 3: Gezielt testen**

Run: `cd frontend && CI=true npm test -- --watch=false src/features/media/useMediaData.test.tsx`

Expected: PASS

- [ ] **Step 4: Typprüfung laufen lassen**

Run: `cd frontend && npx tsc --noEmit`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/media/useMediaData.shared.ts frontend/src/features/media/useMediaData.ts frontend/src/features/media/useMediaData.test.tsx
git commit -m "refactor: extract shared media data helpers"
```

### Task 3: Frontend-Hooks aufteilen und stale-request-Schutz vereinheitlichen

**Files:**
- Create: `frontend/src/features/media/useNowPageData.ts`
- Create: `frontend/src/features/media/useTimegraphPageData.ts`
- Create: `frontend/src/features/media/useDecisionPageData.ts`
- Create: `frontend/src/features/media/useRegionsPageData.ts`
- Create: `frontend/src/features/media/useCampaignsPageData.ts`
- Create: `frontend/src/features/media/useEvidencePageData.ts`
- Create: `frontend/src/features/media/useOperationalDashboardData.ts`
- Modify: `frontend/src/features/media/useMediaData.ts`
- Modify: `frontend/src/features/media/useMediaData.test.tsx`
- Test: `frontend/src/features/media/useMediaData.test.tsx`

- [ ] **Step 1: Einen kleinen Race-Condition-Test ergänzen**

Nutze das bestehende Deferred-Muster in `useMediaData.test.tsx` und ergänze mindestens einen Test, der sicherstellt, dass ein später gestarteter Request nicht von einer alten Antwort überschrieben wird. Der Test soll nicht alle Hooks abdecken, aber das gemeinsame Schutzmuster absichern.

- [ ] **Step 2: Hook-Dateien anlegen**

Ziehe jeden Page-Hook in seine eigene Datei. Regeln:
- keine neuen API-Calls einführen
- Hook-Signaturen unverändert lassen
- gemeinsame Hilfen nur aus `useMediaData.shared.ts` importieren
- `useMediaData.ts` wird zum Barrel mit Re-Exports

- [ ] **Step 3: stale-request-Schutz angleichen**

Verwende für asynchrone Page-Hooks ein einheitliches Muster auf Basis eines Versionszählers oder Abort-Guards, damit alte Responses nach schnellem Seitenwechsel keinen neueren Zustand überschreiben. Wende das mindestens auf `useDecisionPageData`, `useRegionsPageData`, `useCampaignsPageData`, `useEvidencePageData` und `useOperationalDashboardData` an, weil dort heute noch kein konsistenter Schutz sichtbar ist.

- [ ] **Step 4: Gezielt testen**

Run: `cd frontend && CI=true npm test -- --watch=false src/features/media/useMediaData.test.tsx src/components/AppLayout.test.tsx src/components/cockpit/NowWorkspace.test.tsx`

Expected: PASS

- [ ] **Step 5: Typprüfung laufen lassen**

Run: `cd frontend && npx tsc --noEmit`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/media/useMediaData.ts frontend/src/features/media/useMediaData.shared.ts frontend/src/features/media/useNowPageData.ts frontend/src/features/media/useTimegraphPageData.ts frontend/src/features/media/useDecisionPageData.ts frontend/src/features/media/useRegionsPageData.ts frontend/src/features/media/useCampaignsPageData.ts frontend/src/features/media/useEvidencePageData.ts frontend/src/features/media/useOperationalDashboardData.ts frontend/src/features/media/useMediaData.test.tsx frontend/src/components/AppLayout.test.tsx frontend/src/components/cockpit/NowWorkspace.test.tsx
git commit -m "refactor: split media page hooks by responsibility"
```

### Task 4: Backend-Konstanten und Output-Helfer auslagern

**Files:**
- Create: `backend/app/services/marketing_engine/opportunity_engine_constants.py`
- Create: `backend/app/services/marketing_engine/opportunity_engine_presenters.py`
- Modify: `backend/app/services/marketing_engine/opportunity_engine.py`
- Test: `backend/app/tests/test_opportunity_engine_math.py`

- [ ] **Step 1: Bestehende Hilfslogik mit Mathematik-/Output-Tests absichern**

Erweitere `backend/app/tests/test_opportunity_engine_math.py` um gezielte Fälle für:
- `_fact_label`
- `_public_fact_value`
- `_build_decision_brief`
- `_confidence_pct`

Ziel: Die spätere Auslagerung bleibt verhaltensgleich.

- [ ] **Step 2: Konstante Tabellen aus dem Hauptfile ziehen**

Lege `opportunity_engine_constants.py` an und verschiebe dorthin:
- `LEGACY_TO_WORKFLOW`
- `WORKFLOW_TO_LEGACY`
- `WORKFLOW_STATUSES`
- `ALLOWED_TRANSITIONS`
- `BUNDESLAND_NAMES`
- `REGION_NAME_TO_CODE`
- `FORECAST_PLAYBOOK_MAP`

Importiere diese Konstanten zurück in `opportunity_engine.py`.

- [ ] **Step 3: Präsentations-/Output-Helfer auslagern**

Lege `opportunity_engine_presenters.py` an und verschiebe dorthin nur die klaren Output-Helfer:
- `_fact_label`
- `_public_fact_value`
- `_confidence_pct`
- `_secondary_products`
- `_decision_facts`
- `_build_decision_brief`
- `_clean_for_output`

Der Haupt-Engine-Code soll diese Helfer importieren oder über kleine Wrapper weiterverwenden, damit Tests und Aufrufer nicht brechen.

- [ ] **Step 4: Gezielt testen**

Run: `PYTHONPATH=backend .venv-backend311/bin/pytest backend/app/tests/test_opportunity_engine_math.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/marketing_engine/opportunity_engine.py backend/app/services/marketing_engine/opportunity_engine_constants.py backend/app/services/marketing_engine/opportunity_engine_presenters.py backend/app/tests/test_opportunity_engine_math.py
git commit -m "refactor: extract marketing opportunity constants and presenters"
```

### Task 5: Backend-Workflow- und Campaign-Logik entflechten

**Files:**
- Create: `backend/app/services/marketing_engine/opportunity_engine_campaigns.py`
- Create: `backend/app/services/marketing_engine/opportunity_engine_queries.py`
- Modify: `backend/app/services/marketing_engine/opportunity_engine.py`
- Test: `backend/app/tests/test_marketing_api.py`
- Test: `backend/app/tests/test_forecast_decision_service.py`

- [ ] **Step 1: Öffentliche Verhaltenspfade mit Tests absichern**

Ergänze oder schärfe Tests für die stabil zu haltenden Pfade:
- `update_campaign`
- `update_status`
- `export_crm_json`
- `get_opportunities`

Nutze dafür bevorzugt `test_marketing_api.py` und bestehende Engine-nahe Tests in `test_forecast_decision_service.py`.

- [ ] **Step 2: Query- und Filterlogik auslagern**

Ziehe lesende Datenbank-Helfer in `opportunity_engine_queries.py`, zum Beispiel:
- `_latest_market_backtest`
- `get_opportunities`
- `count_opportunities`
- `get_recommendation_by_id`
- kleine Filter-/Status-Helfer wie `_normalize_workflow_status`, `_status_filter_values`, `_parse_iso_datetime`

- [ ] **Step 3: Campaign-/Workflow-Schreiblogik auslagern**

Ziehe schreibende Kampagnen- und Workflow-Logik in `opportunity_engine_campaigns.py`, zum Beispiel:
- `update_campaign`
- `update_status`
- `export_crm_json`
- campaign-pack-/preview-bezogene Helfer

Die öffentliche Klasse `MarketingOpportunityEngine` soll danach nur noch delegieren, damit `api/marketing.py`, `api/media.py` und `services/media/v2_service.py` unverändert bleiben können.

- [ ] **Step 4: Gezielt testen**

Run: `PYTHONPATH=backend .venv-backend311/bin/pytest backend/app/tests/test_marketing_api.py backend/app/tests/test_forecast_decision_service.py -q`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/marketing_engine/opportunity_engine.py backend/app/services/marketing_engine/opportunity_engine_campaigns.py backend/app/services/marketing_engine/opportunity_engine_queries.py backend/app/tests/test_marketing_api.py backend/app/tests/test_forecast_decision_service.py
git commit -m "refactor: split marketing opportunity engine workflows"
```

### Task 6: Abschlussprüfung und Doku angleichen

**Files:**
- Modify: `ARCHITECTURE.md`
- Modify: `docs/superpowers/plans/2026-04-08-phase-3-spaghetti-cleanup.md`

- [ ] **Step 1: Architekturtext knapp nachziehen**

Erkläre in `ARCHITECTURE.md` kurz, dass `useMediaData.ts` jetzt als Kompatibilitäts-Barrel dient und `MarketingOpportunityEngine` in Hilfsmodule delegiert.

- [ ] **Step 2: Gezielte Abschluss-Checks laufen lassen**

Run:
- `cd frontend && CI=true npm test -- --watch=false src/features/media/useMediaData.test.tsx src/components/AppLayout.test.tsx src/components/cockpit/NowWorkspace.test.tsx`
- `cd frontend && npx tsc --noEmit`
- `PYTHONPATH=backend .venv-backend311/bin/pytest backend/app/tests/test_opportunity_engine_math.py backend/app/tests/test_marketing_api.py backend/app/tests/test_forecast_decision_service.py -q`

Expected: PASS

- [ ] **Step 3: Arbeitsstand dokumentieren**

Hake in dieser Plan-Datei die erledigten Schritte ab und notiere kurz verbleibende Rest-Risiken, falls ein Teil-Refactor bewusst verschoben wurde.

- [ ] **Step 4: Finaler Commit**

```bash
git add ARCHITECTURE.md docs/superpowers/plans/2026-04-08-phase-3-spaghetti-cleanup.md
git commit -m "docs: document media data and opportunity engine refactor"
```
