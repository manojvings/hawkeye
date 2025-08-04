# app/core/config.py - Clean OpenTelemetry-optimized configuration
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr
from typing import List

class Settings(BaseSettings):
    """
    Clean settings for CHawk API with OpenTelemetry-first tracing
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database Settings
    DATABASE_URL: str = Field(..., description="PostgreSQL database URL for asyncpg")

    # JWT Authentication Settings
    JWT_SECRET_KEY: SecretStr = Field(..., description="Secret key for signing JWT tokens")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Application Settings
    ENVIRONMENT: str = Field("development", description="Environment name")
    LOG_LEVEL: str = Field("INFO", description="Log level")

    # Logging Configuration
    ENABLE_JSON_LOGGING: bool = Field(True, description="Enable JSON structured logging")

    # OpenTelemetry Tracing Settings (Simplified)
    ENABLE_OTEL_EXPORTER: bool = Field(True, description="Enable OpenTelemetry console exporter")
    ENABLE_OTEL_CONSOLE_EXPORT: bool = Field(False, description="Enable OpenTelemetry console export (JSON spam)")
    ENABLE_EXTERNAL_TRACING: bool = Field(False, description="Enable external OTLP tracing")
    OTLP_ENDPOINT: str = Field("http://localhost:4317", description="OTLP endpoint for external tracing")

    # CORS Settings
    CORS_ORIGINS: str = Field(
        "http://localhost:3000,http://127.0.0.1:3000",
        description="Comma-separated list of allowed CORS origins"
    )

    # Rate Limiting Settings
    RATE_LIMIT_ENABLED: bool = Field(True, description="Enable rate limiting")
    DEFAULT_RATE_LIMIT: str = Field("100/minute", description="Default rate limit")
    LOGIN_RATE_LIMIT: str = Field("5/minute", description="Login rate limit")

    # Performance Settings
    DB_POOL_SIZE: int = Field(20, description="Database connection pool size")
    DB_MAX_OVERFLOW: int = Field(0, description="Database max overflow connections")

    @property
    def cors_origins_list(self) -> List[str]:
        """Convert CORS_ORIGINS string to list"""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def should_use_json_logging(self) -> bool:
        """Use JSON logging in production or when explicitly enabled"""
        return self.ENVIRONMENT == "production" or self.ENABLE_JSON_LOGGING

# Create settings instance
settings = Settings()