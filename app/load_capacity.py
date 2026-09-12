"""Conservative admission budget for local Docker load tests; no resource reservation."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import math
from pathlib import Path
import time

from app.config import LoadCapacityConfig
from app.management import fail


def cpu_ticks():
    # guest times are already included in user/nice; do not count twice.
    values = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    return sum(values), values[3] + values[4]


def host_sample():
    before = cpu_ticks()
    time.sleep(.2)
    after = cpu_ticks()
    elapsed = after[0] - before[0]
    if elapsed <= 0:
        raise ValueError('CPU sample unavailable')
    values = {line.split(':')[0]: int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines()}
    return {'memory_mb': values['MemTotal'] / 1024, 'memory_available_mb': values['MemAvailable'] / 1024,
            'cpu_usage_percent': max(0, min(100, 100 * (1 - (after[1] - before[1]) / elapsed)))}


def calculate(info, host, containers, policy):
    total_cpu, total_memory = info['NCPU'], info['MemTotal'] / 1024**2
    if total_cpu <= 0 or total_memory <= 0 or abs(total_memory - host['memory_mb']) > total_memory * .05:
        raise ValueError('Docker daemon and /proc host do not agree')
    cpu, memory, growth = 0., 0., 0.
    unknown = []
    sandbox_count, running = 0, 0
    for item in containers:
        live = item['status'] in {'running', 'restarting', 'paused'}
        sandbox = bool(item['labels'].get('cloud.agent_id'))
        if not live and not sandbox:
            continue
        running += int(live)
        sandbox_count += int(live and sandbox)
        config = item['host_config']
        limit_cpu = config.get('NanoCpus', 0) / 1e9
        if not limit_cpu and config.get('CpuQuota', 0) > 0 and config.get('CpuPeriod', 0) > 0:
            limit_cpu = config['CpuQuota'] / config['CpuPeriod']
        limit_memory = config.get('Memory', 0) / 1024**2
        usage = item['memory_usage_mb'] if live else 0
        # Stopped sandboxes still have restartable allocations. Unlimited services
        # are covered by observed host usage and reserve; unlimited sandboxes block.
        if sandbox and (limit_cpu <= 0 or limit_memory <= 0):
            unknown.append(item['id'])
        cpu += max(0, limit_cpu)
        memory += max(0, limit_memory)
        growth += max(0, limit_memory - usage)
    reserved_cpu = max(policy.reserved_cpu, total_cpu * policy.reserve_fraction)
    reserved_memory = max(policy.reserved_memory_mb, total_memory * policy.reserve_fraction)
    remaining_cpu = total_cpu - reserved_cpu - cpu
    remaining_memory = min(total_memory - reserved_memory - memory,
                           host['memory_available_mb'] - reserved_memory - growth)
    reasons = []
    if unknown:
        reasons.append('存在未设置 CPU 或内存上限的沙箱，无法计算可分配预算')
    if host['cpu_usage_percent'] >= policy.max_cpu_usage_percent:
        reasons.append('服务器 CPU 当前繁忙，请等待负载下降')
    if remaining_cpu < 0 or remaining_memory < 0:
        reasons.append('当前配额或实际内存已侵占系统预留，请先释放资源')
    return {'known': True, 'sampled_at': time.time(), 'admission_allowed': not reasons, 'reasons': reasons,
        'cpu_count': total_cpu, 'memory_mb': round(total_memory, 1),
        'cpu_usage_percent': round(host['cpu_usage_percent'], 1),
        'memory_available_mb': round(host['memory_available_mb'], 1),
        'allocated_cpu': round(cpu, 3), 'allocated_memory_mb': round(memory, 1),
        'reserved_cpu': round(reserved_cpu, 3), 'reserved_memory_mb': round(reserved_memory, 1),
        'remaining_cpu': math.floor(max(0, remaining_cpu) * 1000) / 1000,
        'remaining_memory_mb': math.floor(max(0, remaining_memory)),
        'running_sandboxes': sandbox_count, 'running_containers': running,
        'unbounded_sandboxes': len(unknown), 'policy': asdict(policy)}


def check_capacity(snapshot, agents):
    if not snapshot.get('known') or time.time() - snapshot.get('sampled_at', 0) > 15:
        fail('服务器资源状态未知或已过期，暂不允许启动压测', 503)
    if not snapshot['admission_allowed']:
        fail('；'.join(snapshot['reasons']), 409)
    cpu = sum(a['cpu_limit'] * a.get('users', 1) for a in agents)
    memory = sum(a['memory_mb'] * a.get('users', 1) for a in agents)
    if cpu > snapshot['remaining_cpu'] + 1e-8 or memory > snapshot['remaining_memory_mb']:
        suggestions = []
        grouped = {}
        for a in agents:
            row = grouped.setdefault(a['agent_id'], {**a, 'users': 0})
            row['users'] += a.get('users', 1)
        for a in grouped.values():
            # Per-row maximum if other selected rows keep their requested count.
            other_cpu = cpu - a['cpu_limit'] * a.get('users', 1)
            other_memory = memory - a['memory_mb'] * a.get('users', 1)
            maximum = max(0, min(math.floor((snapshot['remaining_cpu'] - other_cpu) / a['cpu_limit']),
                                 math.floor((snapshot['remaining_memory_mb'] - other_memory) / a['memory_mb'])))
            suggestions.append(f"{a['agent_id']} 最多 {maximum} 用户（其他行不变）")
        fail(f"压测需要 {cpu:g} 核 / {memory:g} MiB，当前可分配 {snapshot['remaining_cpu']:g} 核 / {snapshot['remaining_memory_mb']:g} MiB。" + '；'.join(suggestions), 409)


class LoadCapacity:
    def __init__(self, backend):
        self.backend = backend
        self.policy = getattr(getattr(backend, 'config', None), 'load_capacity', LoadCapacityConfig())
        self._task = None
        self._cached = None

    def _sample(self):
        info = self.backend.client.info()
        containers = self.backend.client.containers.list(all=True)
        def inspect(container):
            container.reload()
            live = container.status in {'running', 'restarting', 'paused'}
            stats = container.stats(stream=False, one_shot=True) if live else {}
            usage = stats.get('memory_stats', {}).get('usage')
            if live and usage is None:
                raise ValueError('Container memory sample missing')
            memory_stats = stats.get('memory_stats', {}).get('stats', {})
            cache = memory_stats.get('total_cache', memory_stats.get('cache', memory_stats.get('file', 0)))
            # MemAvailable already credits reclaimable file cache. Do not also
            # treat that cache as consumed non-reclaimable quota.
            working = max(0, (usage or 0) - cache)
            return {'id': container.id, 'status': container.status, 'labels': container.attrs['Config'].get('Labels') or {},
                    'host_config': container.attrs['HostConfig'], 'memory_usage_mb': working / 1024**2}
        with ThreadPoolExecutor(max_workers=4) as pool:
            host = pool.submit(host_sample)
            observed = list(pool.map(inspect, containers))
            return calculate(info, host.result(), observed, self.policy)

    async def snapshot(self, fresh=False):
        if not fresh and self._cached and time.time() - self._cached['sampled_at'] < 5:
            return self._cached
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(asyncio.to_thread(self._sample))
        try:
            self._cached = await asyncio.wait_for(asyncio.shield(self._task), 8)
            return self._cached
        except Exception:
            self._cached = None
            # Do not reuse stale green status or spawn more sampling threads while
            # a timed-out Docker call is still running.
            return {'known': False, 'sampled_at': time.time(), 'admission_allowed': False,
                    'reasons': ['无法读取服务器资源状态，请检查 Docker 和宿主机监测'], 'policy': asdict(self.policy)}
