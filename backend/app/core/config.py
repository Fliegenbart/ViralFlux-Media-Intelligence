from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Application configuration settings."""
    
    # App Info
    APP_NAME: str = "ViralFlux Media Intelligence"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    
    # Database
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    # API Keys
    OPENWEATHER_API_KEY: str
    GANZIMMUN_API_URL: str | None = None
    GANZIMMUN_API_KEY: str | None = None
    
    # vLLM (OpenAI-compatible, strictly local)
    VLLM_BASE_URL: str = "http://localhost:8000/v1"
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    
    @property
    def CORS_ORIGINS(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    # Data Sources
    RKI_AMELAG_URL: str = "https://raw.githubusercontent.com/robert-koch-institut/Abwassersurveillance_AMELAG/main"
    RKI_GRIPPEWEB_URL: str = "https://raw.githubusercontent.com/robert-koch-institut/GrippeWeb_Daten_des_Wochenberichts/main"
    RKI_ARE_KONSULTATION_URL: str = "https://raw.githubusercontent.com/robert-koch-institut/ARE-Konsultationsinzidenz/main/ARE-Konsultationsinzidenz.tsv"
    RKI_NOTAUFNAHME_URL: str = "https://raw.githubusercontent.com/robert-koch-institut/Daten_der_Notaufnahmesurveillance/main"
    RKI_INFLUENZA_URL: str = "https://raw.githubusercontent.com/robert-koch-institut/Influenzafaelle_in_Deutschland/main/IfSG_Influenzafaelle.tsv"
    RKI_RSV_URL: str = "https://raw.githubusercontent.com/robert-koch-institut/Respiratorische_Synzytialvirusfaelle_in_Deutschland/main/IfSG_RSVfaelle.tsv"
    DWD_POLLEN_URL: str = "https://opendata.dwd.de/climate_environment/health/alerts/s31fg.json"
    SURVSTAT_LOCAL_DIR: str = "/app/data/raw/survstat"

    # Media AI
    MEDIA_AI_PLAYBOOKS_ENABLED: bool = True
    MEDIA_AI_ASYNC_REFINEMENT_ENABLED: bool = True
    MEDIA_AI_BULK_REFINE_TOP_N: int = 3
    MEDIA_AI_REFINEMENT_POLL_HINT_SECONDS: int = 5
    
    # ML Settings
    FORECAST_DAYS: int = 14
    CONFIDENCE_LEVEL: float = 0.95
    WAVE_PREDICTION_HORIZON_DAYS: int = 14
    WAVE_PREDICTION_LOOKBACK_DAYS: int = 900
    WAVE_PREDICTION_MIN_TRAIN_ROWS: int = 240
    WAVE_PREDICTION_MIN_POSITIVE_ROWS: int = 12
    WAVE_PREDICTION_MODEL_VERSION: str = "wave_prediction_v1"
    WAVE_PREDICTION_BACKTEST_FOLDS: int = 4
    WAVE_PREDICTION_MIN_TRAIN_PERIODS: int = 180
    WAVE_PREDICTION_MIN_TEST_PERIODS: int = 28
    WAVE_PREDICTION_CLASSIFICATION_THRESHOLD: float = 0.5
    WAVE_PREDICTION_ENABLE_FORECAST_WEATHER: bool = True
    WAVE_PREDICTION_ENABLE_DEMOGRAPHICS: bool = True
    WAVE_PREDICTION_ENABLE_INTERACTIONS: bool = True
    WAVE_PREDICTION_LABEL_ABSOLUTE_THRESHOLD: float = 10.0
    WAVE_PREDICTION_LABEL_SEASONAL_ZSCORE: float = 1.5
    WAVE_PREDICTION_LABEL_GROWTH_OBSERVATIONS: int = 2
    WAVE_PREDICTION_LABEL_GROWTH_MIN_RELATIVE_INCREASE: float = 0.2
    WAVE_PREDICTION_LABEL_MAD_FLOOR: float = 1.0
    WAVE_PREDICTION_CALIBRATION_HOLDOUT_FRACTION: float = 0.2
    WAVE_PREDICTION_MIN_CALIBRATION_ROWS: int = 28
    WAVE_PREDICTION_MIN_CALIBRATION_POSITIVES: int = 6
    
    # Scheduling
    DATA_UPDATE_CRON: str = "0 6 * * *"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Operations / Startup Safety
    DB_AUTO_CREATE_SCHEMA: bool | None = None
    DB_ALLOW_RUNTIME_SCHEMA_UPDATES: bool | None = None
    STARTUP_STRICT_READINESS: bool | None = None
    READINESS_REQUIRE_BROKER: bool | None = None
    READINESS_SOURCE_FRESH_DAYS: int = 7
    READINESS_SOURCE_WARNING_DAYS: int = 14
    READINESS_FORECAST_LAG_FRESH_DAYS: int = 3
    READINESS_FORECAST_LAG_WARNING_DAYS: int = 7
    READINESS_MODEL_MAX_AGE_DAYS: int = 45
    READINESS_MODEL_WARNING_AGE_DAYS: int = 21
    READINESS_MIN_SOURCE_COVERAGE: float = 0.6
    CORE_PRODUCTION_SCOPES: str = "RSV A:h7"
    REGIONAL_SARS_H7_PROMOTION_ENABLED: bool = False
    FORECAST_ENABLE_TSFM_CHALLENGERS: bool = False
    FORECAST_TSFM_PROVIDER: str = "timesfm"
    FORECAST_BENCHMARK_MIN_RELATIVE_WIS_IMPROVEMENT: float = 0.01
    FORECAST_ENABLE_ADAPTIVE_REVISION_POLICY: bool = True
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60
    
    # Cache
    CACHE_TTL: int = 3600

    @property
    def EFFECTIVE_DB_AUTO_CREATE_SCHEMA(self) -> bool:
        if self.DB_AUTO_CREATE_SCHEMA is not None:
            return bool(self.DB_AUTO_CREATE_SCHEMA)
        return self.ENVIRONMENT in {"development", "test"}

    @property
    def EFFECTIVE_DB_ALLOW_RUNTIME_SCHEMA_UPDATES(self) -> bool:
        if self.DB_ALLOW_RUNTIME_SCHEMA_UPDATES is not None:
            return bool(self.DB_ALLOW_RUNTIME_SCHEMA_UPDATES)
        return self.ENVIRONMENT in {"development", "test"}

    @property
    def EFFECTIVE_STARTUP_STRICT_READINESS(self) -> bool:
        if self.STARTUP_STRICT_READINESS is not None:
            return bool(self.STARTUP_STRICT_READINESS)
        return self.ENVIRONMENT == "production"

    @property
    def EFFECTIVE_READINESS_REQUIRE_BROKER(self) -> bool:
        if self.READINESS_REQUIRE_BROKER is not None:
            return bool(self.READINESS_REQUIRE_BROKER)
        return self.ENVIRONMENT == "production"

    @property
    def EFFECTIVE_CORE_PRODUCTION_SCOPES(self) -> list[tuple[str, int]]:
        scopes: list[tuple[str, int]] = []
        seen: set[tuple[str, int]] = set()
        raw_value = str(self.CORE_PRODUCTION_SCOPES or "").strip()
        for item in raw_value.split(","):
            token = item.strip()
            if not token or ":" not in token:
                continue
            virus_part, horizon_part = token.rsplit(":", 1)
            virus_typ = virus_part.strip()
            horizon_token = horizon_part.strip().lower()
            if horizon_token.startswith("h"):
                horizon_token = horizon_token[1:]
            try:
                horizon_days = int(horizon_token)
            except ValueError:
                continue
            scope = (virus_typ, horizon_days)
            if scope in seen:
                continue
            seen.add(scope)
            scopes.append(scope)
        return scopes
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
