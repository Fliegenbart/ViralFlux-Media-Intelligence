# 🚀 Quick Start Guide - ViralFlux Media Intelligence

## 5-Minuten Setup

### 1. Repository klonen
```bash
git clone <your-repo-url>
cd viralflux-media
```

### 2. Umgebungsvariablen konfigurieren
```bash
cp .env.example .env
nano .env  # oder dein bevorzugter Editor
```

**Wichtig: Fülle diese Werte aus:**
- `OPENWEATHER_API_KEY` - Hole dir einen kostenlosen Key von [openweathermap.org](https://openweathermap.org/api)
- `OLLAMA_URL` - URL zu deinem Hetzner Server (z.B. `http://your-server:11434`)
- `SECRET_KEY` - Generiere mit: `openssl rand -hex 32`

### 3. Setup ausführen
```bash
./setup.sh
```

Das Script:
- ✅ Prüft alle Dependencies
- ✅ Erstellt Verzeichnisse
- ✅ Installiert Python & Node Pakete
- ✅ Startet Docker Container

### 4. Erste Schritte

**A) Öffne die API Docs:**
```
http://localhost:8000/docs
```

**B) Führe den ersten Datenimport durch:**

1. Gehe zu `/api/v1/ingest/run-all` (POST)
2. Klicke auf "Try it out" → "Execute"
3. Warte ~2-3 Minuten

Oder via curl:
```bash
curl -X POST http://localhost:8000/api/v1/ingest/run-all
```

**C) Öffne das Dashboard:**
```
http://localhost:3000
```

---

## Manueller Start (ohne setup.sh)

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
npm start
```

### Datenbank
```bash
docker-compose up -d db
```

---

## Täglicher Betrieb

### Container starten
```bash
docker-compose up -d
```

### Container stoppen
```bash
docker-compose down
```

### Logs anzeigen
```bash
# Alle Services
docker-compose logs -f

# Nur Backend
docker-compose logs -f backend

# Nur Frontend
docker-compose logs -f frontend
```

---

## Datenimport

### Automatischer Import (geplant)
Der automatische Import läuft täglich um 6:00 Uhr (konfigurierbar in .env)

### Manueller Import via API

**Alle Datenquellen:**
```bash
curl -X POST http://localhost:8000/api/v1/data/import/all
```

**Einzelne Quellen:**
```bash
# RKI Abwasser
curl -X POST http://localhost:8000/api/v1/data/import/amelag

# Google Trends
curl -X POST http://localhost:8000/api/v1/data/import/trends

# Wetter
curl -X POST http://localhost:8000/api/v1/data/import/weather

# Schulferien
curl -X POST http://localhost:8000/api/v1/data/import/holidays
```

---

## ML Prognosen erstellen

```bash
curl -X POST http://localhost:8000/api/v1/forecast/generate
```

---

## Troubleshooting

### Port bereits belegt
```bash
# Ändere Ports in docker-compose.yml
ports:
  - "8001:8000"  # Backend
  - "3001:3000"  # Frontend
```

### Datenbank-Verbindung fehlgeschlagen
```bash
# Prüfe ob Container läuft
docker ps

# Datenbank neu starten
docker-compose restart db

# Logs prüfen
docker-compose logs db
```

### Frontend startet nicht
```bash
# node_modules löschen und neu installieren
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### "Permission denied" beim Setup
```bash
chmod +x setup.sh
```

---

## Nützliche Befehle

### Datenbank-Shell öffnen
```bash
docker-compose exec db psql -U virusradar -d virusradar_db
```

### Backend Shell öffnen
```bash
docker-compose exec backend /bin/bash
```

### Alle Container und Volumes löschen (VORSICHT!)
```bash
docker-compose down -v
```

---

## Deployment auf Hetzner

Siehe vollständige Anleitung in `docs/DEPLOYMENT.md`

**Kurzversion:**
```bash
# Auf Server einloggen
ssh user@your-hetzner-server

# Repository klonen
git clone <repo-url>
cd viralflux-media

# Produktions-Setup
docker-compose -f docker-compose.prod.yml up -d

# SSL einrichten
./scripts/setup-ssl.sh your-domain.de
```

---

## Support

- 📚 Vollständige Dokumentation: `README.md`
- 🐛 Issues: GitHub Issues
- 📧 Kontakt: [deine-email]

---

**Made with ❤️ for smarter healthcare decisions**
