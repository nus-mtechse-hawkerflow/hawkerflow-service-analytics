import os
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class Service(BaseSettings):
    title: str
    root_path: str
    port: int
    host: str
    allow_origins: list[str]
    methods: list[str]
    headers: list[str]
    docs_url: str
    redoc_url: str
    credentials: bool


class Database(BaseSettings):
    driver_name: str
    name: str
    host: str
    port: int


class Driver(BaseSettings):
    package: str
    driver_class: str


class DatabaseOptions(BaseSettings):
    user: SecretStr = Field(alias="postgres.user")
    password: SecretStr = Field(alias="postgres.password")
    echo: bool

    model_config = SettingsConfigDict(
        secrets_dir=Path(os.getenv("PROJECT_ROOT") or ".") / "vault"
    )


class Datasource(BaseSettings):
    driver: Driver
    database: Database
    options: DatabaseOptions


class AppConfig(BaseSettings):
    """Configuration for the analytics service.

    Deliberately carries no sqs or events section: this service consumes no
    queues and publishes no events. It only reads.
    """

    service: Service
    datasource: Datasource

    model_config = SettingsConfigDict(
        yaml_file=Path(os.getenv("PROJECT_ROOT") or ".") / "resources" / "config.yml"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            init_settings,
        )
