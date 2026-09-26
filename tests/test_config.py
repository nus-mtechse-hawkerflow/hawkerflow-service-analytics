"""Configuration tests.

These pin the security-relevant settings from the plan's Global Constraints:
the service must bind to loopback and must not open CORS to every origin.
"""

from pathlib import Path

import pytest

from configurations.app_config import AppConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def project_root(monkeypatch):
    monkeypatch.setenv("PROJECT_ROOT", str(PROJECT_ROOT))
    yield


@pytest.fixture
def config():
    return AppConfig()


def test_config_loads_from_the_repository_resources(config):
    assert config.service.title == "HawkerFlow Service Analytics"
    assert config.datasource.database.name == "hawkerflow_order_db"


def test_service_binds_to_loopback_only(config):
    assert config.service.host == "127.0.0.1"
    assert config.service.port == 8083


def test_cors_names_one_origin_and_never_a_wildcard(config):
    assert config.service.allow_origins == ["http://localhost:4200"]
    assert "*" not in config.service.allow_origins


def test_only_read_methods_are_allowed(config):
    assert config.service.methods == ["GET"]
    for unsafe in ("POST", "PUT", "PATCH", "DELETE", "*"):
        assert unsafe not in config.service.methods


def test_credentials_are_read_from_the_gitignored_vault(config):
    assert config.datasource.options.user.get_secret_value()
    assert config.datasource.options.password.get_secret_value()


def test_secrets_never_appear_in_the_repr(config):
    rendered = repr(config)

    assert "SecretStr" in rendered
    assert config.datasource.options.password.get_secret_value() not in rendered


def test_config_declares_no_queue_or_event_settings(config):
    assert not hasattr(config, "sqs")
    assert not hasattr(config, "events")


def test_vault_and_local_config_are_gitignored():
    ignored = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "vault/" in ignored
    assert "resources/config.local.yml" in ignored
