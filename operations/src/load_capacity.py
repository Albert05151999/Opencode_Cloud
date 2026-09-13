import math, time
from .common import fail


def check_capacity(snapshot, agents):
    if not snapshot.get("known") or time.time() - snapshot.get("sampled_at", 0) > 15:
        fail("服务器资源状态未知或已过期，暂不允许启动压测", 503)
    if not snapshot["admission_allowed"]:
        fail("；".join(snapshot["reasons"]), 409)
    cpu = sum(a["cpu_limit"] * a.get("users", 1) for a in agents)
    memory = sum(a["memory_mb"] * a.get("users", 1) for a in agents)
    if (
        cpu > snapshot["remaining_cpu"] + 1e-8
        or memory > snapshot["remaining_memory_mb"]
    ):
        suggestions = []
        grouped = {}
        for a in agents:
            row = grouped.setdefault(a["agent_id"], {**a, "users": 0})
            row["users"] += a.get("users", 1)
        for a in grouped.values():
            # Per-row maximum if other selected rows keep their requested count.
            other_cpu = cpu - a["cpu_limit"] * a.get("users", 1)
            other_memory = memory - a["memory_mb"] * a.get("users", 1)
            maximum = max(
                0,
                min(
                    math.floor(
                        (snapshot["remaining_cpu"] - other_cpu) / a["cpu_limit"]
                    ),
                    math.floor(
                        (snapshot["remaining_memory_mb"] - other_memory)
                        / a["memory_mb"]
                    ),
                ),
            )
            suggestions.append(f"{a['agent_id']} 最多 {maximum} 用户（其他行不变）")
        fail(
            f"压测需要 {cpu:g} 核 / {memory:g} MiB，当前可分配 {snapshot['remaining_cpu']:g} 核 / {snapshot['remaining_memory_mb']:g} MiB。"
            + "；".join(suggestions),
            409,
        )


class LoadCapacity:
    def __init__(self, runtime):
        self.runtime = runtime

    async def snapshot(self, fresh=False):
        return await self.runtime.call("sandbox_manager", "/internal/v1/capacity")
