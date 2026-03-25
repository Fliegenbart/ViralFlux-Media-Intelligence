from datetime import UTC, datetime

from sqlalchemy import Column, Integer, LargeBinary, String, Float, DateTime, Boolean, JSON, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _utc_now() -> datetime:
    # Keep existing naive-UTC storage semantics, but avoid the deprecated utcnow() API.
    return datetime.now(UTC).replace(tzinfo=None)


class WastewaterData(Base):
    """RKI AMELAG Abwasserdaten."""
    __tablename__ = "wastewater_data"
    
    id = Column(Integer, primary_key=True, index=True)
    standort = Column(String, nullable=False)
    bundesland = Column(String, nullable=False)
    datum = Column(DateTime, nullable=False, index=True)
    available_time = Column(DateTime, nullable=True, index=True)
    virus_typ = Column(String, nullable=False)  # SARS-CoV-2, Influenza A, etc.
    viruslast = Column(Float)
    viruslast_normalisiert = Column(Float)
    vorhersage = Column(Float)
    obere_schranke = Column(Float)
    untere_schranke = Column(Float)
    einwohner = Column(Integer)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    unter_bg = Column(Boolean)  # Unter Bestimmungsgrenze
    created_at = Column(DateTime, default=_utc_now)

    __table_args__ = (
        Index('idx_wastewater_date_virus', 'datum', 'virus_typ'),
        Index('idx_wastewater_location', 'standort', 'bundesland'),
    )


class WastewaterAggregated(Base):
    """Aggregierte bundesweite Abwasserdaten."""
    __tablename__ = "wastewater_aggregated"
    
    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    available_time = Column(DateTime, nullable=True, index=True)
    virus_typ = Column(String, nullable=False)
    n_standorte = Column(Integer)  # Anzahl Standorte
    anteil_bev = Column(Float)  # Anteil Bevölkerung
    viruslast = Column(Float)
    viruslast_normalisiert = Column(Float)
    vorhersage = Column(Float)
    obere_schranke = Column(Float)
    untere_schranke = Column(Float)
    created_at = Column(DateTime, default=_utc_now)
    
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
    created_at = Column(DateTime, default=_utc_now)
    
    __table_args__ = (
        Index('idx_grippeweb_date_type', 'datum', 'erkrankung_typ'),
    )


class AREKonsultation(Base):
    """RKI ARE-Konsultationsinzidenz — Arztbesuche wegen akuter Atemwegserkrankungen."""
    __tablename__ = "are_konsultation"

    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    available_time = Column(DateTime, nullable=True, index=True)
    kalenderwoche = Column(Integer, nullable=False)
    saison = Column(String, nullable=False)
    altersgruppe = Column(String, nullable=False)
    bundesland = Column(String, nullable=False)
    bundesland_id = Column(Integer)
    konsultationsinzidenz = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=_utc_now)

    __table_args__ = (
        Index('idx_are_konsult_date_age', 'datum', 'altersgruppe'),
        Index('idx_are_konsult_bundesland', 'bundesland', 'kalenderwoche'),
    )


class NotaufnahmeSyndromData(Base):
    """RKI/AKTIN Notaufnahmesurveillance Zeitreihen (Syndrome)."""
    __tablename__ = "notaufnahme_syndrome_data"

    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    ed_type = Column(String, nullable=False)      # all, central, pediatric
    age_group = Column(String, nullable=False)    # 00+, 0-4, ...
    syndrome = Column(String, nullable=False)     # ARI, SARI, ILI, COVID, GI
    relative_cases = Column(Float)
    relative_cases_7day_ma = Column(Float)
    expected_value = Column(Float)
    expected_lowerbound = Column(Float)
    expected_upperbound = Column(Float)
    ed_count = Column(Integer)
    created_at = Column(DateTime, default=_utc_now)

    __table_args__ = (
        Index('idx_notaufnahme_date_syndrome', 'datum', 'syndrome'),
        Index('idx_notaufnahme_filters', 'syndrome', 'ed_type', 'age_group'),
    )


class NotaufnahmeStandort(Base):
    """RKI/AKTIN Notaufnahmesurveillance Standort-Metadaten."""
    __tablename__ = "notaufnahme_standorte"

    id = Column(Integer, primary_key=True, index=True)
    ik_number = Column(String, unique=True, nullable=False, index=True)
    ed_name = Column(String)
    ed_type = Column(String)
    level_of_care = Column(String)
    state = Column(String)
    state_id = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    created_at = Column(DateTime, default=_utc_now)

    __table_args__ = (
        Index('idx_notaufnahme_state_type', 'state', 'ed_type'),
    )


