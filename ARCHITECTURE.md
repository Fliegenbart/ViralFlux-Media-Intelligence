# 🏗️ ViralFlux Media Intelligence - System Architecture

## Overview

ViralFlux Media Intelligence ist ein dreischichtiges System (Data, ML, Frontend) für predictive Pharma-Media-Steuerung mit folgenden Kernkomponenten:

```
┌─────────────────────────────────────────────────────────────┐
│                    DATA SOURCES LAYER                        │
│  RKI AMELAG │ GrippeWeb │ Notaufnahme │ BfArM │ Trends │ Weather │ Ferien │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────┐
│                  BACKEND / API LAYER                         │
│  ┌────────────────┐  ┌────────────────┐  ┌───────────────┐ │
│  │ Data Ingestion │  │  ML Pipeline   │  │ LLM Service   │ │
│  │   Services     │  │    (Prophet)   │  │    (vLLM)     │ │
│  └────────────────┘  └────────────────┘  └───────────────┘ │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         PostgreSQL + TimescaleDB                     │  │
│  │  (Zeitreihen-optimierte Speicherung)                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  FastAPI REST API                                            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           v
┌─────────────────────────────────────────────────────────────┐
│                   FRONTEND LAYER                             │
│  React + TypeScript + TailwindCSS + Recharts                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │Dashboard │  │Forecast  │  │ Recomm.  │  │ Settings │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 Tech Stack

### Backend
- **Framework:** FastAPI 0.109
- **Database:** PostgreSQL 15 + TimescaleDB
- **ML:** Prophet 1.1.5, scikit-learn
- **LLM:** vLLM (OpenAI-kompatibel, strikt lokal)
- **Data Processing:** Pandas, NumPy
- **API Clients:** pytrends, requests, aiohttp
- **Task Scheduling:** Celery Beat + Celery Worker

### Frontend
- **Framework:** React 18 + TypeScript
- **Styling:** TailwindCSS 3.4
- **Charts:** Recharts 2.10
- **State:** React Hooks + SWR
- **Routing:** React Router v6

### Infrastructure
- **Containerization:** Docker + Docker Compose
- **Web Server:** Nginx (Reverse Proxy)
- **Database:** TimescaleDB (PostgreSQL Extension)

---

## 📊 Datenfluss

### 1. Data Ingestion (täglich 6:00 Uhr)

```python
Celery Beat Schedule
    ↓
Celery Worker Task
    ↓
AmelagIngestionService.run_full_import()
    ├─ Fetch TSV from GitHub
    ├─ Parse & Validate
    ├─ Store in WastewaterData / WastewaterAggregated
    └─ Log success/failure

NotaufnahmeIngestionService.run_full_import()
    ├─ Fetch TSV from GitHub (Syndrome + Standorte)
    ├─ Parse & Validate
    ├─ Store in NotaufnahmeSyndromData / NotaufnahmeStandort
    └─ Log success/failure

GoogleTrendsService.run_full_import()
    ├─ Fetch via pytrends (Rate-Limited)
    ├─ Process keyword chunks (max 5/request)
    ├─ Store in GoogleTrendsData
    └─ 60s pause between requests

WeatherService.run_full_import()
    ├─ Fetch current & forecast (OpenWeather API)
    ├─ Process 5 cities
    ├─ Store in WeatherData
    └─ Update every 3 hours

SchoolHolidaysService.run_full_import()
    ├─ Load static data (2025-2026)
    ├─ Store in SchoolHolidays
    └─ Yearly update
```

### 2. ML Pipeline (nach Datenimport)

```python
ForecastService.run_forecasts_for_all_viruses()
    ↓
For each virus (Influenza A/B, SARS-CoV-2, RSV):
    ├─ prepare_training_data(lookback=180 days)
    │   ├─ Fetch: Wastewater, Trends, Weather, GrippeWeb, Notaufnahme, Holidays
    │   ├─ Feature Engineering: Lag-7, Lag-14, MA-7
    │   └─ Output: DataFrame with 15+ features
    │
    ├─ Prophet Model Training
    │   ├─ Add regressors: trends, weather, holidays, lags
    │   ├─ Fit model (daily, weekly, yearly seasonality)
    │   └─ Hyperparameters: changepoint_prior_scale=0.05
    │
    ├─ Generate Forecast (14 days)
    │   ├─ make_future_dataframe(periods=14)
    │   ├─ predict() with confidence intervals
    │   └─ Calculate feature importance (correlations)
    │
    └─ save_forecast(to Database)
        └─ Store in MLForecast table
```

### 3. LLM Recommendations (on-demand)

```python
LLMRecommendationService.generate_recommendation()
    ├─ Build context (forecast + inventory + trends)
    ├─ Generate prompt with structured data
    ├─ Call vLLM API (OpenAI-compatible, local)
    ├─ Parse response
    ├─ Extract structured action (increase/decrease/maintain)
    └─ save_recommendation(to Database)
        └─ Store in LLMRecommendation table
