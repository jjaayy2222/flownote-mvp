# backend/core/config.py

"""
Application configuration settings
"""


from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings for the FlowNote API.

    This class loads and validates environment variables from the `.env` file
    using Pydantic Settings. It defines fallback default values for API
    configuration, file size limits, internationalization (i18n), CORS, and
    running server parameters.

    Attributes:
        API_TITLE (str): The name of the API project. Default is "FlowNote API".
        API_VERSION (str): The current release version of the API. Default is "4.0.0".
        API_DESCRIPTION (str): Brief description of the API capabilities.
        MAX_UPLOAD_SIZE (int): Maximum allowed file size for uploads in bytes.
            Default is 10MB (10 * 1024 * 1024).
        DEFAULT_LOCALE (str): Default language locale code. Default is "ko".
        SUPPORTED_LOCALES (list[str]): List of supported locales for internationalization.
            Default is ["ko", "en"].
        CORS_ORIGINS (list[str]): Allowed origins for Cross-Origin Resource Sharing.
            Default is ["*"].
        HOST (str): Network address the server binds to. Default is "0.0.0.0".
        PORT (int): Port number on which the server listens. Default is 8000.
        RELOAD (bool): Enable or disable auto-reload on file change. Default is True.
    """

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