class InfluenzaData(Base):
    """RKI IfSG Influenzafälle — wöchentliche Meldedaten nach Region und Altersgruppe."""
    __tablename__ = "influenza_data"

    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    available_time = Column(DateTime, nullable=True, index=True)
    meldewoche = Column(String, nullable=False)  # Original 'YYYY-Wxx'
    region = Column(String, nullable=False)
    region_id = Column(String, nullable=True)
    altersgruppe = Column(String, nullable=False)
    fallzahl = Column(Integer, nullable=True)
    inzidenz = Column(Float, nullable=True)
    created_at = Column(DateTime, default=_utc_now)

    __table_args__ = (
        Index('idx_influenza_date_region_age', 'datum', 'region', 'altersgruppe'),
    )


class RSVData(Base):
    """RKI IfSG RSV-Fälle — wöchentliche Meldedaten nach Region und Altersgruppe."""
    __tablename__ = "rsv_data"

    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    available_time = Column(DateTime, nullable=True, index=True)
    meldewoche = Column(String, nullable=False)  # Original 'YYYY-Wxx'
    region = Column(String, nullable=False)
    region_id = Column(String, nullable=True)
    altersgruppe = Column(String, nullable=False)
    fallzahl = Column(Integer, nullable=True)
    inzidenz = Column(Float, nullable=True)
    created_at = Column(DateTime, default=_utc_now)

    __table_args__ = (
        Index('idx_rsv_date_region_age', 'datum', 'region', 'altersgruppe'),
    )


class SurvstatWeeklyData(Base):
    """SURVSTAT RKI Meldeinzidenzen je Woche/Bundesland/Krankheit."""
    __tablename__ = "survstat_weekly_data"

    id = Column(Integer, primary_key=True, index=True)
    week_label = Column(String, nullable=False, index=True)  # YYYY_WW
    week_start = Column(DateTime, nullable=False, index=True)  # Montag der ISO-Woche
    available_time = Column(DateTime, nullable=True, index=True)
    year = Column(Integer, nullable=False, index=True)
    week = Column(Integer, nullable=False)
    bundesland = Column(String, nullable=False)
    disease = Column(String, nullable=False)
    disease_cluster = Column(String, nullable=True, index=True)  # RESPIRATORY, GASTROINTESTINAL, etc.
    age_group = Column(String, nullable=True)  # "00-04", "05-14", "15+", "Gesamt", etc.
    incidence = Column(Float)
    source_file = Column(String)
    created_at = Column(DateTime, default=_utc_now)

    __table_args__ = (
        Index('idx_survstat_week_state', 'week_label', 'bundesland'),
        Index('idx_survstat_disease_week', 'disease', 'week_start'),
        Index('idx_survstat_cluster_week', 'disease_cluster', 'week_start'),
        Index('uq_survstat_week_state_disease', 'week_label', 'bundesland', 'disease', unique=True),
    )


class SurvstatKreisData(Base):
    """RKI SurvStat Landkreis-Level Fallzahlen (via OLAP-Cube API)."""
    __tablename__ = "survstat_kreis_data"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False, index=True)
    week = Column(Integer, nullable=False)
    week_label = Column(String, nullable=False, index=True)
    kreis = Column(String, nullable=False, index=True)
    disease = Column(String, nullable=False, index=True)
    disease_cluster = Column(String, nullable=True, index=True)
    fallzahl = Column(Integer, nullable=False, default=0)
    inzidenz = Column(Float, nullable=True)
    created_at = Column(DateTime, default=_utc_now)

    __table_args__ = (
        UniqueConstraint("week_label", "kreis", "disease", name="uq_survstat_kreis"),
        Index("idx_survstat_kreis_disease_week", "disease", "year", "week"),
        Index("idx_survstat_kreis_cluster", "disease_cluster", "year"),
    )


