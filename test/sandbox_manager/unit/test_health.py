from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sandbox_manager.health import HealthMonitor


def monitor_with_records(count: int) -> HealthMonitor:
    records = [SimpleNamespace(sandbox_id=f"sandbox-{index}") for index in range(count)]
    backend = SimpleNamespace(
        registry=SimpleNamespace(list_sandboxes=lambda: records),
    )
    monitor = HealthMonitor(backend, SimpleNamespace(), SimpleNamespace())

    async def model_health() -> bool:
        return True

    monitor.model_health = model_health
    return monitor


def test_tick_uses_at_most_four_workers_and_continues_after_record_failure() -> None:
    async def scenario() -> None:
        monitor = monitor_with_records(8)
        release_first_wave = asyncio.Event()
        first_wave_started = asyncio.Event()
        active = 0
        maximum = 0
        started: list[str] = []
        completed: list[str] = []

        async def check(snapshot, now) -> None:
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            started.append(snapshot.sandbox_id)
            if len(started) == 4:
                first_wave_started.set()
            try:
                if snapshot.sandbox_id in {"sandbox-0", "sandbox-1", "sandbox-2", "sandbox-3"}:
                    await release_first_wave.wait()
                if snapshot.sandbox_id == "sandbox-1":
                    raise RuntimeError("injected record failure")
                completed.append(snapshot.sandbox_id)
            finally:
                active -= 1

        monitor._check_sandbox = check
        task = asyncio.create_task(monitor.tick())
        await asyncio.wait_for(first_wave_started.wait(), timeout=1)
        await asyncio.sleep(0)
        assert maximum == 4
        assert started == [f"sandbox-{index}" for index in range(4)]

        release_first_wave.set()
        await asyncio.wait_for(task, timeout=1)
        assert maximum == 4
        assert set(started) == {f"sandbox-{index}" for index in range(8)}
        assert set(completed) == {f"sandbox-{index}" for index in range(8)} - {"sandbox-1"}

    asyncio.run(scenario())


def test_one_slow_record_does_not_block_the_remaining_queue() -> None:
    async def scenario() -> None:
        monitor = monitor_with_records(7)
        slow_started = asyncio.Event()
        release_slow = asyncio.Event()
        others_done = asyncio.Event()
        completed: list[str] = []

        async def check(snapshot, now) -> None:
            if snapshot.sandbox_id == "sandbox-0":
                slow_started.set()
                await release_slow.wait()
            completed.append(snapshot.sandbox_id)
            if len(completed) == 6:
                others_done.set()

        monitor._check_sandbox = check
        task = asyncio.create_task(monitor.tick())
        await asyncio.wait_for(slow_started.wait(), timeout=1)
        await asyncio.wait_for(others_done.wait(), timeout=1)
        assert "sandbox-0" not in completed
        release_slow.set()
        await asyncio.wait_for(task, timeout=1)
        assert len(completed) == 7

    asyncio.run(scenario())


def test_tick_lock_prevents_overlapping_ticks() -> None:
    async def scenario() -> None:
        monitor = monitor_with_records(1)
        entered = asyncio.Event()
        release = asyncio.Event()
        checks = 0

        async def check(snapshot, now) -> None:
            nonlocal checks
            checks += 1
            entered.set()
            await release.wait()

        monitor._check_sandbox = check
        first = asyncio.create_task(monitor.tick())
        await asyncio.wait_for(entered.wait(), timeout=1)
        second = asyncio.create_task(monitor.tick())
        await asyncio.sleep(0.05)
        assert checks == 1
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=1)
        assert checks == 2

    asyncio.run(scenario())


