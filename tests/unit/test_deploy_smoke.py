import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load_smoke():
    spec = importlib.util.spec_from_file_location("deploy_smoke", ROOT / "deploy" / "smoke.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_burst_reports_actual_seven_successes(monkeypatch) -> None:
    smoke = load_smoke()

    def one(_client, _agent, _username, _model, marker):
        if marker.endswith("agent-data-1-1"):
            raise smoke.SmokeError("InjectedFailure", 503)
        return "ses_" + marker, marker

    monkeypatch.setattr(smoke, "burst_one", one)
    sessions = []
    result = smoke.burst_smoke(object(), "fixture", sessions)
    assert result["requests"] == 8
    assert result["successes"] == 7
    assert result["failures"] == [{
        "marker": "stage35-fixture-agent-data-1-1",
        "error_code": "InjectedFailure",
        "status": 503,
    }]
    assert len(sessions) == 7


def test_partial_session_pair_is_already_tracked_for_cleanup(monkeypatch) -> None:
    smoke = load_smoke()
    calls = 0

    class ReadyClient:
        def json(self, method, path, payload=None, **kwargs):
            if path == "/doc":
                return 200, {}, {"paths": {"/api/session": {}}, "x-cloud-routing": {}}
            assert (method, path) == ("GET", "/cloud/health/ready")
            return 200, {}, {"ok": True}

    def create(_client, _agent, _username):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise smoke.SmokeError("InjectedCreateFailure", 503)
        return "ses_first"

    monkeypatch.setattr(smoke, "create_session", create)
    sessions = []
    with pytest.raises(smoke.SmokeError, match="InjectedCreateFailure"):
        smoke.ordinary_smoke(ReadyClient(), "fixture", sessions)
    assert sessions == ["ses_first"]