class KreisEinwohner(Base):
    """Referenztabelle: Landkreis-Einwohnerzahlen (Destatis)."""
    __tablename__ = "kreis_einwohner"

    id = Column(Integer, primary_key=True, index=True)
    kreis_name = Column(String, nullable=False, unique=True, index=True)
    ags = Column(String(5), nullable=True)
    bundesland = Column(String, nullable=False, index=True)
    einwohner = Column(Integer, nullable=False)
    updated_at = Column(DateTime, default=_utc_now)


class GoogleTrendsData(Base):
    """Google Trends Suchanfragen-Daten."""
    __tablename__ = "google_trends_data"
    
    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    available_time = Column(DateTime, nullable=True, index=True)
    keyword = Column(String, nullable=False)
    region = Column(String, default="DE")  # Deutschland
    interest_score = Column(Integer)  # 0-100
    is_partial = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_utc_now)
    
    __table_args__ = (
        Index('idx_trends_date_keyword', 'datum', 'keyword'),
    )


class WeatherData(Base):
    """Wetterdaten von OpenWeather API."""
    __tablename__ = "weather_data"
    
    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    available_time = Column(DateTime, nullable=True, index=True)
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
    created_at = Column(DateTime, default=_utc_now)

    __table_args__ = (
        Index('idx_weather_date_city', 'datum', 'city'),
        Index('idx_weather_data_type', 'data_type'),
    )


class PollenData(Base):
    """DWD Pollenflugdaten (manueller Ingest via OpenData JSON)."""
    __tablename__ = "pollen_data"

    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    available_time = Column(DateTime, nullable=True, index=True)
    region_code = Column(String, nullable=False, index=True)  # Bundesland-Code (BW, BY, ...)
    pollen_type = Column(String, nullable=False, index=True)  # Birke, Graeser, ...
    pollen_index = Column(Float, nullable=False)  # 0.0 - 3.0 (DWD-Skala)
    source = Column(String, nullable=False, default="DWD")
    created_at = Column(DateTime, default=_utc_now, index=True)

    __table_args__ = (
        Index('idx_pollen_region_date', 'region_code', 'datum'),
        Index('idx_pollen_type_date', 'pollen_type', 'datum'),
        Index('uq_pollen_region_type_date', 'region_code', 'pollen_type', 'datum', unique=True),
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
    created_at = Column(DateTime, default=_utc_now)
    
    __table_args__ = (
        Index('idx_holidays_dates', 'start_datum', 'end_datum'),
    )


class GanzimmunData(Base):
    """Optionale interne ganzimmun Daten (Testverkäufe, Ergebnisse)."""
    __tablename__ = "ganzimmun_data"
    
    id = Column(Integer, primary_key=True, index=True)
    datum = Column(DateTime, nullable=False, index=True)
    available_time = Column(DateTime, nullable=True, index=True)
    test_typ = Column(String, nullable=False)
    anzahl_tests = Column(Integer)
    positive_ergebnisse = Column(Integer)
    region = Column(String)
    extra_data = Column(JSON)  # Flexibel für zusätzliche Daten
    created_at = Column(DateTime, default=_utc_now)


class MLForecast(Base):
    """Machine Learning Prognosen."""
    __tablename__ = "ml_forecasts"
    
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=_utc_now, index=True)
    forecast_date = Column(DateTime, nullable=False, index=True)
    virus_typ = Column(String, nullable=False)
    region = Column(String, nullable=False, default="DE", index=True)
    horizon_days = Column(Integer, nullable=False, default=7, index=True)
    predicted_value = Column(Float, nullable=False)
    lower_bound = Column(Float)
    upper_bound = Column(Float)
    confidence = Column(Float)  # 0-1
    model_version = Column(String)
    features_used = Column(JSON)  # Welche Features wurden verwendet
    trend_momentum_7d = Column(Float, nullable=True)  # 7-Tage-Slope (1. Ableitung)
    outbreak_risk_score = Column(Float, nullable=True)  # 0.0 – 1.0

    __table_args__ = (
        Index('idx_forecast_scope_date', 'forecast_date', 'virus_typ', 'region', 'horizon_days'),
        Index('idx_forecast_scope_created', 'virus_typ', 'region', 'horizon_days', 'created_at'),
    )


class LLMRecommendation(Base):
    """LLM-generierte Empfehlungen."""
    __tablename__ = "llm_recommendations"
    
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=_utc_now, index=True)
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
    timestamp = Column(DateTime, default=_utc_now, index=True)
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
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now)


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
    created_at = Column(DateTime, default=_utc_now)

    __table_args__ = (
        Index('idx_outbreak_date_virus', 'datum', 'virus_typ'),
    )


