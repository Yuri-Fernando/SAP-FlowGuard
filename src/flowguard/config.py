from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "SAP FlowGuard"
    sap_mode: Literal["mock", "sandbox", "hybrid", "live"] = "mock"
    sap_mock_base_url: str = "http://localhost:8080"
    sap_sandbox_base_url: str = "https://sandbox.api.sap.com/s4hanacloud"
    sap_api_key: SecretStr | None = None
    sap_live_base_url: str | None = None
    sap_read_username: str | None = None
    sap_read_password: SecretStr | None = None
    sap_write_username: str | None = None
    sap_write_password: SecretStr | None = None

    enable_sap_write: bool = False
    require_human_approval: bool = True
    allow_fi_posting: bool = False
    allow_billing_cancel: bool = False
    allow_invoice_release: bool = False

    database_url: str = "sqlite:///./flowguard.db"
    redis_url: str = "redis://localhost:6379/0"
    demo_scenario: str = "billing_without_fi"
    request_timeout_seconds: float = 15.0
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
