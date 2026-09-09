import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "doctor.py"
SPEC = importlib.util.spec_from_file_location("doctor", SCRIPT)
doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(doctor)


def write_config(path, root, host="127.0.0.1"):
    path.write_text(f"""[platform]
host={host}
port=8080
data_root={root}/data
[storage]
workspace_root={root}/workspaces
state_root={root}/state
[model_gateway]
base_url=http://127.0.0.1:4001/v1
[metrics]
prometheus_port=9090
grafana_port=3001
""", encoding="utf-8")


def test_parse_layout_accepts_public_controller_but_requires_local_gateway(tmp_path):
    config = tmp_path / "config.cfg"
    write_config(config, tmp_path)
    ports, paths = doctor.parse_layout(config, tmp_path)
    assert ports == [8080, 9090, 3001, 4001]
    assert paths == [str(tmp_path / "data"), str(tmp_path / "workspaces"), str(tmp_path / "state")]
    write_config(config, tmp_path, host="0.0.0.0")
    assert doctor.parse_layout(config, tmp_path)[0] == ports
    config.write_text(config.read_text().replace("http://127.0.0.1:4001", "http://0.0.0.0:4001"))
    with pytest.raises(ValueError, match="loopback"):
        doctor.parse_layout(config, tmp_path)


def test_release_manifest_requires_controller_image_id(tmp_path):
    (tmp_path / "release-images.json").write_text(json.dumps({"images": {"cloud-agent-controller": {"id": "sha256:abc"}}}))
    assert doctor.read_release_image(tmp_path) == "sha256:abc"
    (tmp_path / "release-images.json").write_text(json.dumps({"images": {}}))
    with pytest.raises(KeyError):
        doctor.read_release_image(tmp_path)


def test_meminfo_and_version_parsing(tmp_path):
    source = tmp_path / "meminfo"
    source.write_text("MemTotal: 8388608 kB\nMemAvailable: 3145728 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n")
    assert doctor.read_meminfo(source)["MemAvailable"] == 3145728
    assert doctor.version_tuple("29.8.0-ce") == (29, 8, 0)


def test_write_probe_removes_probe(tmp_path):
    target = tmp_path / "state"
    doctor.write_probe([str(target)])
    assert target.is_dir()
    assert list(target.iterdir()) == []


def test_trial_admits_observed_host_without_changing_strict_policy():
    memory = dict(MemTotal=7869652, MemAvailable=4441856, SwapTotal=2035708, SwapFree=446748)
    strict = doctor.host_policy('29.7.2', memory, 'strict')
    assert not strict['docker_engine'] and not strict['memory']
    trial = doctor.host_policy('29.7.2', memory, 'coexistence-trial')
    assert trial['docker_engine'] and trial['memory'] and trial['warnings']
    assert not doctor.host_policy('29.7.1', memory, 'coexistence-trial')['docker_engine']
    memory['MemAvailable'] = 2 * 1024 * 1024
    assert not doctor.host_policy('29.7.2', memory, 'coexistence-trial')['memory']
    with pytest.raises(ValueError):
        doctor.host_policy('29.8.0', memory, 'ignore-everything')