```

### 4. API Endpoints

Interne Legacy-Endpunkte sind JWT-geschützt. Schreibende bzw. Import-Endpunkte sind zusätzlich auf Admin-Rolle begrenzt.

```
GET  /api/v1/dashboard/overview
     └─ Aggregiert: Viruslast, Trends, ARE, Notaufnahme, SURVSTAT, Wetter

GET  /api/v1/dashboard/timeseries/{virus}
     └─ Historische Daten + Forecast

GET  /api/v1/forecast/{virus}
     └─ ML Prognose Details

POST /api/v1/recommendations/generate
     └─ Generiere LLM Empfehlung

POST /api/v1/recommendations/{id}/approve
     └─ Human Approval (ANNEx 22)

POST /api/v1/ingest/run-all
     └─ Manueller Vollimport aller Datenquellen

POST /api/v1/ingest/notaufnahme
     └─ Notaufnahmesurveillance Import (RKI/AKTIN)

POST /api/v1/ingest/survstat-local
     └─ Lokaler SURVSTAT Wochenimport (manuell)

POST /api/v1/calibration/simulate-market
     └─ Twin-Mode Markt-Check (RKI_ARE oder SURVSTAT Targets)
```

---

## 🗄️ Datenbankschema

### Zeitreihen-Tabellen (TimescaleDB Hypertables)

**wastewater_data** (Einzelstandorte)
- `id`, `standort`, `bundesland`, `datum`, `virus_typ`
- `viruslast`, `viruslast_normalisiert`, `vorhersage`
- `obere_schranke`, `untere_schranke`, `einwohner`
- Index: (datum, virus_typ), (standort, bundesland)

**wastewater_aggregated** (Bundesweit)
- `id`, `datum`, `virus_typ`, `n_standorte`, `anteil_bev`
- `viruslast`, `viruslast_normalisiert`, `vorhersage`
- Index: (datum, virus_typ)

**google_trends_data**
- `id`, `datum`, `keyword`, `region`, `interest_score`
- Index: (datum, keyword)

**weather_data**
- `id`, `datum`, `city`, `temperatur`, `luftfeuchtigkeit`
- `luftdruck`, `wetter_beschreibung`
- Index: (datum, city)

**grippeweb_data**
- `id`, `datum`, `kalenderwoche`, `erkrankung_typ`
- `altersgruppe`, `bundesland`, `inzidenz`
- Index: (datum, erkrankung_typ)

**notaufnahme_syndrome_data**
- `id`, `datum`, `ed_type`, `age_group`, `syndrome`
- `relative_cases`, `relative_cases_7day_ma`, `expected_value`
- `expected_lowerbound`, `expected_upperbound`, `ed_count`
- Index: (datum, syndrome), (syndrome, ed_type, age_group)

**notaufnahme_standorte**
- `id`, `ik_number`, `ed_name`, `ed_type`, `level_of_care`
- `state`, `state_id`, `latitude`, `longitude`
- Index: (ik_number), (state, ed_type)

**survstat_weekly_data**
- `id`, `week_label`, `week_start`, `year`, `week`
- `bundesland`, `disease`, `incidence`, `source_file`
- Index: (week_label, bundesland), (disease, week_start)

### ML & LLM Tabellen

**ml_forecasts**
- `id`, `created_at`, `forecast_date`, `virus_typ`
- `predicted_value`, `lower_bound`, `upper_bound`
- `confidence`, `model_version`, `features_used` (JSON)

**llm_recommendations**
- `id`, `recommendation_text`, `context_data` (JSON)
- `suggested_action` (JSON), `confidence_score`
- `approved`, `approved_by`, `approved_at`
- `modified_action` (JSON)
- Foreign Key → `ml_forecasts(id)`

**audit_logs** (ANNEx 22 Compliance)
- `id`, `timestamp`, `user`, `action`
- `entity_type`, `entity_id`, `old_value`, `new_value`
- `reason`, `ip_address`

---

## 🤖 ML Model Details

### Prophet Configuration

```python
model = Prophet(
    daily_seasonality=True,      # Tägliche Muster
    weekly_seasonality=True,     # Wochenmuster (Wochenende)
    yearly_seasonality=True,     # Saisonale Grippe-Wellen
    changepoint_prior_scale=0.05, # Flexibilität für Trend-Änderungen
    interval_width=0.95          # 95% Konfidenzintervall
)

