import requests
import json
from datetime import datetime
from sqlalchemy.orm import Session
import logging
from typing import Dict, List

from app.core.config import get_settings
from app.models.database import MLForecast, LLMRecommendation, InventoryLevel

logger = logging.getLogger(__name__)
settings = get_settings()


class OllamaRecommendationService:
    """Service für LLM-gestützte Bedarfsempfehlungen via Ollama."""
    
    def __init__(self, db: Session):
        self.db = db
        self.ollama_url = settings.OLLAMA_URL
        self.model = settings.OLLAMA_MODEL
    
    def generate_recommendation(
        self,
        forecast_data: Dict,
        inventory_data: Dict
    ) -> Dict:
        """
        Generiere natürlichsprachige Empfehlung basierend auf Prognose und Lagerbestand.
        
        Args:
            forecast_data: ML-Prognose-Daten
            inventory_data: Aktuelle Lagerbestände
        
        Returns:
            Dict mit Empfehlung und strukturierter Aktion
        """
        logger.info("Generating LLM recommendation...")
        
        # Kontext für LLM zusammenstellen
        context = self._build_context(forecast_data, inventory_data)
        
        # Prompt für Ollama
        prompt = self._build_prompt(context)
        
        # Ollama API Call
        try:
            response = self._call_ollama(prompt)
            
            # Strukturierte Aktion extrahieren
            suggested_action = self._extract_action(response, forecast_data, inventory_data)
            
            result = {
                "recommendation_text": response,
                "context_data": context,
                "suggested_action": suggested_action,
                "confidence_score": self._calculate_confidence(forecast_data),
                "timestamp": datetime.utcnow()
            }
            
            logger.info("LLM recommendation generated successfully")
            return result
            
        except Exception as e:
            logger.error(f"Error generating recommendation: {e}")
            return {
                "error": str(e),
                "recommendation_text": "Fehler bei der Empfehlungsgenerierung.",
                "timestamp": datetime.utcnow()
            }
    
    def _build_context(self, forecast_data: Dict, inventory_data: Dict) -> Dict:
        """Baue Kontext-Informationen für LLM."""
        return {
            "virus_typ": forecast_data.get('virus_typ'),
            "aktuelle_viruslast": forecast_data.get('current_viral_load'),
            "trend": forecast_data.get('trend'),  # steigend, fallend, stabil
            "prognose_7_tage": forecast_data.get('forecast_7d'),
            "prognose_14_tage": forecast_data.get('forecast_14d'),
            "confidence": forecast_data.get('confidence'),
            "aktueller_bestand": inventory_data.get('current_stock'),
            "min_bestand": inventory_data.get('min_stock'),
            "lieferzeit_tage": inventory_data.get('lead_time_days'),
            "historischer_verbrauch": inventory_data.get('avg_consumption'),
            "google_trends": forecast_data.get('trends_score'),
            "temperatur": forecast_data.get('temperature'),
            "schulferien": forecast_data.get('school_holidays')
        }
    
    def _build_prompt(self, context: Dict) -> str:
        """Baue Prompt für Ollama."""
        prompt = f"""Du bist ein Experte für Labordiagnostik und hilfst dabei, Lagerbestände zu optimieren.

Analysiere folgende Daten und gib eine präzise Handlungsempfehlung:

**Aktueller Status:**
- Virustyp: {context['virus_typ']}
- Aktuelle Viruslast im Abwasser: {context['aktuelle_viruslast']:.1f} Genkopien/L
- Trend: {context['trend']}

**Prognose:**
- In 7 Tagen: {context['prognose_7_tage']:.1f} Genkopien/L (Änderung: {((context['prognose_7_tage'] / context['aktuelle_viruslast']) - 1) * 100:.1f}%)
- In 14 Tagen: {context['prognose_14_tage']:.1f} Genkopien/L (Änderung: {((context['prognose_14_tage'] / context['aktuelle_viruslast']) - 1) * 100:.1f}%)
- Konfidenz: {context['confidence'] * 100:.0f}%

**Lagerbestand:**
- Aktuell: {context['aktueller_bestand']} Tests
- Mindestbestand: {context['min_bestand']} Tests
- Lieferzeit: {context['lieferzeit_tage']} Tage
- Ø Verbrauch: {context['historischer_verbrauch']} Tests/Woche

**Zusatzinformationen:**
- Google Trends Score: {context['google_trends']}/100
- Temperatur: {context['temperatur']:.1f}°C
- Schulferien: {"Ja" if context['schulferien'] else "Nein"}

**Aufgabe:**
Erstelle eine fundierte Empfehlung mit:
1. Kurzer Situationsanalyse (2-3 Sätze)
2. Konkreter Handlungsempfehlung (z.B. "Bestellung von X Tests")
3. Begründung basierend auf den Daten
4. Zeitrahmen für die Umsetzung

Antworte professionell und präzise. Fokussiere auf die wichtigsten Erkenntnisse.
"""
        return prompt
    
    def _call_ollama(self, prompt: str) -> str:
        """Rufe Ollama API auf."""
        logger.info(f"Calling Ollama at {self.ollama_url}")
        
        try:
            url = f"{self.ollama_url}/api/generate"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_tokens": 500
                }
            }
            
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            return data.get('response', '')
            
        except Exception as e:
            logger.error(f"Ollama API call failed: {e}")
            raise
    
    def _extract_action(
        self, 
        llm_response: str, 
        forecast_data: Dict,
        inventory_data: Dict
    ) -> Dict:
        """
        Extrahiere strukturierte Aktion aus LLM-Antwort.
        
        Vereinfachte Heuristik - könnte durch JSON-Output von LLM ersetzt werden.
        """
        action = {
            "action_type": "maintain",  # maintain, increase, decrease
            "recommended_quantity": inventory_data.get('current_stock'),
            "priority": "normal",  # low, normal, high, critical
            "reason": "Basierend auf LLM-Analyse"
        }
        
        # Heuristik basierend auf Prognose-Trend
        forecast_change = (
            forecast_data.get('forecast_14d', 0) - 
            forecast_data.get('current_viral_load', 1)
        ) / forecast_data.get('current_viral_load', 1)
        
        if forecast_change > 0.3:  # >30% Anstieg
            action['action_type'] = 'increase'
            action['recommended_quantity'] = int(
                inventory_data.get('current_stock', 0) * 1.5
            )
            action['priority'] = 'high'
            action['reason'] = 'Signifikanter Anstieg der Viruslast prognostiziert'
            
        elif forecast_change < -0.3:  # >30% Rückgang
            action['action_type'] = 'decrease'
            action['recommended_quantity'] = int(
                inventory_data.get('current_stock', 0) * 0.7
            )
            action['priority'] = 'low'
            action['reason'] = 'Rückgang der Viruslast erwartet'
        
        return action
    
    def _calculate_confidence(self, forecast_data: Dict) -> float:
        """Berechne Konfidenz der Empfehlung."""
        # Basiert auf ML-Konfidenz und Datenvollständigkeit
        ml_confidence = forecast_data.get('confidence', 0.5)
        data_quality = forecast_data.get('data_quality', 0.8)
        
        return min(ml_confidence * data_quality, 1.0)
    
    def save_recommendation(self, recommendation_data: Dict, forecast_id: int = None):
        """Speichere Empfehlung in Datenbank."""
        logger.info("Saving LLM recommendation to database...")
        
        recommendation = LLMRecommendation(
            recommendation_text=recommendation_data['recommendation_text'],
            context_data=recommendation_data['context_data'],
            confidence_score=recommendation_data['confidence_score'],
            suggested_action=recommendation_data['suggested_action'],
            forecast_id=forecast_id
        )
        
        self.db.add(recommendation)
        self.db.commit()
        self.db.refresh(recommendation)
        
        logger.info(f"Recommendation saved with ID: {recommendation.id}")
        return recommendation
    
    def approve_recommendation(
        self,
        recommendation_id: int,
        approved_by: str,
        modified_action: Dict = None,
        reason: str = None
    ):
        """
        Genehmige oder modifiziere eine Empfehlung (ANNEx 22 Compliance).
        
        Args:
            recommendation_id: ID der Empfehlung
            approved_by: User der genehmigt
            modified_action: Optional: Modifizierte Aktion
            reason: Optional: Begründung für Änderungen
        """
        logger.info(f"Approving recommendation {recommendation_id}")
        
        recommendation = self.db.query(LLMRecommendation).filter(
            LLMRecommendation.id == recommendation_id
        ).first()
        
        if not recommendation:
            raise ValueError(f"Recommendation {recommendation_id} not found")
        
        recommendation.approved = True
        recommendation.approved_by = approved_by
        recommendation.approved_at = datetime.utcnow()
        
        if modified_action:
            recommendation.modified_action = modified_action
        
        # Audit Log würde hier erstellt
        
        self.db.commit()
        logger.info(f"Recommendation {recommendation_id} approved by {approved_by}")
        
        return recommendation
