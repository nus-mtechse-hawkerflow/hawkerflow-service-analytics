from sqlalchemy import URL
from sqlalchemy.engine import Engine
from sqlmodel import create_engine

from configurations.app_config import Datasource
from factory.database_factory import DatabaseFactory


class DBSession:
    def __init__(self, config: Datasource):
        self._engine: Engine | None = None
        self._config: Datasource = config

    @property
    def engine(self) -> Engine:
        """
        Returns the database engine, creating it on first access.
        Connection handling is bounded: this service is read-only and
        should never hold a large pool open against the order database.
        """
        if self._engine is None:
            self._engine = create_engine(
                self._get_connection(),
                echo=self._config.options.echo,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=2,
            )

        return self._engine

    def _get_connection(self) -> str | URL:
        """Loads the database driver and creates a connection URL."""
        driver_class = DatabaseFactory().create_driver(
            self._config.driver.package,
            self._config.driver.driver_class,
        )

        return driver_class(self._config).get_connection()
