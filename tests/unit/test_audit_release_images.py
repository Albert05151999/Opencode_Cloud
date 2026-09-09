import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit-release-images.py"
SPEC = importlib.util.spec_from_file_location("audit_release_images", SCRIPT)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_scan_detects_sensitive_env_secret_and_development_home():
    inspect = {"Config": {"Env": ["SERVICE_API_KEY=actual-secret"], "WorkingDir": "C:\\Users\\alice\\src"}}
    errors = audit.scan(inspect, [{"CreatedBy": "RUN use actual-secret"}], ["actual-secret"])
    assert errors == {"embedded_sensitive_env", "embedded_env_secret", "development_home_path"}


def test_scan_allows_empty_and_symbolic_placeholders_and_production_home():
    inspect = {
        "Config": {
            "Env": ["API_KEY=", "ACCESS_TOKEN=${ACCESS_TOKEN}", "DB_PASSWORD=<injected>"],
            "WorkingDir": "/home/opencode/workspace",
        }
    }
    assert audit.scan(inspect, [{"CreatedBy": "ENV API_KEY=__RUNTIME__"}], []) == set()


def test_scan_detects_sensitive_assignment_in_history_without_env_file():
    assert audit.scan({"Config": {}}, [{"CreatedBy": "ENV BUILD_TOKEN=secret-value"}], []) == {
        "embedded_sensitive_env"
    }


def test_scan_detects_reference_machine_home():
    assert audit.scan({"Config": {"WorkingDir": "/home/zephyrusg14/projects/cloud-agent"}}, [], []) == {
        "development_home_path"
    }


def test_parse_env_keeps_only_real_sensitive_values_in_memory(tmp_path):
    env = tmp_path / ".env"
    env.write_text("NORMAL=value\nAPI_KEY='real-key'\nTOKEN=${TOKEN}\nPASSWORD=\n", encoding="utf-8")
    assert audit.parse_env_file(env) == ["real-key"]