class MarketingOpportunity(Base):
    """Marketing/Sales Opportunities aus der MarketingOpportunityEngine."""
    __tablename__ = "marketing_opportunities"

    id = Column(Integer, primary_key=True, index=True)
    opportunity_id = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=_utc_now, index=True)
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
    brand = Column(String, index=True)
    product = Column(String, index=True)
    budget_shift_pct = Column(Float)
    channel_mix = Column(JSON)
    activation_start = Column(DateTime)
    activation_end = Column(DateTime)
    recommendation_reason = Column(String)
    campaign_payload = Column(JSON)
    playbook_key = Column(String, index=True)
    strategy_mode = Column(String, default="PLAYBOOK_AI", index=True)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, index=True)
    expires_at = Column(DateTime)
    exported_at = Column(DateTime)

    __table_args__ = (
        Index('idx_opportunity_type_status', 'opportunity_type', 'status'),
        Index('idx_opportunity_urgency', 'urgency_score'),
        Index('idx_opportunity_brand_status', 'brand', 'status'),
        Index('idx_opportunity_playbook', 'playbook_key'),
    )


class BrandProduct(Base):
    """Externer Marken-Produktkatalog (z. B. Gelo Produktseite)."""
    __tablename__ = "brand_products"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, nullable=False, index=True)
    product_name = Column(String, nullable=False, index=True)
    source_url = Column(String, nullable=False)
    source_hash = Column(String, nullable=False)
    active = Column(Boolean, default=True, index=True)
    extra_data = Column(JSON)
    last_seen_at = Column(DateTime, default=_utc_now, index=True)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, index=True)

    __table_args__ = (
        Index('idx_brand_products_brand_active', 'brand', 'active'),
        Index('uq_brand_products_brand_name', 'brand', 'product_name', unique=True),
    )


class ProductConditionMapping(Base):
    """Auto+Review Mapping Produkt -> Lageklasse."""
    __tablename__ = "product_condition_mapping"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("brand_products.id"), nullable=False, index=True)
    condition_key = Column(String, nullable=False, index=True)
    rule_source = Column(String, nullable=False, default="auto", index=True)  # auto | hard_rule
    fit_score = Column(Float, nullable=False, default=0.0)
    mapping_reason = Column(String)
    is_approved = Column(Boolean, default=False, index=True)
    priority = Column(Integer, default=0)
    notes = Column(String)
    created_at = Column(DateTime, default=_utc_now)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, index=True)

    product = relationship("BrandProduct")

    __table_args__ = (
        Index('idx_pcm_brand_condition', 'brand', 'condition_key'),
        Index('idx_pcm_brand_approved', 'brand', 'is_approved'),
        Index('uq_pcm_product_condition', 'product_id', 'condition_key', unique=True),
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
    created_at = Column(DateTime, default=_utc_now)


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
    created_at = Column(DateTime, default=_utc_now, index=True)


class MediaOutcomeRecord(Base):
    """Manuell oder per CSV importierte Truth-/Outcome-Daten für Media-Evidenz."""
    __tablename__ = "media_outcome_records"

    id = Column(Integer, primary_key=True, index=True)
    week_start = Column(DateTime, nullable=False, index=True)
    brand = Column(String, nullable=False, index=True, default="gelo")
    product = Column(String, nullable=False, index=True)
    region_code = Column(String, nullable=False, index=True)
    media_spend_eur = Column(Float)
    impressions = Column(Float)
    clicks = Column(Float)
    qualified_visits = Column(Float)
    search_lift_index = Column(Float)
    sales_units = Column(Float)
    order_count = Column(Float)
    revenue_eur = Column(Float)
    source_label = Column(String, nullable=False, default="manual", index=True)
    import_batch_id = Column(String, nullable=True, index=True)
    extra_data = Column(JSON)
    created_at = Column(DateTime, default=_utc_now, index=True)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, index=True)

    __table_args__ = (
        UniqueConstraint("week_start", "brand", "product", "region_code", "source_label", name="uq_media_outcome_record"),
        Index("idx_media_outcome_brand_week", "brand", "week_start"),
        Index("idx_media_outcome_product_week", "product", "week_start"),
    )


