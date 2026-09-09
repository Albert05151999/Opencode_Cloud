#!/usr/bin/env python3
"""Run real provider bursts; retain failed gates without marking acceptance complete."""
import argparse
import asyncio
import importlib.util
import json
import shutil
import socket
import tempfile
import time
import httpx
from dataclasses import replace
from pathlib import Path

import uvicorn

from app.config import load_config
from app.main import build_app

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = "stage29-verification"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


async def verify_client(warm_rounds=10, cold_rounds=5):
    load = module("cloud_load_client", "tests/load/run_load.py")
    with tempfile.TemporaryDirectory(prefix="cloud-stage29-") as temporary:
        directory = Path(temporary)
        shutil.copytree(ROOT / "agents", directory / "agents")
        config = load_config(ROOT / "config.cfg")
        config = replace(config, platform=replace(config.platform, instance_id=INSTANCE, data_root=str(directory)), storage=replace(config.storage, workspace_root=str(directory / "workspaces"), state_root=str(directory / "state")))
        app = build_app(config, directory / "agents")
        backend = app.state.backend
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        listener.bind(("127.0.0.1", 0))
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            async with asyncio.timeout(15):
                while not server.started:
                    if task.done():
                        await task
                    await asyncio.sleep(0.05)
            output = ROOT / "artifacts/perf/concurrency" / time.strftime("run-%Y%m%d-%H%M%S")
            output.mkdir(parents=True, exist_ok=True)
            report = {"result": "running", "rounds": [], "acquires": [], "routing_failures": 0, "pending_gates": ["native proxy overhead", "model gateway overhead versus physical backend"]}
            all_records = []
            original_acquire = backend.acquire
            phase = "cold"
            async def measured_acquire(agent, user):
                started = time.perf_counter()
                endpoint = await original_acquire(agent, user)
                report["acquires"].append({"phase": phase, "reused": endpoint.reused, "duration_ms": (time.perf_counter()-started)*1000})
                return endpoint
            backend.acquire = measured_acquire
            try:
                for phase, rounds in [("cold", cold_rounds), ("warm", warm_rounds)]:
                    for index in range(rounds):
                        if phase == 'cold' and index:
                            async with asyncio.timeout(10):
                                while backend.in_use:
                                    await asyncio.sleep(0.05)
                            for container in backend.client.containers.list(all=True, filters={'label': f'cloud.platform_instance={INSTANCE}'}):
                                assert container.labels.get('cloud.platform_instance') == INSTANCE
                                await asyncio.to_thread(container.remove, force=True)
                        path = output / f"{phase}-{index}"
                        summary = await load.run(f"http://127.0.0.1:{listener.getsockname()[1]}", rounds=1, output=path, timeout=120)
                        report["rounds"].append({"phase": phase, "index": index, "summary": summary})
                        records = json.loads(path.with_suffix('.json').read_text())["requests"]
                        all_records.extend(records)
                        for record in records:
                            route = backend.registry.get_session_route(record['session_id']) if record['session_id'] else None
                            if route is None or (route.agent_id, route.username) != (record['agent_id'], record['username']):
                                report['routing_failures'] += 1
                        print(json.dumps({"phase": phase, "round": index, "failures": summary["failures"]}), flush=True)
                        if summary['failures'] or report['routing_failures']:
                            report['failure_diagnostics'] = []
                            async with httpx.AsyncClient(timeout=10, trust_env=False) as diagnostic:
                                for record in records:
                                    if record['status'] == 'passed' or not record['session_id']:
                                        continue
                                    endpoint = await backend.inspect(record['agent_id'], record['username'])
                                    if endpoint is None:
                                        continue
                                    messages = await diagnostic.get(endpoint.base_url + '/session/' + record['session_id'] + '/message')
                                    detail = {'request_id': record['request_id'], 'messages_http_status': messages.status_code}
                                    if messages.is_success:
                                        detail['messages'] = [{'role': m.get('info', {}).get('role'), 'finish': m.get('info', {}).get('finish'), 'error_name': (m.get('info', {}).get('error') or {}).get('name'), 'parts': [{'type': p.get('type'), 'tool': p.get('tool'), 'status': p.get('state', {}).get('status'), 'input': p.get('state', {}).get('input'), 'time': p.get('state', {}).get('time'), 'error': str(p.get('state', {}).get('error', ''))[:1000]} for p in m.get('parts', [])]} for m in messages.json()]
                                    detail['native_status'] = (await diagnostic.get(endpoint.base_url + '/session/status')).json()
                                    report['failure_diagnostics'].append(detail)
                                    await diagnostic.post(endpoint.base_url + '/session/' + record['session_id'] + '/abort')
                            raise RuntimeError('burst validation failed')
                async with asyncio.timeout(10):
                    while backend.in_use:
                        await asyncio.sleep(0.05)
                phase = 'validation'
                report['isolation_checks'] = {'message_markers': 0, 'sse_owner_checks': 0, 'cross_user_rejections': 0, 'model_routes': 0}
                native_sessions = {}
                async with httpx.AsyncClient(timeout=30, trust_env=False) as check:
                    for owner in {(r['agent_id'], r['username']) for r in all_records}:
                        endpoint = await backend.inspect(*owner)
                        response = await check.get(endpoint.base_url + '/session')
                        response.raise_for_status()
                        native_sessions[owner] = {item['id'] for item in response.json()}
                    owners = list(native_sessions)
                    for index, owner in enumerate(owners):
                        for other in owners[index+1:]:
                            assert not native_sessions[owner] & native_sessions[other], 'shared native sessions'
                    for record in all_records:
                        owner = (record['agent_id'], record['username'])
                        sid = record['session_id']
                        assert sid in native_sessions[owner]
                        assert sid in record['sse_session_ids'], 'missing own SSE evidence'
                        assert set(record['sse_session_ids']) <= native_sessions[owner], 'cross-owner SSE event'
                        report['isolation_checks']['sse_owner_checks'] += 1
                        base = f'http://127.0.0.1:{listener.getsockname()[1]}'
                        response = await check.get(base + '/session/' + sid + '/message')
                        response.raise_for_status()
                        messages = response.json()
                        user_text = [part.get('text', '') for m in messages if m.get('info', {}).get('role') == 'user' for part in m.get('parts', []) if part.get('type') == 'text']
                        assert 'Reply briefly: ' + record['request_id'] in user_text, 'wrong message content'
                        report['isolation_checks']['message_markers'] += 1
                        assistants = [m['info'] for m in messages if m.get('info', {}).get('role') == 'assistant']
                        assert assistants and all(m.get('modelID') == record['logical_model'] and m.get('providerID') == 'cloud-model-gateway' for m in assistants), 'wrong model route'
                        report['isolation_checks']['model_routes'] += 1
                        response = await check.get(base + '/session/' + sid, headers={'X-Cloud-Username': 'bob' if owner[1] == 'alice' else 'alice'})
                        assert response.status_code == 409, 'cross-user route not rejected'
                        report['isolation_checks']['cross_user_rejections'] += 1
                from prometheus_client.parser import text_string_to_metric_families
                report['http_5xx'] = sum(sample.value for family in text_string_to_metric_families(app.state.metrics.render().decode()) for sample in family.samples if sample.name == 'cloud_http_requests_total' and int(sample.labels.get('status', 0)) >= 500)
                assert report['http_5xx'] == 0
                async with asyncio.timeout(10):
                    while backend.in_use:
                        await asyncio.sleep(0.05)
                report['leases_after_disconnect'] = 0
                report['result'] = 'component_passed'
            except Exception as exc:
                report.update(result='failed', error=type(exc).__name__)
                raise
            finally:
                report['acquire_summary_ms'] = {}
                for category in ('cold', 'warm'):
                    values = [x['duration_ms'] for x in report['acquires'] if x['phase'] == category and (category == 'warm' or not x['reused'])]
                    report['acquire_summary_ms'][category] = {'count': len(values), 'p50': load.percentile(values, 0.5), 'p95': load.percentile(values, 0.95)}
                report['timing_gates'] = {category: values['p95'] is not None and values['p95'] <= limit for category, limit in [('cold', 5000), ('warm', 500)] for values in [report['acquire_summary_ms'][category]]}
                if not all(report['timing_gates'].values()):
                    report['result'] = 'failed'
                (output / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
                (output / 'controller.prom').write_bytes(app.state.metrics.render())
            assert all(report['timing_gates'].values()), report['acquire_summary_ms']

        finally:
            for container in backend.client.containers.list(all=True, filters={"label": f"cloud.platform_instance={INSTANCE}"}):
                if container.labels.get("cloud.platform_instance") != INSTANCE:
                    raise RuntimeError("container ownership mismatch")
                container.remove(force=True)
            server.should_exit = True
            await task
            listener.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--warm-rounds", type=int, default=10)
    parser.add_argument("--cold-rounds", type=int, default=5)
    args = parser.parse_args()
    if args.warm_rounds < 1 or args.cold_rounds < 1:
        parser.error("warm rounds must be positive")
    asyncio.run(verify_client(args.warm_rounds, args.cold_rounds))
