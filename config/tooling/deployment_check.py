"""Check the effective API port without printing Compose credentials."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.request


def command(root, *args):
    result = subprocess.run(args, cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Deployment command failed; inspect ./compose.sh ps -a and ./compose.sh logs --tail=80 api_gateway')
    return result.stdout


def published(bindings, target, host, port):
    return any(
        int(binding['HostPort']) == port
        and binding['HostIp'] in {host, '0.0.0.0', '::', ''}
        for binding in (bindings.get(f'{target}/tcp') or [])
    )


def check(root, phase):
    root = Path(root).resolve()
    config = json.loads(command(root, 'sh', './compose.sh', 'config', '--format', 'json'))
    gateway = config['services']['api_gateway']
    ports = [p for p in gateway.get('ports', []) if p.get('protocol', 'tcp') == 'tcp']
    if not ports:
        if json.loads((root / 'manifest.json').read_text()).get('mode') == 'domain':
            print('Domain deployment: API gateway has no direct host port; verify HTTPS separately.')
            return
        raise ValueError('IP deployment is missing api_gateway ports in the effective Compose configuration.')
    for mapping in ports:
        target, port = int(mapping['target']), int(mapping['published'])
        host = mapping.get('host_ip', '0.0.0.0')
        def has_binding():
            ids = command(root, 'sh', './compose.sh', 'ps', '-a', '-q', 'api_gateway').split()
            if not ids:
                return False
            containers = json.loads(command(root, 'docker', 'inspect', *ids))
            return any(c['State']['Running'] and published(c['NetworkSettings']['Ports'], target, host, port)
                       for c in containers)
        if phase == 'pre':
            if has_binding():
                continue
            family = socket.AF_INET6 if ':' in host else socket.AF_INET
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                try:
                    probe.bind((host, port))
                except OSError:
                    raise ValueError(f'Host API port {host}:{port} is occupied. Inspect sudo ss -ltnp and docker ps; stop the identified conflicting service or change API_PORT in .env. No services were stopped.') from None
        else:
            if not has_binding():
                print('API port mapping missing; recreating only api_gateway to restore it.', flush=True)
                command(root, 'sh', './compose.sh', 'up', '-d', '--no-deps', '--force-recreate', '--wait', 'api_gateway')
            if not has_binding():
                raise ValueError('API gateway still has no published port after recreation; inspect Docker networking.')
            address = '127.0.0.1' if host in ('0.0.0.0', '') else ('[::1]' if host == '::' else host)
            if ':' in address and not address.startswith('['):
                address = '[' + address + ']'
            url = f'http://{address}:{port}/cloud/health'
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for attempt in range(10):
                try:
                    with opener.open(url, timeout=3) as response:
                        if response.status != 200:
                            raise ValueError('Unexpected health status')
                    print(f'Host API health verified: {url}')
                    break
                except (OSError, ValueError):
                    if attempt == 9:
                        raise ValueError(f'Host API health failed: {url}; inspect ./compose.sh logs --tail=80 api_gateway') from None
                    time.sleep(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--phase', choices=['pre', 'post'], required=True)
    args = parser.parse_args()
    try:
        check(args.root, args.phase)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, str(error) + '\n')