class OutcomeObservation(Base):
    """Generic outcome observations kept separate from epidemiological ground truth."""
    __tablename__ = "outcome_observations"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, nullable=False, index=True, default="gelo")
    product = Column(String, nullable=False, index=True)
    region_code = Column(String, nullable=False, index=True)
    window_start = Column(DateTime, nullable=False, index=True)
    window_end = Column(DateTime, nullable=False, index=True)
    metric_name = Column(String, nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    metric_unit = Column(String)
    source_label = Column(String, nullable=False, default="manual", index=True)
    channel = Column(String, nullable=True, index=True)
    campaign_id = Column(String, nullable=True, index=True)
    holdout_group = Column(String, nullable=True, index=True)
    confidence_hint = Column(Float, nullable=True)
    metadata_json = Column("metadata", JSON)
    created_at = Column(DateTime, default=_utc_now, index=True)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, index=True)

    __table_args__ = (
        UniqueConstraint(
            "window_start",
            "window_end",
            "brand",
            "product",
            "region_code",
            "metric_name",
            "source_label",
            name="uq_outcome_observation",
        ),
        Index("idx_outcome_obs_brand_window", "brand", "window_start"),
        Index("idx_outcome_obs_metric_window", "metric_name", "window_start"),
        Index("idx_outcome_obs_region_product", "region_code", "product"),
    )


class MediaOutcomeImportBatch(Base):
    """Persistierte Import-Batches für Truth-/Outcome Uploads."""
    __tablename__ = "media_outcome_import_batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String, nullable=False, unique=True, index=True)
    brand = Column(String, nullable=False, index=True, default="gelo")
    source_label = Column(String, nullable=False, default="manual", index=True)
    source_system = Column(String, nullable=True, index=True)
    external_batch_id = Column(String, nullable=True, index=True)
    ingestion_mode = Column(String, nullable=False, default="manual_backoffice", index=True)
    file_name = Column(String)
    status = Column(String, nullable=False, default="validated", index=True)
    rows_total = Column(Integer, nullable=False, default=0)
    rows_valid = Column(Integer, nullable=False, default=0)
    rows_imported = Column(Integer, nullable=False, default=0)
    rows_rejected = Column(Integer, nullable=False, default=0)
    rows_duplicate = Column(Integer, nullable=False, default=0)
    week_min = Column(DateTime, index=True)
    week_max = Column(DateTime, index=True)
    coverage_after_import = Column(JSON)
    uploaded_at = Column(DateTime, default=_utc_now, index=True)
    created_at = Column(DateTime, default=_utc_now, index=True)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, index=True)

    __table_args__ = (
        Index("idx_media_outcome_batch_brand_uploaded", "brand", "uploaded_at"),
        Index("idx_media_outcome_batch_status_uploaded", "status", "uploaded_at"),
        UniqueConstraint("source_system", "external_batch_id", name="uq_media_outcome_batch_external"),
    )


class MediaOutcomeImportIssue(Base):
    """Persistierte Zeilenfehler und Mapping-Issues eines Truth-Imports."""
    __tablename__ = "media_outcome_import_issues"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String, nullable=False, index=True)
    row_number = Column(Integer, nullable=True, index=True)
    field_name = Column(String, nullable=True, index=True)
    issue_code = Column(String, nullable=False, index=True)
    message = Column(String, nullable=False)
    raw_row = Column(JSON)
    created_at = Column(DateTime, default=_utc_now, index=True)

    __table_args__ = (
        Index("idx_media_outcome_issue_batch_row", "batch_id", "row_number"),
        Index("idx_media_outcome_issue_batch_code", "batch_id", "issue_code"),
    )


class LabConfiguration(Base):
    """Gelernte Gewichte (Global oder pro Mandant)."""
    __tablename__ = "lab_configurations"

    id = Column(Integer, primary_key=True, index=True)
    is_global_default = Column(Boolean, default=False, index=True)
    weight_bio = Column(Float, default=0.35)
    weight_market = Column(Float, default=0.35)
    weight_psycho = Column(Float, default=0.10)
    weight_context = Column(Float, default=0.20)
    last_calibration_date = Column(DateTime, default=_utc_now)
    calibration_source = Column(String)
    correlation_score = Column(Float)
    analyzed_days = Column(Integer)


