#!/bin/bash

# ViralFlux Media Intelligence - Setup Script
# Dieses Script richtet das komplette Projekt ein

set -e

echo "📡 ViralFlux Media Intelligence - Setup"
echo "=========================="
echo ""

# Farben für Output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Umgebungsvariablen prüfen
echo -e "${YELLOW}1. Prüfe Umgebungsvariablen...${NC}"
if [ ! -f .env ]; then
    echo "   Erstelle .env aus .env.example..."
    cp .env.example .env
    echo -e "   ${YELLOW}⚠️  Bitte .env mit deinen API-Keys bearbeiten!${NC}"
    echo "   - OPENWEATHER_API_KEY"
    echo "   - OLLAMA_URL"
    echo "   - SECRET_KEY (generiere mit: openssl rand -hex 32)"
    read -p "   Drücke Enter wenn du .env konfiguriert hast..."
else
    echo -e "   ${GREEN}✓ .env gefunden${NC}"
fi

# 2. Docker prüfen
echo -e "\n${YELLOW}2. Prüfe Docker Installation...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "   ${YELLOW}⚠️  Docker nicht gefunden. Bitte installiere Docker Desktop.${NC}"
    exit 1
fi
echo -e "   ${GREEN}✓ Docker gefunden${NC}"

if ! command -v docker-compose &> /dev/null; then
    echo -e "   ${YELLOW}⚠️  Docker Compose nicht gefunden.${NC}"
    exit 1
fi
echo -e "   ${GREEN}✓ Docker Compose gefunden${NC}"

# 3. Daten-Verzeichnisse erstellen
echo -e "\n${YELLOW}3. Erstelle Daten-Verzeichnisse...${NC}"
mkdir -p data/raw
mkdir -p data/raw/survstat
mkdir -p data/processed
echo -e "   ${GREEN}✓ Verzeichnisse erstellt${NC}"

# 4. Backend Dependencies installieren (lokal für Development)
echo -e "\n${YELLOW}4. Installiere Backend Dependencies...${NC}"
if command -v python3 &> /dev/null; then
    cd backend
    if [ ! -d "venv" ]; then
        echo "   Erstelle Virtual Environment..."
        python3 -m venv venv
    fi
    echo "   Aktiviere venv und installiere Pakete..."
    source venv/bin/activate
    pip install -r requirements.txt
    deactivate
    cd ..
    echo -e "   ${GREEN}✓ Backend Dependencies installiert${NC}"
else
    echo -e "   ${YELLOW}⚠️  Python3 nicht gefunden - überspringe lokale Installation${NC}"
fi

# 5. Frontend Dependencies installieren
echo -e "\n${YELLOW}5. Installiere Frontend Dependencies...${NC}"
if command -v npm &> /dev/null; then
    cd frontend
    npm install
    cd ..
    echo -e "   ${GREEN}✓ Frontend Dependencies installiert${NC}"
else
    echo -e "   ${YELLOW}⚠️  npm nicht gefunden - überspringe Frontend Setup${NC}"
fi

# 6. Docker Container starten
echo -e "\n${YELLOW}6. Starte Docker Container...${NC}"
docker-compose up -d db

# Warte auf Datenbank
echo "   Warte auf Datenbank..."
sleep 10

# Starte Backend und Frontend
docker-compose up -d backend frontend

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Setup erfolgreich abgeschlossen!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Die Anwendung läuft nun auf:"
echo "  🌐 Frontend:  http://localhost:3000"
echo "  🔧 Backend:   http://localhost:8000"
echo "  📚 API Docs:  http://localhost:8000/docs"
echo ""
echo "Nächste Schritte:"
echo "  1. Öffne http://localhost:8000/docs"
echo "  2. Führe den ersten Datenimport durch"
echo "  3. Öffne http://localhost:3000 für das Dashboard"
echo ""
echo "Logs anzeigen:"
echo "  docker-compose logs -f backend"
echo "  docker-compose logs -f frontend"
echo ""
echo "Stoppen:"
echo "  docker-compose down"
echo ""
