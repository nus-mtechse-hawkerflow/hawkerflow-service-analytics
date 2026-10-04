import os
from pathlib import Path

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
    name: str = os.getenv("DB_NAME", "hawker")
    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", 5432))


class Driver(BaseSettings):
    package: str
    driver_class: str


class DatabaseOptions(BaseSettings):
    user: str = os.getenv("DB_USERNAME", "")
    password: str = os.getenv("DB_PASSWORD", "")
    echo: bool = False


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
