"""The Lab receives only service-scoped configuration, never exchange credentials."""

from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LAB_", extra="ignore")
    data_dir: Path = Path("./var/experiment-lab")
    service_url: str = "http://experiment-lab:8010"
    replay_timeout_seconds: int = Field(default=10800, ge=60, le=86400)
    service_token: SecretStr = Field(min_length=32)
    advisor_token: SecretStr | None = None
    runner_token: SecretStr | None = None

    @model_validator(mode="after")
    def validate_scoped_credentials(self) -> "Settings":
        credentials = [
            value.get_secret_value()
            for value in (self.service_token, self.advisor_token, self.runner_token)
            if value is not None
        ]
        if any(len(value) < 32 for value in credentials):
            raise ValueError(
                "Every configured service credential needs at least 32 characters"
            )
        if len(set(credentials)) != len(credentials):
            raise ValueError("Owner, advisor and runner credentials must be distinct")
        return self
