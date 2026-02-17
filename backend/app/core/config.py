from pydantic_settings import BaseSettings
from typing import List
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
    
    # Ollama
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama2"
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000"
    
    @property
    def CORS_ORIGINS(self) -> List[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]
    
    # Data Sources
    RKI_AMELAG_URL: str = "https://raw.githubusercontent.com/robert-koch-institut/Abwassersurveillance_AMELAG/main"
    RKI_GRIPPEWEB_URL: str = "https://raw.githubusercontent.com/robert-koch-institut/GrippeWeb_Daten_des_Wochenberichts/main"
    RKI_ARE_KONSULTATION_URL: str = "https://raw.githubusercontent.com/robert-koch-institut/ARE-Konsultationsinzidenz/main/ARE-Konsultationsinzidenz.tsv"
    RKI_NOTAUFNAHME_URL: str = "https://raw.githubusercontent.com/robert-koch-institut/Daten_der_Notaufnahmesurveillance/main"
    DWD_POLLEN_URL: str = "https://opendata.dwd.de/climate_environment/health/alerts/s31fg.json"
    SURVSTAT_LOCAL_DIR: str = "/app/data/raw/survstat"

    # Media AI
    MEDIA_AI_PLAYBOOKS_ENABLED: bool = True
    
    # ML Settings
    FORECAST_DAYS: int = 14
    CONFIDENCE_LEVEL: float = 0.95
    
    # Scheduling
    DATA_UPDATE_CRON: str = "0 6 * * *"
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60
    
    # Cache
    CACHE_TTL: int = 3600
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
