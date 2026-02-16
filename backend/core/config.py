# backend/core/config.py

"""
Application configuration settings
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    # Pydantic V2 Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",  # Allow extra env vars (e.g., from .env during tests)
    )

    # API Configuration
    API_TITLE: str = "FlowNote API"
    API_VERSION: str = "4.0.0"
    API_DESCRIPTION: str = "AI-powered PARA classification and conflict resolution API"

    # File Upload Configuration
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB in bytes

    # i18n Configuration
    DEFAULT_LOCALE: str = "ko"
    SUPPORTED_LOCALES: list[str] = ["ko", "en"]

    # CORS Configuration
    CORS_ORIGINS: list[str] = ["*"]

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True


# Global settings instance
settings = Settings()
