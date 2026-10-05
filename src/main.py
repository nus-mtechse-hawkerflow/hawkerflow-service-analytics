import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from configurations.app_config import AppConfig
from endpoints.analytics_routes import analytics_router
from endpoints.health_routes import health_router
from lifecycle.lifespan import startup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hawkerflow-analytics")


class HawkerFlowAnalytics:
    def __init__(self):
        self._app: FastAPI | None = None
        self._config = AppConfig()

        self._init_app()

    def start(self):
        """Starting point for the app. Binds to the host and port in config.yml."""
        uvicorn.run(
            self._app,
            host=self._config.service.host,
            port=self._config.service.port,
        )

    def _init_app(self):
        """Initialise and configure the FastAPI application."""
        self._app = FastAPI(
            title=self._config.service.title,
            docs_url=self._config.service.docs_url,
            redoc_url=self._config.service.redoc_url,
            root_path=self._config.service.root_path,
            lifespan=startup,
        )

        self._add_middleware()
        self._include_routers()

    def _add_middleware(self):
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=self._config.service.allow_origins,
            allow_credentials=self._config.service.credentials,
            allow_methods=self._config.service.methods,
            allow_headers=self._config.service.headers,
        )

    def _include_routers(self):
        self._app.include_router(health_router)
        self._app.include_router(analytics_router)


if __name__ == "__main__":
    HawkerFlowAnalytics().start()
