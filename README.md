# 📡 ViralFlux Media Intelligence

**Regionales PEIX-Mediatool für Virus-Frühwarnung und validierte Media-Entscheidungen mit GELO als Truth-Partner**

## 📋 Überblick

ViralFlux Media Intelligence ist ein datengetriebenes Frühwarn- und Decision-System für PEIX. Die Plattform kombiniert AMELAG, SurvStat und weitere RKI-Signale mit Kontextdaten, um regionale Viruswellen in den nächsten 3 bis 7 Tagen früher zu erkennen und daraus priorisierte Media-Entscheidungen abzuleiten.

Das System ist zweistufig aufgebaut:

- **Epidemiologischer Forecast**: regionale Früherkennung pro Viruslinie
- **Business-Gate**: separate kommerzielle Freigabe auf Basis echter Outcome-Daten

GELO ist der erste Truth-Partner für diese zweite Ebene. Echte Sales-, Order- und Media-Daten werden nicht als Ersatz für die Epidemiologie genutzt, sondern als Validierung dafür, ob aus einem epidemiologischen Signal bereits eine belastbare Budgetentscheidung werden darf.

### Kernfeatures

- 📊 **Signal Fusion**: AMELAG, SurvStat, GrippeWeb, ARE, Notaufnahme, Wetter, Ferien, Pollen, Trends
- 🎯 **3- bis 7-Tage-Frühwarnung**: regionale Viruswellen vor klassischer Marktreaktion erkennen
- 🗺️ **Bundesland-Forecasts**: priorisierte Regionen, Virus-Portfolio und Watch-/Prepare-/Activate-Logik
- 🧪 **Point-in-Time ML**: leakage-sichere as-of Datasets, Walk-forward-Backtests, Quality Gates
- 🧾 **Business-Gate**: PEIX/GELO-Freigabelogik mit Truth-Readiness, Holdout- und Evidenzstatus
- 📈 **Decision Cockpit**: operative Entscheidungsansicht, Wave-Verlauf, Quellenfrische und Portfolio-Ranking

## 🏗️ Architektur

```
┌─────────────────────────────────────────────────────┐
│              Datenquellen                            │
│  RKI AMELAG | GrippeWeb | Notaufnahme | SURVSTAT | BfArM | DWD | Trends │
└────────────────────┬────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────┐
│        Backend (FastAPI + PostgreSQL)                │
│  • Data Ingestion Pipeline                           │
│  • Prophet ML Forecasting                            │
│  • vLLM (OpenAI-kompatibel) LLM Integration          │
│  • TimescaleDB für Zeitreihen                        │
└────────────────────┬────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────┐
│        Frontend (React + TypeScript)                 │
│  • Real-time Dashboard                               │
│  • Interactive Forecasts                             │
│  • Human-Approval Workflow                           │
└─────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Voraussetzungen

- Docker & Docker Compose
- Node.js 18+
- Python 3.11+
- vLLM Server (OpenAI-kompatibel, läuft lokal auf Hetzner)

### Installation

```bash
# Repository klonen
git clone <your-repo-url>
cd viralflux-media

# Umgebungsvariablen konfigurieren
cp .env.example .env
# Bearbeite .env mit deinen API-Keys

# Mit Docker starten
docker-compose up -d

# Frontend Development
cd frontend
npm install
npm run dev

# Backend Development
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Die App läuft dann auf:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## 🎙️ Elevator Pitch

\"ViralFlux ist ein PEIX-Mediatool, das regionale Viruswellen 3 bis 7 Tage früher sichtbar macht und daraus priorisierte Media-Entscheidungen ableitet. Die Epidemiologie kommt aus AMELAG, SurvStat und weiteren RKI-Signalen, die kommerzielle Validierung aus echten GELO-Outcome-Daten. So entsteht nicht nur ein besseres Radar, sondern ein messbar belastbarer Entscheidungsprozess für regionale Aktivierung.\"

## 📊 Datenquellen

### 1. RKI AMELAG (Abwassersurveillance)
- **Quelle**: `github.com/robert-koch-institut/Abwassersurveillance_AMELAG`
- **Update**: Wöchentlich
- **Daten**: SARS-CoV-2, Influenza A/B, RSV
- **Vorlauf**: ~14 Tage

### 2. RKI GrippeWeb
- **Quelle**: `github.com/robert-koch-institut/GrippeWeb_Daten_des_Wochenberichts`
- **Update**: Wöchentlich
- **Daten**: ARE/ILI Inzidenzen nach Region und Alter

### 3. RKI/AKTIN Notaufnahmesurveillance
- **Quelle**: `github.com/robert-koch-institut/Daten_der_Notaufnahmesurveillance`
- **Update**: Täglich (bis Vorvortag)
- **Daten**: ARI, SARI, ILI, COVID, GI (relativer Anteil + Erwartungswerte)

### 4. RKI SURVSTAT (manueller Weekly Import)
- **Quelle**: SURVSTAT Exportdateien (CSV/TSV, UTF-16)
- **Update**: Manuell, Woche für Woche
- **Daten**: Meldeinzidenzen nach Bundesland + Krankheitsbild (inkl. Gesamt)
- **Import**: `POST /api/v1/ingest/survstat-local?folder_path=/pfad/zum/ordner`