# Regressoren
model.add_regressor('trends_score')        # Google Trends
model.add_regressor('are_inzidenz')        # GrippeWeb ARE
model.add_regressor('temperatur')          # Wetter
model.add_regressor('luftfeuchtigkeit')
model.add_regressor('schulferien')         # Binär
model.add_regressor('viruslast_lag7')      # Autoregressive
model.add_regressor('viruslast_lag14')
model.add_regressor('trends_ma7')          # Moving Average
```

### Feature Engineering

**Lag Features:**
- `viruslast_lag7`: Viruslast vor 7 Tagen
- `viruslast_lag14`: Viruslast vor 14 Tagen

**Moving Averages:**
- `viruslast_ma7`: 7-Tage-Durchschnitt
- `trends_ma7`: Trends 7-Tage-Durchschnitt

**Binary Features:**
- `schulferien`: 1 wenn Ferien, sonst 0

**Normalization:**
- Temperatur: -10°C bis 40°C
- Luftfeuchtigkeit: 0-100%
- Trends: 0-100

---

## 🔐 Security & Compliance

### ANNEx 22 Compliance

**Transparency:**
- Alle ML-Entscheidungen sind erklärbar
- Feature Importance wird gespeichert
- Model Version Tracking

**Human Oversight:**
- Keine automatischen Bestellungen
- Alle Empfehlungen müssen approved werden
- User kann Empfehlung modifizieren

**Audit Trail:**
- Vollständige Protokollierung in `audit_logs`
- Who, What, When, Why
- Unveränderbar (Append-Only)

**Data Privacy:**
- DSGVO-konform
- Lokale Verarbeitung (kein Cloud-LLM)
- vLLM läuft lokal auf eigenem Server

**API Access Controls:**
- Interne Dashboard-, Inventory-, Recommendation-, Map-, Ordering- und Data-Import-Endpunkte erfordern JWT-Authentifizierung
- Schreibende/administrative Aktionen erfordern Admin-Rolle
- `/api/v1/outbreak-score/peix-score` bleibt bewusst öffentlich für die Landing-Page

**Login Protection:**
- `/api/auth/login` ist rate-limitiert
- Nach 5 Fehlversuchen wird der Login-Key für 15 Minuten gesperrt
- Erfolgreicher Login setzt zusätzlich ein `httpOnly` Session-Cookie für Browser-Sessions
- Das Frontend speichert kein lesbares JWT mehr in `localStorage` oder `sessionStorage`

**Session Flow:**
- Browser-Requests laufen standardmäßig mit Cookie-Credentials
- `/api/auth/session` prüft nach Reloads, ob noch eine gültige Session existiert
- `/api/auth/logout` löscht das Session-Cookie serverseitig aus dem Browser-Kontext

---

## 📈 Performance Optimizations

### Database
- TimescaleDB Hypertables für Zeitreihen
- Chunk Size: 7 days
- Compression nach 30 Tagen
- Indexes auf häufige Queries

### API
- Connection Pooling (SQLAlchemy)
- Async Endpoints (FastAPI)
- Rate Limiting (100 req/min)
- Caching (TTL: 1 hour)

### Frontend
- Code Splitting (React.lazy)
- SWR für Data Fetching (Auto-Revalidate)
- Memoization (useMemo, useCallback)
- Production Build Optimierung

---

## 🚀 Deployment Architecture

### Production Setup (Hetzner)

```
Internet
    │
    v
┌───────────────┐
│    Nginx      │  Port 80/443 (SSL)
│ Reverse Proxy │
└───────┬───────┘
        │
        ├──────────────────┐
        │                  │
        v                  v
┌──────────────┐   ┌──────────────┐
│   Frontend   │   │   Backend    │
│  (React)     │   │  (FastAPI)   │
│  Port 3000   │   │  Port 8000   │
└──────────────┘   └───────┬──────┘
                           │
                           v
                   ┌───────────────┐
                   │  PostgreSQL   │
                   │ + TimescaleDB │
                   │  Port 5432    │
                   └───────────────┘

┌──────────────────────┐
│  vLLM (lokal)        │
│  eigener Endpoint    │
│  z. B. host.docker.  │
│  internal:8001/v1    │
└──────────────────────┘
```

### Docker Compose Services

1. **db** (TimescaleDB)
   - Image: `timescale/timescaledb:latest-pg15`
   - Volume: `postgres_data`
   - Health Check: `pg_isready`

2. **backend** (FastAPI)
   - Build: `Dockerfile.backend`
   - Depends: db
   - Environment: .env
   - Restart: always

3. **frontend** (React)
   - Development Build: `Dockerfile.frontend.dev`
   - Production Build: `Dockerfile.frontend`
   - Depends: backend
   - Node-Dev-Server für Entwicklung, statischer Build mit nginx für Produktion

4. **nginx** (Reverse Proxy)
   - Profile: production
   - SSL/TLS Termination
   - Rate Limiting
   - Gzip Compression

---

## 🔄 Data Update Schedule

```
┌─────────────────────────────────────────┐
│        Automatisierte Updates           │
├─────────────────────────────────────────┤
│  06:00  RKI AMELAG Import               │
│  06:10  RKI GrippeWeb Import            │
│  06:15  RKI/AKTIN Notaufnahme Import    │
│  06:20  Google Trends Import            │
│  06:30  Weather Update                  │
│  07:00  ML Forecasts Generation         │
│  03:00  Database Backup                 │
│  Alle 3h  Weather Update (Forecast)     │
└─────────────────────────────────────────┘
```

---

## 📊 Monitoring & Logging

### Health Checks
- `/health` → Database + API Status
- `/api/v1/status` → Data Freshness (nur authentifiziert)

### Logging
- Format: JSON (structured)
- Level: INFO (Production), DEBUG (Development)
- Storage: Docker volumes
- Rotation: Daily

### Metrics (geplant)
- Prometheus Client
- Grafana Dashboards
- Alerting via Email/Slack

---

**Made with ❤️ for smarter healthcare decisions**
