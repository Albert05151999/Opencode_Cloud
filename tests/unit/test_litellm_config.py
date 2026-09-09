from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[2]
LITELLM_PATH = ROOT / "config" / "litellm_config.yaml"
COMPOSE_PATH = ROOT / "deploy" / "docker-compose.yml"
VERSIONS_PATH = ROOT / "versions.env"

EXPECTED_GROUPS = {
    "coding-fast",
    "coding-quality",
    "data-fast",
    "data-quality",
}
ENV_REFERENCE = re.compile(r"^os\.environ/[A-Z][A-Z0-9_]*$")
IMAGE_REFERENCE = re.compile(
    r"^ghcr\.io/berriai/litellm:v(?P<version>[^@]+)@(?P<digest>sha256:[0-9a-f]{64})$"
)


def load_yaml(path: Path) -> dict[str, object]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def load_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in VERSIONS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        assert separator and key and value
        assert key not in result
        result[key] = value
    return result


def test_four_logical_groups_have_exactly_two_deployments_and_unique_ids() -> None:
    config = load_yaml(LITELLM_PATH)
    models = config["model_list"]
    assert isinstance(models, list)

    names = [entry["model_name"] for entry in models]
    assert set(names) == EXPECTED_GROUPS
    assert Counter(names) == {name: 2 for name in EXPECTED_GROUPS}

    deployment_ids = [entry["model_info"]["id"] for entry in models]
    assert len(deployment_ids) == 8
    assert len(set(deployment_ids)) == len(deployment_ids)
    for name in EXPECTED_GROUPS:
        assert {
            entry["model_info"]["id"]
            for entry in models
            if entry["model_name"] == name
        } == {f"{name}-1", f"{name}-2"}


def test_every_provider_value_comes_from_the_environment_and_has_no_secret() -> None:
    config = load_yaml(LITELLM_PATH)
    raw = LITELLM_PATH.read_text(encoding="utf-8")

    for deployment in config["model_list"]:
        params = deployment["litellm_params"]
        assert set(("model", "api_base", "api_key")).issubset(params)
        for key in ("model", "api_base", "api_key"):
            value = params[key]
            assert isinstance(value, str)
            assert ENV_REFERENCE.fullmatch(value), (deployment["model_name"], key, value)

    lowered = raw.lower()
    assert "sk-" not in lowered
    assert "bearer " not in lowered
    assert "api_key:" in lowered
    assert not re.search(
        r"(?im)^\s*(api_key|master_key)\s*:\s*(?!os\.environ/)[^\s#]+",
        raw,
    )


def test_router_resilience_and_timeout_contract_is_exact() -> None:
    router = load_yaml(LITELLM_PATH)["router_settings"]
    assert isinstance(router, dict)
    assert router == {
        "routing_strategy": "least-busy",
        "num_retries": 2,
        "timeout": 600,
        "allowed_fails": 1,
        "cooldown_time": 30,
    }
    assert router["num_retries"] > 0
    assert router["timeout"] > 0
    assert router["allowed_fails"] > 0
    assert router["cooldown_time"] > 0


def test_prometheus_callback_and_stream_label_are_enabled() -> None:
    settings = load_yaml(LITELLM_PATH)["litellm_settings"]
    assert isinstance(settings, dict)
    assert "prometheus" in settings["callbacks"]
    assert settings["prometheus_emit_stream_label"] is True
    assert settings["require_auth_for_metrics_endpoint"] is False


def test_compose_image_tag_and_digest_match_versions_file() -> None:
    compose = load_yaml(COMPOSE_PATH)
    service = compose["services"]["model-gateway"]
    image = service["image"]
    versions = load_versions()
    match = IMAGE_REFERENCE.fullmatch(image)

    assert match is not None
    assert match.group("version") == versions["LITELLM_VERSION"]
    assert match.group("digest") == versions["LITELLM_IMAGE_DIGEST"]
    assert versions["LITELLM_VERSION"] not in {"latest", "main", "master"}
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", versions["LITELLM_IMAGE_DIGEST"])


def test_compose_has_loopback_config_health_and_container_hardening() -> None:
    compose = load_yaml(COMPOSE_PATH)
    service = compose["services"]["model-gateway"]

    assert service["ports"] == [
        "127.0.0.1:4001:4000",
        "${MODEL_GATEWAY_BRIDGE_IP:?use scripts/model-gateway.sh}:4001:4000",
    ]
    assert service["volumes"] == [
        "../config/litellm_config.yaml:/app/config.yaml:ro",
        "./cloud_logging.py:/app/cloud_logging.py:ro",
    ]
    assert service["command"] == ["--config", "/app/config.yaml", "--port", "4000"]
    assert service["extra_hosts"] == ["host.docker.internal:host-gateway"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert service["cap_drop"] == ["ALL"]

    health = service["healthcheck"]
    assert health["test"][0] == "CMD"
    assert "http://127.0.0.1:4000/health/liveliness" in health["test"][-1]
    assert health["interval"]
    assert health["timeout"]
    assert health["retries"] > 0
    assert health["start_period"]


def test_compose_passes_every_referenced_environment_variable_without_literals() -> None:
    litellm = load_yaml(LITELLM_PATH)
    compose = load_yaml(COMPOSE_PATH)
    environment = compose["services"]["model-gateway"]["environment"]
    referenced = {
        value.removeprefix("os.environ/")
        for deployment in litellm["model_list"]
        for key, value in deployment["litellm_params"].items()
        if key in {"model", "api_base", "api_key"}
    }

    assert set(environment) == referenced
    for name, value in environment.items():
        assert value == "$" + "{" + name + ":?set " + name + "}"