### 5. Google Trends
- **Library**: pytrends
- **Keywords**: Erkältung, Grippe, Schnupfen, Fieber, etc.
- **Geo**: Deutschland

### 6. OpenWeather API
- **Daten**: Temperatur, Luftfeuchtigkeit, Wettervorhersage
- **Relevanz**: Einfluss auf Atemwegserkrankungen

### 7. Schulferien
- **Quelle**: API oder statische Daten
- **Relevanz**: Erkrankungsrückgang in Ferienzeiten

### 8. GELO Outcome- und Truth-Daten
- **Schnittstelle vorbereitet**: CSV/API Import
- **Daten**: Sales, Orders, Spend, Kampagnenstarts, Kanäle, regionale Holdout-Zuordnung
- **Rolle**: Business-Validierung, nicht Ersatz für epidemiologische Truth

## 🤖 ML Pipeline

### Prophet Forecasting Model
- **Features**: 
  - Viruslast (Abwasser)
  - Google Trends Score
  - ARE/ILI Inzidenzen
  - Temperatur, Luftfeuchtigkeit
  - Schulferien (Binär)
  - Lag Features (7, 14 Tage)
  
- **Output**: 
  - 14-Tage-Prognose
  - Confidence Intervals (95%)
  - Feature Importance

### vLLM (lokal, OpenAI-kompatibel)
- **Modell**: Läuft auf deinem Hetzner Server
- **Funktion**: Agentur- und Kundenbriefings in natürlicher Sprache
- **Kontext**: Aktuelle Signale + Prognose + Aktivierungsfenster

## 📁 Projektstruktur

```
viralflux-media/
├── backend/
│   ├── app/
│   │   ├── api/          # API Endpoints
│   │   ├── core/         # Config, Security
│   │   ├── models/       # SQLAlchemy Models
│   │   ├── services/     # Business Logic
│   │   │   ├── data_ingest/    # RKI (AMELAG/GrippeWeb/Notaufnahme/SURVSTAT), Trends, Weather
│   │   │   ├── ml/             # Prophet, Training
│   │   │   └── llm/            # vLLM Integration
│   │   └── db/           # Database Setup
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/   # React Components
│   │   ├── pages/        # Pages
│   │   ├── services/     # API Calls
│   │   └── types/        # TypeScript Types
│   └── package.json
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
├── data/
│   ├── raw/              # Rohdaten
│   └── processed/        # Verarbeitete Daten
├── docker-compose.yml
└── .env.example
```

## 🔐 Umgebungsvariablen

```env
# Database
POSTGRES_USER=virusradar
POSTGRES_PASSWORD=<strong-password>
POSTGRES_DB=virusradar_db

# APIs
OPENWEATHER_API_KEY=<your-key>
VLLM_BASE_URL=http://localhost:8000/v1

# Security
SECRET_KEY=<generate-secure-key>

# Optional: Kundendaten
GANZIMMUN_API_URL=<optional>
GANZIMMUN_API_KEY=<optional>
```

## 🧪 Testing

```bash
# Backend Tests
cd backend
python3 -m pytest

# Frontend Tests
cd frontend
npm test -- --passWithNoTests
```

## 📦 Deployment auf Hetzner

```bash
# SSH auf Server
ssh user@your-hetzner-server

# Repository klonen
git clone <repo-url>
cd viralflux-media

# Produktion starten
docker-compose -f docker-compose.prod.yml up -d
```

Vollständige Produktionsanleitung: `DEPLOY.md`

## 📈 ANNEx 22 Compliance

- ✅ **Transparency**: Alle ML-Entscheidungen sind erklärbar
- ✅ **Human Oversight**: Keine automatischen Bestellungen
- ✅ **Audit Trail**: Vollständige Protokollierung
- ✅ **Data Privacy**: DSGVO-konform, lokale Verarbeitung

## 🛠️ Entwicklung

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## 📝 API Dokumentation

Siehe: http://localhost:8000/docs (Swagger UI)

Hauptendpoints:
- `GET /api/v1/dashboard` - Dashboard-Daten
- `GET /api/v1/forecast` - ML-Prognose
- `POST /api/v1/recommendations` - LLM-Empfehlung
- `GET /api/v1/data/wastewater` - Abwasserdaten
- `GET /api/v1/data/trends` - Google Trends
- `POST /api/v1/ingest/notaufnahme` - Notaufnahmesurveillance Import
- `POST /api/v1/ingest/survstat-local` - Lokaler SURVSTAT Wochenimport
- `POST /api/v1/calibration/simulate-market` - Twin-Mode Markt-Check (RKI ARE/SURVSTAT)

## 🤝 Support & Contribution

Entwickelt als **PEIX Service-Plattform** für Pharma- und Healthcare-Marken.

## 📄 Lizenz

Proprietary - © 2026 PEIX / ViralFlux

---

**Made with ❤️ for smarter healthcare decisions**
