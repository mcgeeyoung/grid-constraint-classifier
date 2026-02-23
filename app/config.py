"""Application configuration via environment variables."""

import os
from pathlib import Path


class Settings:
    """Application settings loaded from environment variables."""

    DATABASE_URL: str = os.environ.get(
        "DATABASE_URL",
        "postgresql://gridclass:gridclass@localhost:5432/gridclass",
    )
    # Heroku uses postgres:// but SQLAlchemy needs postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    ASYNC_DATABASE_URL: str = DATABASE_URL.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )

    PROJECT_ROOT: Path = Path(__file__).parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "data"

    # API settings
    API_TITLE: str = "Grid Constraint Classifier API"
    API_VERSION: str = "1.0.0"
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "https://wattcarbon.github.io",
    ]

    # Pipeline credentials (optional)
    PJM_SUBSCRIPTION_KEY: str = os.environ.get("PJM_SUBSCRIPTION_KEY", "")
    PJM_GIS_USERNAME: str = os.environ.get("PJM_GIS_USERNAME", "")
    PJM_GIS_PASSWORD: str = os.environ.get("PJM_GIS_PASSWORD", "")
    ISONE_USERNAME: str = os.environ.get("ISONE_USERNAME", "")
    ISONE_PASSWORD: str = os.environ.get("ISONE_PASSWORD", "")


settings = Settings()
