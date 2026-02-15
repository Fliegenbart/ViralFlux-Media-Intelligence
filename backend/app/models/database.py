from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class WastewaterData(Base):
    """RKI AMELAG Abwasserdaten."""
    __tablename__ = "wastewater_data"
    
    id = Column(Integer, primary_key=True, index=True)
    standort = Column(String, nullable=False)
    bundesland = Column(String, nullable=False)
    datum = Column(DateTime, nullable=False, index=True)
    virus_typ = Column(String, nullable=False)  # SARS-CoV-2, Influenza A, etc.
    viruslast = Column(Float)
    viruslast_normalisiert = Column(Float)
    vorhersage = Column(Float)
    obere_schranke = Column(Float)
    untere_schranke = Column(Float)
    einwohner = Column(Integer)
    unter_bg = Column(Boolean)  # Unter Bestimmungsgrenze
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_wastewater_date_virus', 'datum', 'virus_typ'),
        Index('idx_wastewater_location', 'standort', 'bundesland'),
    )


class WastewaterAggregated(Base):
    """Aggregierte bundesweite Abwasserdaten."""
    __tablename__ = "wastewater_aggregated"
    
    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    virus_typ = Column(String, nullable=False)
    n_standorte = Column(Integer)  # Anzahl Standorte
    anteil_bev = Column(Float)  # Anteil Bevölkerung
    viruslast = Column(Float)
    viruslast_normalisiert = Column(Float)
    vorhersage = Column(Float)
    obere_schranke = Column(Float)
    untere_schranke = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_agg_date_virus', 'datum', 'virus_typ'),
    )


class GrippeWebData(Base):
    """RKI GrippeWeb ARE/ILI Daten."""
    __tablename__ = "grippeweb_data"
    
    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    kalenderwoche = Column(Integer)
    erkrankung_typ = Column(String, nullable=False)  # ARE, ILI
    altersgruppe = Column(String)
    bundesland = Column(String)
    inzidenz = Column(Float)  # Pro 100.000 Einwohner
    anzahl_meldungen = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_grippeweb_date_type', 'datum', 'erkrankung_typ'),
    )


class AREKonsultation(Base):
    """RKI ARE-Konsultationsinzidenz — Arztbesuche wegen akuter Atemwegserkrankungen."""
    __tablename__ = "are_konsultation"

    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    kalenderwoche = Column(Integer, nullable=False)
    saison = Column(String, nullable=False)
    altersgruppe = Column(String, nullable=False)
    bundesland = Column(String, nullable=False)
    bundesland_id = Column(Integer)
    konsultationsinzidenz = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_are_konsult_date_age', 'datum', 'altersgruppe'),
        Index('idx_are_konsult_bundesland', 'bundesland', 'kalenderwoche'),
    )


class GoogleTrendsData(Base):
    """Google Trends Suchanfragen-Daten."""
    __tablename__ = "google_trends_data"
    
    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    keyword = Column(String, nullable=False)
    region = Column(String, default="DE")  # Deutschland
    interest_score = Column(Integer)  # 0-100
    is_partial = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_trends_date_keyword', 'datum', 'keyword'),
    )


class WeatherData(Base):
    """Wetterdaten von OpenWeather API."""
    __tablename__ = "weather_data"
    
    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    city = Column(String, nullable=False)
    temperatur = Column(Float)  # °C
    gefuehlte_temperatur = Column(Float)  # °C
    luftfeuchtigkeit = Column(Float)  # %
    luftdruck = Column(Float)  # hPa
    wetter_beschreibung = Column(String)
    wind_geschwindigkeit = Column(Float)  # m/s
    uv_index = Column(Float)  # UV-Index (0-11+)
    wolken = Column(Float)  # Cloud cover % (0-100)
    niederschlag_wahrscheinlichkeit = Column(Float)  # Probability of precipitation (0-1)
    regen_mm = Column(Float)  # Rain volume mm
    schnee_mm = Column(Float)  # Snow volume mm
    taupunkt = Column(Float)  # Dew point °C
    data_type = Column(String, default="CURRENT")  # CURRENT, DAILY_FORECAST, HOURLY_FORECAST
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_weather_date_city', 'datum', 'city'),
        Index('idx_weather_data_type', 'data_type'),
    )


class SchoolHolidays(Base):
    """Schulferien-Kalender."""
    __tablename__ = "school_holidays"
    
    id = Column(Integer, primary_key=True, index=True)
    bundesland = Column(String, nullable=False)
    ferien_typ = Column(String, nullable=False)  # Sommer, Winter, etc.
    start_datum = Column(DateTime, nullable=False)
    end_datum = Column(DateTime, nullable=False)
    jahr = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_holidays_dates', 'start_datum', 'end_datum'),
    )


class GanzimmunData(Base):
    """Optionale interne ganzimmun Daten (Testverkäufe, Ergebnisse)."""
    __tablename__ = "ganzimmun_data"
    
    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    test_typ = Column(String, nullable=False)
    anzahl_tests = Column(Integer)
    positive_ergebnisse = Column(Integer)
    region = Column(String)
    extra_data = Column(JSON)  # Flexibel für zusätzliche Daten
    created_at = Column(DateTime, default=datetime.utcnow)


