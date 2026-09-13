import asyncio
import threading

from sandbox_manager.native_router import SessionRecorder


def test_concurrent_routes_wait_for_commit_and_cancellation_does_not_drop_others():
    entered, commit = threading.Event(), threading.Event()

    class Registry:
        batches = []

        def record_sessions_batch(self, entries):
            self.batches.append(entries)
            entered.set()
            assert commit.wait(5)
            return [entry[0] for entry in entries]

    async def scenario():
        registry = Registry()
        recorder = SessionRecorder(registry)
        tasks = [asyncio.create_task(recorder.record(index)) for index in range(8)]
        assert await asyncio.to_thread(entered.wait, 5)
        assert not any(task.done() for task in tasks)
        tasks[0].cancel()
        commit.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert isinstance(results[0], asyncio.CancelledError)
        assert results[1:] == list(range(1, 8))
        await recorder.worker
        assert len(registry.batches) == 1
        assert not recorder.pending

    asyncio.run(scenario())


def test_commit_failure_reaches_every_waiter_and_next_batch_can_recover():
    class Registry:
        broken = True

        def record_sessions_batch(self, entries):
            if self.broken:
                raise OSError('commit failed')
            return [entry[0] for entry in entries]

    async def scenario():
        registry = Registry()
        recorder = SessionRecorder(registry)
        results = await asyncio.gather(*(recorder.record(i) for i in range(8)), return_exceptions=True)
        assert all(isinstance(result, OSError) for result in results)
        registry.broken = False
        assert await recorder.record('recovered') == 'recovered'

    asyncio.run(scenario())
