#!/usr/bin/env python3
"""Run or aggregate all stage-29 gates; never accept missing component evidence."""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fingerprint():
    paths = [ROOT / 'config.cfg', ROOT / 'pyproject.toml', ROOT / 'config/litellm_config.yaml']
    paths += list((ROOT / 'app').glob('*.py'))
    paths += [p for p in (ROOT / 'agents').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def check(concurrency, native, ttft):
    counts = sum(item['summary']['request_count'] for item in concurrency['rounds'])
    assert concurrency['result'] == 'component_passed'
    assert counts >= 120
    assert all(item['summary']['failures'] == 0 for item in concurrency['rounds'])
    assert concurrency['routing_failures'] == concurrency['http_5xx'] == concurrency['leases_after_disconnect'] == 0
    assert all(concurrency['isolation_checks'][key] == counts for key in ('message_markers', 'sse_owner_checks', 'cross_user_rejections', 'model_routes'))
    for name, minimum, maximum in [('cold', 20, 5000), ('warm', 240, 500)]:
        values = concurrency['acquire_summary_ms'][name]
        assert values['count'] >= minimum and values['p95'] <= maximum
    assert native['result'] == 'passed' and native['overhead_ms']['count'] >= 160
    assert native['overhead_ms']['p95'] <= 100 and native['leases_after_requests'] == 0
    assert set(native['operations_p95_ms']) == {'health', 'list_sessions', 'create_session', 'get_session'}
    assert all(value <= 100 for value in native['operations_p95_ms'].values())
    assert ttft['result'] == 'passed' and not ttft.get('cleanup_errors')
    assert set(ttft['models']) == {'coding-fast', 'coding-quality', 'data-fast', 'data-quality'}
    assert ttft['image']['same_image_id']
    assert ttft['config']['sha256'] == hashlib.sha256((ROOT / 'config/litellm_config.yaml').read_bytes()).hexdigest()
    assert all(item['passed'] and item['samples'] >= 20 and item['paired_overhead_p95_ms'] <= 300 for item in ttft['models'].values())
    return {'request_count': counts, 'cold_p95_ms': concurrency['acquire_summary_ms']['cold']['p95'], 'warm_p95_ms': concurrency['acquire_summary_ms']['warm']['p95'], 'native_overhead_p95_ms': native['overhead_ms']['p95'], 'model_gateway_overhead_p95_ms': {name: item['paired_overhead_p95_ms'] for name, item in ttft['models'].items()}}


def run(script, directory):
    before = set(directory.glob('run-*/report.json'))
    subprocess.run([sys.executable, str(ROOT / 'scripts' / script)], cwd=ROOT, check=True)
    created = set(directory.glob('run-*/report.json')) - before
    assert len(created) == 1, 'expected one new component report'
    return created.pop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reports', type=Path, nargs=3, metavar=('CONCURRENCY', 'NATIVE', 'TTFT'), help='Aggregate MainAgent-reviewed saved evidence; omit to run the entire verification')
    args = parser.parse_args()
    before = fingerprint()
    report = {'result': 'running', 'started_at': datetime.now(timezone.utc).isoformat(), 'mode': 'reviewed_saved_evidence' if args.reports else 'fresh_verification', 'source_sha256': before}
    output = ROOT / 'artifacts/perf/stage29-report.json'
    try:
        if args.reports:
            paths = args.reports
        else:
            subprocess.run([sys.executable, '-m', 'pytest', 'tests/unit', '-q'], cwd=ROOT, check=True)
            subprocess.run([sys.executable, 'scripts/verify-health.py'], cwd=ROOT, check=True)
            native = run('verify-native-overhead.py', ROOT / 'artifacts/perf/native-overhead')
            concurrency = run('verify-concurrency.py', ROOT / 'artifacts/perf/concurrency')
            ttft = run('verify-gateway-ttft.py', ROOT / 'artifacts/perf/gateway-ttft')
            paths = [concurrency, native, ttft]
        report['evidence'] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        report['gates'] = check(*(json.loads(path.read_text()) for path in paths))
        assert fingerprint() == before, 'production sources changed during verification'
        report['result'] = 'passed'
    except Exception as exc:
        report.update(result='failed', error=type(exc).__name__)
        raise
    finally:
        output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'result': report['result'], 'gates': report['gates']}, indent=2))


if __name__ == '__main__':
    main()
