import logging
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str
    db_name: str = "agncf"
    db_user: str = "agncf_user"
    db_password: str = "changeme"

    # Gitea
    gitea_url: str
    gitea_token: str
    gitea_org: str = "agncf"
    gitea_secret_key: str

    # Encryption
    fernet_key: str

    # Global credentials (fallback)
    net_user_global: Optional[str] = None
    net_pass_global: Optional[str] = None

    # Nornir
    nornir_num_workers: int = 50
    api_semaphore_limit: int = 30

    # Application
    log_level: str = "INFO"
    debug: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


def get_settings() -> Settings:
    """Return singleton settings instance."""
    return Settings()


def setup_logging(settings: Settings) -> None:
    """Configure logging based on settings."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
