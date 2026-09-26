from fastapi import FastAPI
from fastapi.testclient import TestClient

from endpoints.health_routes import health_router


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(health_router)
    return TestClient(app)


def test_health_reports_ok_without_touching_the_database():
    response = build_client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "analytics"}


def test_health_response_carries_no_credentials():
    body = build_client().get("/health").text.lower()

    assert "password" not in body
    assert "postgres" not in body
    assert "@" not in body
