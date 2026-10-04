"""Configuration tests.

These pin what the deployed service depends on: the address it is served
under, the port the load balancer targets, and that connection details come
from the environment rather than from a file in the image.
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


def test_service_listens_where_the_load_balancer_expects(config):
    assert config.service.host == "0.0.0.0"
    assert config.service.port == 8080


def test_public_path_avoids_the_word_blockers_refuse(config):
    # Ad and tracker blockers drop browser requests whose path contains
    # /analytics/, which left the hawker dashboard unable to load.
    assert config.service.root_path == "/insights"
    assert "analytics" not in config.service.root_path


def test_config_yml_carries_no_database_address_or_credentials():
    shipped = (PROJECT_ROOT / "resources" / "config.yml").read_text(encoding="utf-8")

    for key in ("host:", "password", "user:"):
        assert key not in shipped.split("datasource:")[1]


def test_config_declares_no_queue_or_event_settings(config):
    assert not hasattr(config, "sqs")
    assert not hasattr(config, "events")


def test_vault_and_local_config_are_gitignored():
    ignored = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "vault/" in ignored
    assert "resources/config.local.yml" in ignored
