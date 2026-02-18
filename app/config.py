import logging
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str

    # Gitea
    gitea_url: str
    gitea_token: str
    gitea_org: str = "agncf"

    # Credential encryption (Fernet key, 44-char URL-safe base64)
    fernet_key: str

    # Global network credentials — optional fallback tier
    net_user_global: Optional[str] = None
    net_pass_global: Optional[str] = None

    # Nornir / concurrency tuning
    nornir_num_workers: int = 50
    api_semaphore_limit: int = 30

    # Application
    log_level: str = "INFO"
    debug: bool = False

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first load)."""
    return Settings()


def setup_logging(settings: Settings) -> None:
    """Configure root logger from settings."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s  %(name)-40s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
