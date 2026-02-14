# 🧪 LabPulse Pro

**Intelligentes Frühwarnsystem für Labordiagnostik mit KI-gestützter Bedarfsprognose**

## 📋 Überblick

LabPulse Pro ist ein professionelles Prognosesystem für Labordiagnostik-Unternehmen, das durch die Kombination von Abwasserdaten, Krankheitsmeldungen, Google Trends und Wetterdaten einen 14-Tage-Vorlauf für die Bedarfsplanung von Testkits ermöglicht.

### Kernfeatures

- 📊 **Multi-Source Data Integration**: RKI Abwasserdaten, GrippeWeb, Google Trends, Wetterdaten, Schulferien
- 🤖 **Predictive Analytics**: Prophet ML-Modell mit Multi-Variate-Features
- 🧠 **LLM-Empfehlungen**: Ollama-gestützte, natürlichsprachige Handlungsempfehlungen
- 🎯 **14-Tage-Vorlauf**: Früherkennung durch Abwasser-Surveillance
- ✅ **ANNEx 22 Compliant**: Human-in-the-Loop, vollständiger Audit Trail
- 📈 **Professional Dashboard**: React-basierte, moderne UI

## 🏗️ Architektur

```
┌─────────────────────────────────────────────────────┐
│              Datenquellen                            │
│  RKI AMELAG | GrippeWeb | Google Trends | Weather   │
└────────────────────┬────────────────────────────────┘
                     │
                     v
┌─────────────────────────────────────────────────────┐
│        Backend (FastAPI + PostgreSQL)                │
│  • Data Ingestion Pipeline                           │
│  • Prophet ML Forecasting                            │
│  • Ollama LLM Integration                            │
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
- Ollama Server (läuft bereits auf Hetzner)

### Installation

```bash
# Repository klonen
git clone <your-repo-url>
cd virusradar-pro

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

### 3. Google Trends
- **Library**: pytrends
- **Keywords**: Erkältung, Grippe, Schnupfen, Fieber, etc.
- **Geo**: Deutschland

### 4. OpenWeather API
- **Daten**: Temperatur, Luftfeuchtigkeit, Wettervorhersage
- **Relevanz**: Einfluss auf Atemwegserkrankungen

### 5. Schulferien
- **Quelle**: API oder statische Daten
- **Relevanz**: Erkrankungsrückgang in Ferienzeiten

### 6. Interne ganzimmun-Daten (Optional)
- **Schnittstelle vorbereitet**: CSV/API Import
- **Daten**: Historische Testverkäufe, Ergebnisse

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

### Ollama LLM
- **Modell**: Läuft auf deinem Hetzner Server
- **Funktion**: Natürlichsprachige Empfehlungen
- **Kontext**: Aktuelle Daten + ML-Prognose + Lagerbestand

## 📁 Projektstruktur

```
virusradar-pro/
├── backend/
│   ├── app/
│   │   ├── api/          # API Endpoints
│   │   ├── core/         # Config, Security
│   │   ├── models/       # SQLAlchemy Models
│   │   ├── services/     # Business Logic
│   │   │   ├── data_ingest/    # RKI, Trends, Weather
│   │   │   ├── ml/             # Prophet, Training
│   │   │   └── llm/            # Ollama Integration
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
OLLAMA_URL=http://your-hetzner-server:11434

# Security
SECRET_KEY=<generate-secure-key>

# Optional: ganzimmun Data
GANZIMMUN_API_URL=<optional>
GANZIMMUN_API_KEY=<optional>
```

## 🧪 Testing

```bash
# Backend Tests
cd backend
pytest

# Frontend Tests
cd frontend
npm test
```

## 📦 Deployment auf Hetzner

```bash
# SSH auf Server
ssh user@your-hetzner-server

# Repository klonen
git clone <repo-url>
cd virusradar-pro

# Produktion starten
docker-compose -f docker-compose.prod.yml up -d

# SSL mit Let's Encrypt
./scripts/setup-ssl.sh your-domain.de
```

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

## 🤝 Support & Contribution

Entwickelt für **ganzimmun** als professionelles Frühwarnsystem.

## 📄 Lizenz

Proprietary - © 2026 ganzimmun

---

**Made with ❤️ for smarter healthcare decisions**