class BacktestRun(Base):
    """Persistierte Backtest-Läufe für Twin-Mode (Market + Customer)."""
    __tablename__ = "backtest_runs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, unique=True, nullable=False, index=True)
    mode = Column(String, nullable=False, index=True)  # MARKET_CHECK, CUSTOMER_CHECK
    status = Column(String, nullable=False, default="success", index=True)
    virus_typ = Column(String, nullable=False, index=True)
    target_source = Column(String, nullable=False, index=True)
    target_key = Column(String)
    target_label = Column(String)
    strict_vintage_mode = Column(Boolean, default=True)
    horizon_days = Column(Integer, default=14)
    min_train_points = Column(Integer, default=20)
    parameters = Column(JSON)
    metrics = Column(JSON)
    baseline_metrics = Column(JSON)
    improvement_vs_baselines = Column(JSON)
    optimized_weights = Column(JSON)
    proof_text = Column(String)
    llm_insight = Column(String)
    lead_lag = Column(JSON)
    chart_points = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utc_now, index=True)

    __table_args__ = (
        Index('idx_backtest_mode_created', 'mode', 'created_at'),
        Index('idx_backtest_target_created', 'target_source', 'created_at'),
    )


class BacktestPoint(Base):
    """Zeitpunkte eines Backtest-Runs (für Charts und Auditing)."""
    __tablename__ = "backtest_points"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, ForeignKey("backtest_runs.run_id"), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    region = Column(String, nullable=True, index=True)
    real_qty = Column(Float)
    predicted_qty = Column(Float)
    baseline_persistence = Column(Float)
    baseline_seasonal = Column(Float)
    bio = Column(Float)
    psycho = Column(Float)
    context = Column(Float)
    extra = Column(JSON)
    created_at = Column(DateTime, default=_utc_now, index=True)

    backtest_run = relationship("BacktestRun")

    __table_args__ = (
        Index('idx_backtest_points_run_date', 'run_id', 'date'),
    )


class ForecastAccuracyLog(Base):
    """Tägliches Monitoring: Forecast vs. tatsächliche Abwasserdaten."""
    __tablename__ = "forecast_accuracy_log"

    id = Column(Integer, primary_key=True, index=True)
    computed_at = Column(DateTime, default=_utc_now, nullable=False, index=True)
    virus_typ = Column(String, nullable=False, index=True)
    window_days = Column(Integer, nullable=False, default=14)
    samples = Column(Integer, nullable=False)
    mae = Column(Float)
    rmse = Column(Float)
    mape = Column(Float)
    correlation = Column(Float)
    drift_detected = Column(Boolean, default=False)
    details = Column(JSON)

    __table_args__ = (
        Index('idx_accuracy_virus_computed', 'virus_typ', 'computed_at'),
    )


class SourceNowcastSnapshot(Base):
    """Append-only snapshots of raw source observations for revision auditing."""
    __tablename__ = "source_nowcast_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(String, nullable=False, index=True)
    signal_id = Column(String, nullable=False, index=True)
    region_code = Column(String, nullable=True, index=True)
    reference_date = Column(DateTime, nullable=False, index=True)
    effective_available_time = Column(DateTime, nullable=False, index=True)
    raw_value = Column(Float, nullable=False)
    snapshot_captured_at = Column(DateTime, nullable=False, default=_utc_now, index=True)
    timing_provenance = Column(String, nullable=False)
    metadata_json = Column("metadata", JSON)
    created_at = Column(DateTime, default=_utc_now, index=True)

    __table_args__ = (
        Index("idx_nowcast_snapshot_source_ref", "source_id", "reference_date"),
        Index("idx_nowcast_snapshot_signal_region", "signal_id", "region_code"),
        Index("idx_nowcast_snapshot_capture_source", "snapshot_captured_at", "source_id"),
    )


class WeeklyBrief(Base):
    """Wöchentlicher Gelo Media Action Brief (PDF)."""
    __tablename__ = "weekly_briefs"

    id = Column(Integer, primary_key=True, index=True)
    calendar_week = Column(String(10), nullable=False, index=True)
    generated_at = Column(DateTime, default=_utc_now, nullable=False)
    pdf_bytes = Column(LargeBinary)
    summary_json = Column(JSON)
    virus_typ = Column(String(50))
    brand = Column(String(50), default="gelo", index=True)

    __table_args__ = (
        Index('idx_weekly_brief_week_brand', 'calendar_week', 'brand'),
    )
