from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.health import HealthMonitor


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