class MLForecast(Base):
    """Machine Learning Prognosen."""
    __tablename__ = "ml_forecasts"
    
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    forecast_date = Column(DateTime, nullable=False, index=True)
    virus_typ = Column(String, nullable=False)
    predicted_value = Column(Float, nullable=False)
    lower_bound = Column(Float)
    upper_bound = Column(Float)
    confidence = Column(Float)  # 0-1
    model_version = Column(String)
    features_used = Column(JSON)  # Welche Features wurden verwendet
    
    __table_args__ = (
        Index('idx_forecast_date_virus', 'forecast_date', 'virus_typ'),
    )


class LLMRecommendation(Base):
    """LLM-generierte Empfehlungen."""
    __tablename__ = "llm_recommendations"
    
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    recommendation_text = Column(String, nullable=False)
    context_data = Column(JSON)  # Input-Daten für LLM
    confidence_score = Column(Float)
    suggested_action = Column(JSON)  # Strukturierte Aktion (z.B. Bestellung)
    approved = Column(Boolean, default=False)
    approved_by = Column(String)
    approved_at = Column(DateTime)
    modified_action = Column(JSON)  # Falls vom User angepasst
    
    forecast_id = Column(Integer, ForeignKey('ml_forecasts.id'))
    forecast = relationship("MLForecast")


class AuditLog(Base):
    """Audit Trail für ANNEx 22 Compliance."""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user = Column(String)
    action = Column(String, nullable=False)  # view, approve, modify, reject
    entity_type = Column(String)  # recommendation, forecast, etc.
    entity_id = Column(Integer)
    old_value = Column(JSON)
    new_value = Column(JSON)
    reason = Column(String)  # Begründung für Änderungen
    ip_address = Column(String)
    
    __table_args__ = (
        Index('idx_audit_timestamp', 'timestamp'),
        Index('idx_audit_user', 'user'),
    )


class InventoryLevel(Base):
    """Lagerbestände (ganzimmun)."""
    __tablename__ = "inventory_levels"

    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    test_typ = Column(String, nullable=False)
    aktueller_bestand = Column(Integer, nullable=False)
    min_bestand = Column(Integer)
    max_bestand = Column(Integer)
    empfohlener_bestand = Column(Integer)
    lieferzeit_tage = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OutbreakScore(Base):
    """Ganz Immun Outbreak Risk Score — Fusion Engine Ergebnis."""
    __tablename__ = "outbreak_scores"

    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    virus_typ = Column(String, nullable=False)
    final_risk_score = Column(Float, nullable=False)
    risk_level = Column(String)          # GREEN, YELLOW, RED
    leading_indicator = Column(String)
    confidence_level = Column(String)    # Sehr Hoch, Hoch, Mittel, Niedrig
    confidence_numeric = Column(Float)
    component_scores = Column(JSON)      # Aufschlüsselung aller Signale
    data_source_mode = Column(String)    # FULL, ESTIMATED_FROM_ORDERS
    phase = Column(String)               # A (heuristisch) oder B (KI-gesteuert)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_outbreak_date_virus', 'datum', 'virus_typ'),
    )


class MarketingOpportunity(Base):
    """Marketing/Sales Opportunities aus der MarketingOpportunityEngine."""
    __tablename__ = "marketing_opportunities"

    id = Column(Integer, primary_key=True, index=True)
    opportunity_id = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    opportunity_type = Column(String, nullable=False)
    status = Column(String, default="NEW")
    urgency_score = Column(Float, nullable=False)
    region_target = Column(JSON)
    trigger_source = Column(String)
    trigger_event = Column(String)
    trigger_details = Column(JSON)
    trigger_detected_at = Column(DateTime)
    target_audience = Column(JSON)
    sales_pitch = Column(JSON)
    suggested_products = Column(JSON)
    expires_at = Column(DateTime)
    exported_at = Column(DateTime)

    __table_args__ = (
        Index('idx_opportunity_type_status', 'opportunity_type', 'status'),
        Index('idx_opportunity_urgency', 'urgency_score'),
    )


class ProductCatalog(Base):
    """Produktkatalog für Marketing-Opportunity Produktempfehlungen."""
    __tablename__ = "product_catalog"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String)
    applicable_types = Column(JSON)
    applicable_conditions = Column(JSON)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class UploadHistory(Base):
    """Upload-Verlauf für Datenimport-Seite."""
    __tablename__ = "upload_history"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    upload_type = Column(String, nullable=False)  # "lab_results" or "orders"
    file_format = Column(String)  # "csv" or "xlsx"
    row_count = Column(Integer)
    date_range_start = Column(DateTime)
    date_range_end = Column(DateTime)
    status = Column(String, default="success")  # success, error, partial
    error_message = Column(String)
    summary = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class LabConfiguration(Base):
    """Gelernte Gewichte (Global oder pro Mandant)."""
    __tablename__ = "lab_configurations"

    id = Column(Integer, primary_key=True, index=True)
    is_global_default = Column(Boolean, default=False, index=True)
    weight_bio = Column(Float, default=0.35)
    weight_market = Column(Float, default=0.35)
    weight_psycho = Column(Float, default=0.10)
    weight_context = Column(Float, default=0.20)
    last_calibration_date = Column(DateTime, default=datetime.utcnow)
    calibration_source = Column(String)
    correlation_score = Column(Float)
    analyzed_days = Column(Integer)