def test_tick_cancellation_propagates() -> None:
    async def scenario() -> None:
        monitor = monitor_with_records(1)
        entered = asyncio.Event()

        async def check(snapshot, now) -> None:
            entered.set()
            await asyncio.Event().wait()

        monitor._check_sandbox = check
        task = asyncio.create_task(monitor.tick())
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_confirmed_stopped_container_keeps_state_before_idle_expiry():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    record=SimpleNamespace(agent_id='agent-code',username='alice',sandbox_id='sbx',container_id='cid',status='stopped',last_active_at=datetime.now(timezone.utc).isoformat())
    calls=[]
    backend=SimpleNamespace(_locks={},in_use={},registry=SimpleNamespace(get_sandbox=lambda *args:record),agent_catalog=SimpleNamespace(load=lambda *args:SimpleNamespace(idle_timeout_seconds=3600)),_verify_ownership=lambda *args:calls.append('ownership'))
    async def get(*args):return SimpleNamespace(status='exited')
    async def inspect(*args):raise AssertionError('Confirmed stopped is not a health failure')
    backend._get_container=get;backend.inspect=inspect
    monitor=HealthMonitor(backend,SimpleNamespace(),SimpleNamespace())
    monitor.failures['sbx']=2
    asyncio.run(monitor._check_sandbox(record,None))
    assert calls==['ownership'] and 'sbx' not in monitor.failures and record.status=='stopped'


def test_remote_catalog_load_does_not_block_event_loop():
    import threading
    from datetime import datetime, timezone
    started=threading.Event();release=threading.Event();calls=[]
    record=SimpleNamespace(agent_id='agent-code',username='alice',sandbox_id='sbx',container_id='cid',status='stopped',last_active_at=datetime.now(timezone.utc).isoformat())
    def load(aid):
        calls.append(aid);started.set()
        assert release.wait(2), 'Event loop must schedule while remote catalog waits'
        return SimpleNamespace(idle_timeout_seconds=3600)
    backend=SimpleNamespace(_locks={},in_use={},registry=SimpleNamespace(get_sandbox=lambda *args:record),agent_catalog=SimpleNamespace(load=load),_verify_ownership=lambda *args:None)
    async def get(*args):return SimpleNamespace(status='exited')
    backend._get_container=get
    monitor=HealthMonitor(backend,SimpleNamespace(),SimpleNamespace())
    async def scenario():
        task=asyncio.create_task(monitor._check_sandbox(record,None))
        try:
            assert await asyncio.to_thread(started.wait,1)
            await asyncio.sleep(0)
            assert not task.done()
        finally:release.set()
        await task
    asyncio.run(scenario())
    assert calls==['agent-code']


def test_tick_catalog_snapshot_shared_then_refreshed_next_tick_and_version(tmp_path):
    from pathlib import Path
    from sandbox_manager.registry import Registry
    registry=Registry(tmp_path/'registry.db');registry.initialize()
    paths=[tmp_path/'v1/agent-code',tmp_path/'v2/agent-code']
    for path in paths:path.mkdir(parents=True)
    registry.upsert_agent('agent-code',str(paths[0]),'runtime',True)
    records=[SimpleNamespace(sandbox_id=str(i)) for i in range(8)]
    registry.list_sandboxes=lambda:records
    active=[0];calls=[]
    def load(aid):
        calls.append(active[0]);return SimpleNamespace(path=paths[active[0]],idle_timeout_seconds=10)
    backend=SimpleNamespace(registry=registry,agent_catalog=SimpleNamespace(load=load))
    monitor=HealthMonitor(backend,SimpleNamespace(),SimpleNamespace())
    async def model_health():return True
    monitor.model_health=model_health
    async def check(*args):await monitor._idle_definition('agent-code')
    monitor._check_sandbox=check
    async def scenario():
        await monitor.tick();assert calls==[0]
        await monitor.tick();assert calls==[0,0]
        from sandbox_manager.health import _tick_catalog
        token=_tick_catalog.set({})
        try:
            first=await monitor._idle_definition('agent-code')
            active[0]=1;registry.upsert_agent('agent-code',str(paths[1]),'runtime',True)
            second=await monitor._idle_definition('agent-code')
            assert first.path!=second.path and calls[-2:]==[0,1]
        finally:_tick_catalog.reset(token)
    asyncio.run(scenario())
