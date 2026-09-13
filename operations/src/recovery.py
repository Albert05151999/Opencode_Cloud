"""Bounded recovery policy consumes sandbox observations and creates durable jobs."""

import asyncio
import time
from pydantic import BaseModel, ConfigDict, Field, field_validator
from fastapi import HTTPException


class RecoveryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    failure_threshold: int = Field(3, ge=1, le=20)
    max_attempts: int = Field(3, ge=1, le=10)
    window_seconds: int = Field(900, ge=60, le=86400)
    backoff_seconds: list[int] = Field(
        default_factory=lambda: [30, 60, 120], min_length=1, max_length=10
    )
    stable_seconds: int = Field(300, ge=30, le=3600)
    agent_enabled: dict[str, bool] = Field(default_factory=dict)
    max_parallel_recoveries: int = Field(2, ge=1, le=2)

    @field_validator("backoff_seconds")
    @classmethod
    def backoff(cls, values):
        if any(v < 1 or v > 3600 for v in values):
            raise ValueError("Recovery backoff must be 1–3600 seconds")
        return values


class Recovery:
    def __init__(self, runtime):
        self.runtime = runtime
        self.store = runtime.store

    def policy(self):
        return RecoveryPolicy.model_validate(self.store.state("recovery-policy") or {})

    def state(self, sid):
        return self.store.state("recovery:" + sid) or {}

    def update(self, sid, **changes):
        value = self.state(sid)
        value.update(changes)
        self.store.state("recovery:" + sid, value)
        return value

    async def tick(self):
        policy = self.policy()
        if not policy.enabled:
            return
        records = []
        while True:
            result = await self.runtime.call(
                "sandbox_manager",
                "/internal/v1/sandboxes?limit=200&offset=" + str(len(records)),
            )
            items = (
                result
                if isinstance(result, list)
                else result.get("items", result.get("sandboxes", []))
            )
            records.extend(items)
            if (
                isinstance(result, list)
                or not items
                or len(records) >= result.get("total", len(records))
            ):
                break
        catalog = await self.runtime.call(
            "catalog_service", "/internal/v1/load-test-catalog"
        )
        active = [
            j
            for j in self.store.jobs()
            if j["kind"] == "sandbox.recover"
            and j["status"] in {"queued", "running", "waiting", "applying"}
        ]
        for record in records:
            aid, sid = record["agent_id"], record["sandbox_id"]
            if (
                record.get("username", "").startswith("loadtest-")
                or not record.get("container_id")
                or not policy.agent_enabled.get(aid, True)
            ):
                continue
            if catalog["agents"].get(aid, {}).get("lifecycle") in {
                "archived",
                "deleting",
            }:
                continue
            if self.store.state("desired:" + sid) == {"state": "stopped"}:
                continue
            if any(
                j.get("scope", j["target"]) in {aid, "*"}
                and j["status"]
                in {"queued", "running", "waiting", "applying", "needs_recovery"}
                for j in self.store.jobs()
            ):
                continue
            detail = await self.runtime.call(
                "sandbox_manager", "/internal/v1/sandboxes/" + sid
            )
            state, now = self.state(sid), time.time()
            if record["status"] == "ready":
                since = state.get("healthy_since") or now
                changes = {
                    "failures": 0,
                    "healthy_since": since,
                    "reason": None,
                    "execution": detail.get("execution", "unknown"),
                    "container_id": record["container_id"],
                    "activity_generation": detail.get("activity_generation"),
                }
                if now - since >= policy.stable_seconds:
                    changes.update(attempts=[], next_attempt=0)
                self.update(sid, **changes)
                continue
            if record["status"] not in {"unhealthy", "missing"}:
                continue
            failures = state.get("failures", 0) + 1
            self.update(sid, failures=failures, healthy_since=None)
            if failures < policy.failure_threshold or now < state.get(
                "next_attempt", 0
            ):
                continue
            attempts = [
                t for t in state.get("attempts", []) if now - t < policy.window_seconds
            ]
            if len(attempts) >= policy.max_attempts:
                self.update(
                    sid, reason="Recovery limit reached; manual intervention required"
                )
                continue
            idle = detail.get("execution") == "idle"
            if not idle:
                idle = (
                    state.get("execution") == "idle"
                    and state.get("container_id") == record["container_id"]
                    and state.get("activity_generation") is not None
                    and state["activity_generation"]
                    == detail.get("activity_generation")
                )
            if not idle:
                self.update(
                    sid,
                    reason="Execution is busy or unknown; automatic restart skipped",
                )
                continue
            if len(active) >= policy.max_parallel_recoveries:
                break
            try:
                job, created = self.store.submit(
                    "sandbox.recover",
                    sid,
                    {
                        "request_id": "recovery-" + str(time.time_ns()),
                        "expected_container_id": record["container_id"],
                        "expected_activity_generation": detail.get(
                            "activity_generation"
                        ),
                    },
                    scope=aid,
                )
            except HTTPException:
                continue
            if created:
                self.update(
                    sid,
                    attempts=attempts + [now],
                    next_attempt=now
                    + policy.backoff_seconds[
                        min(len(attempts), len(policy.backoff_seconds) - 1)
                    ],
                    reason="Recovery queued",
                )
                active.append(job)
                self.runtime.spawn(job["id"])

    async def loop(self):
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(10)
