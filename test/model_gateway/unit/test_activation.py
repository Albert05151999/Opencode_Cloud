import copy
import pytest
from fastapi import HTTPException
from model_gateway.src.state import GatewayState


def release(name="one"):
    return {
        "release_id": name,
        "version": 1,
        "configuration": {
            "model_list": [
                {"model_name": "sample", "litellm_params": {"model": "openai/sample"}}
            ]
        },
    }


def test_activation_idempotence_conflict_restart_and_rollback(tmp_path):
    gateway = GatewayState(tmp_path, lambda config: config)
    assert not gateway.status()["ready"]
    assert gateway.activate(release())["ready"]
    gateway.activate(release())
    changed = release()
    changed["version"] = 2
    with pytest.raises(HTTPException) as error:
        gateway.activate(changed)
    assert error.value.status_code == 409
    gateway.activate(release("two"))
    restarted = GatewayState(tmp_path, lambda config: config)
    assert restarted.status()["release_id"] == "two"
    assert restarted.rollback("two")["release_id"] == "one"
    assert GatewayState(tmp_path, lambda config: config).status()["release_id"] == "one"


def test_failed_router_keeps_old_release(tmp_path):
    def factory(config):
        if not config["model_list"]:
            raise ValueError("invalid")
        return config

    gateway = GatewayState(tmp_path, factory)
    gateway.activate(release())
    invalid = release("broken")
    invalid["configuration"]["model_list"] = []
    with pytest.raises(ValueError):
        gateway.activate(invalid)
    assert gateway.status()["release_id"] == "one"
    assert GatewayState(tmp_path, factory).status()["release_id"] == "one"
