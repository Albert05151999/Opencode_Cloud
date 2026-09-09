from pathlib import Path

import pytest

from app.config import ConfigurationError, load_config, parse_csv


ROOT = Path(__file__).resolve().parents[2]


def config_copy(tmp_path: Path, replacement: tuple[str, str] | None = None) -> Path:
    text = (ROOT / "config.cfg").read_text(encoding="utf-8")
    if replacement:
        text = text.replace(*replacement)
    path = tmp_path / "config.cfg"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_typed_values_and_csv() -> None:
    config = load_config(ROOT / "config.cfg", environ={})
    assert config.platform.port == 18080
    assert config.sandbox.default_cpu == 4.0
    assert config.sandbox.read_only_rootfs is True
    assert parse_csv("agent-code, agent-data,,") == ("agent-code", "agent-data")


def test_environment_overrides_known_value() -> None:
    config = load_config(
        ROOT / "config.cfg",
        environ={"CLOUD_AGENT__SANDBOX__DEFAULT_MEMORY_MB": "6144"},
    )
    assert config.sandbox.default_memory_mb == 6144


def test_sqlite_sync_policy_is_explicit_and_rejects_off(tmp_path):
    assert load_config(ROOT / 'config.cfg', environ={}).platform.sqlite_synchronous == 'NORMAL'
    assert load_config(ROOT / 'config.cfg', environ={'CLOUD_AGENT__PLATFORM__SQLITE_SYNCHRONOUS': 'FULL'}).platform.sqlite_synchronous == 'FULL'
    with pytest.raises(ConfigurationError, match='NORMAL or FULL'):
        load_config(ROOT / 'config.cfg', environ={'CLOUD_AGENT__PLATFORM__SQLITE_SYNCHRONOUS': 'OFF'})
    old = config_copy(tmp_path, ('sqlite_synchronous = NORMAL', ''))
    assert load_config(old, environ={}).platform.sqlite_synchronous == 'FULL'


@pytest.mark.parametrize(
    "environment",
    [
        {"CLOUD_AGENT__SANDBOX__UNKNOWN": "1"},
        {"CLOUD_AGENT__SANDBOX__DEFAULT_MEMORY_MB__EXTRA": "1"},
        {"CLOUD_AGENT__PLATFORM__PORT": "70000"},
    ],
)
def test_rejects_invalid_environment(environment: dict[str, str]) -> None:
    with pytest.raises(ConfigurationError):
        load_config(ROOT / "config.cfg", environ=environment)


def test_rejects_relative_storage_path(tmp_path: Path) -> None:
    path = config_copy(tmp_path, ("workspace_root = /srv/cloud-agent/workspaces", "workspace_root = relative"))
    with pytest.raises(ConfigurationError, match="absolute normalized"):
        load_config(path, environ={})


def test_rejects_secret_in_ini(tmp_path: Path) -> None:
    path = config_copy(tmp_path, ("routing_strategy = least-busy", "routing_strategy = least-busy\nprovider_api_key = forbidden"))
    with pytest.raises(ConfigurationError, match="must use the environment"):
        load_config(path, environ={})


def test_rejects_disabled_startup_safety_flag(tmp_path: Path) -> None:
    path = config_copy(tmp_path, ("startup_disable_autoupdate = true", "startup_disable_autoupdate = false"))
    with pytest.raises(ConfigurationError, match="flags must stay enabled"):
        load_config(path, environ={})
