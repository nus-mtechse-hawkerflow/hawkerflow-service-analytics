import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from configurations.app_config import AppConfig
from repository.analytics_repo import AnalyticsRepo
from session.db_session import DBSession

logger = logging.getLogger("hawkerflow-analytics.lifecycle")


@asynccontextmanager
async def startup(app: FastAPI):
    """
    Startup for the analytics service.

    Note what is deliberately absent: there is no SQLModel.metadata.create_all
    here. The order service owns this schema. This service must never create,
    alter or drop a table.
    """
    project_root = Path(__file__).resolve().parents[2]
    os.environ.setdefault("PROJECT_ROOT", str(project_root))

    config = AppConfig()
    session = DBSession(config.datasource)

    app.state.config = config
    app.state.session = session
    app.state.analytics_repo = AnalyticsRepo(session.engine)

    logger.info(
        "Analytics service ready (read-only against %s)",
        config.datasource.database.name,
    )

    yield

    logger.info("Analytics service shutting down")
