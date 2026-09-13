"""Bounded module log queries and explicit trace reconstruction."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager, suppress
import heapq
import json
import math
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from shared_libs.service import configure_service, run, settings

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def create_app(config=None):
    config = config or settings("observability")
    root = Path(config["log_root"]).resolve()
    root.mkdir(parents=True, exist_ok=True)

    def prune():
        cutoff = (
            time.time()
            - max(1, int(config.get("settings", {}).get("retention_days", 14))) * 86400
        )
        for path in root.glob("**/events.jsonl.*"):
            if not path.name.rsplit(".", 1)[-1].isdigit() or path.is_symlink():
                continue
            try:
                if (
                    path.resolve().is_relative_to(root)
                    and path.stat().st_mtime < cutoff
                ):
                    path.unlink()
            except FileNotFoundError:
                pass

    @asynccontextmanager
    async def lifespan(app):
        async def retention():
            while True:
                await asyncio.to_thread(prune)
                await asyncio.sleep(3600)

        task = asyncio.create_task(retention())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    application = FastAPI(title="Module observability", lifespan=lifespan)
    application.state.prune = prune
    configure_service(application, "observability", config)

    @application.get("/health/ready")
    def ready():
        return {"ok": root.is_dir()}

    @application.get("/cloud/logs/modules")
    def modules():
        return {
            "items": sorted(
                p.name
                for p in root.iterdir()
                if p.is_dir() and not p.is_symlink() and NAME.fullmatch(p.name)
            )
        }

    def json_safe(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {str(key): json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [json_safe(item) for item in value]
        return value

    def query(module=None, trace_id=None, job_id=None, session_id=None, limit=100):
        if module and not NAME.fullmatch(module):
            raise HTTPException(400, "Invalid module")
        search = root / module if module else root
        if search.is_symlink():
            raise HTTPException(400, "Invalid log path")
        events = []
        # Explicit bounded tail scan; report truncation rather than promise full history.
        candidates=[]
        for path in search.glob("**/events.jsonl*"):
            if path.is_symlink() or not re.fullmatch(r"events\.jsonl(?:\.\d+)?",path.name): continue
            try:
                if path.resolve().is_relative_to(root): candidates.append((path.stat().st_mtime,path))
            except FileNotFoundError: pass
        candidates = [item[1] for item in sorted(candidates, key=lambda item:item[0], reverse=True)]
        max_files = max(1, min(500, int(config.get("settings", {}).get("trace_scan_files", 100))))
        max_bytes = max(1024 * 1024, min(256 * 1024 * 1024, int(config.get("settings", {}).get("trace_scan_bytes", 64 * 1024 * 1024))))
        files = candidates[:max_files]
        scanned = 0
        bytes_scanned = 0
        files_scanned = 0
        matched = 0
        partial = len(candidates) > len(files)
        for path in files:
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                continue
            try:
                with path.open("rb") as stream:
                    stream.seek(0, 2)
                    size = stream.tell()
                    remaining = max_bytes - bytes_scanned
                    if remaining <= 0:
                        partial = True
                        break
                    read_size = min(size, remaining)
                    partial = partial or read_size < size
                    stream.seek(max(0, size - read_size))
                    chunk = stream.read(read_size)
                    bytes_scanned += len(chunk); files_scanned += 1
                    if read_size < size:
                        chunk = chunk.partition(b"\n")[2]
            except FileNotFoundError:
                continue
            for line in chunk.splitlines():
                scanned += 1
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeError):
                    continue
                if not isinstance(event, dict):
                    continue
                event = json_safe(event)
                if trace_id and event.get("trace_id") != trace_id:
                    continue
                if job_id and event.get("job_id") != job_id:
                    continue
                if session_id and event.get("session_id") != session_id:
                    continue
                matched += 1
                item = (str(event.get("timestamp", "")), scanned, event)
                if len(events) < limit:
                    heapq.heappush(events, item)
                elif item[:2] > events[0][:2]:
                    heapq.heapreplace(events, item)
        return {
            "items": [x[2] for x in sorted(events, reverse=True)],
            "next_cursor": None,
            "truncated": matched > limit or partial,
            "scanned": scanned,
            "coverage": {"partial": partial, "files_considered": len(candidates),
                "files_scanned": files_scanned, "bytes_scanned": bytes_scanned,
                "max_files": max_files, "max_bytes": max_bytes,
                "retention_days": max(1, int(config.get("settings", {}).get("retention_days", 14)))},
        }

    def instant(value):
        if not isinstance(value, str): return None
        try: return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except (OverflowError, ValueError): return None

    def duration_value(event):
        value = event.get("duration_ms")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None

    def aggregate(events):
        grouped = {}
        for event in events:
            sid = event.get("span_id")
            if not isinstance(sid, str): continue
            grouped.setdefault(sid, []).append(event)
        spans = []
        intervals = {}
        for sid, members in grouped.items():
            dated = [(instant(e.get("timestamp")), e) for e in members]
            dated = [(d,e) for d,e in dated if d is not None]
            end = max((d for d,_ in dated), default=None)
            starts = []
            for date, event in dated:
                duration_ms = duration_value(event)
                if duration_ms is None:
                    continue
                try:
                    starts.append(date - timedelta(milliseconds=duration_ms))
                except OverflowError:
                    continue
            start = min(starts, default=None)
            duration = (end-start).total_seconds()*1000 if start and end else None
            latest = max(dated, default=(None, members[-1]), key=lambda item: item[0] or datetime.min.replace(tzinfo=timezone.utc))[1]
            module = next((e.get("module") for e in reversed(members) if e.get("module")), None)
            status = next((e.get("status_code") for e in reversed(members) if e.get("status_code") is not None), None)
            error = next((e.get("error_code") for e in reversed(members) if e.get("error_code")), None)
            failed = (
                bool(error)
                or isinstance(status, (int, float))
                and not isinstance(status, bool)
                and status >= 400
                or any(str(e.get("level", "")).upper() in {"ERROR", "CRITICAL"} for e in members)
            )
            span = {"span_id": sid, "parent_span_id": latest.get("parent_span_id"), "module": module,
                "name": latest.get("stage") or latest.get("action"),
                "start_time": start.isoformat() if start else None, "end_time": end.isoformat() if end else None,
                "duration_ms": round(duration,3) if duration is not None else None, "status_code": status,
                "status":"error" if failed else "ok" if status is not None else "unknown", "error_code": error,
                "event_count": len(members), "events": sorted(members,key=lambda e:str(e.get("timestamp",""))), "children": []}
            spans.append(span)
            if module and start and end: intervals.setdefault(module, []).append((start,end))
        by_id = {s["span_id"]:s for s in spans}
        roots=[]
        for span in spans:
            parent=by_id.get(span["parent_span_id"])
            span["external_parent"] = bool(span["parent_span_id"] and not parent)
            ancestor = parent
            cycle = False
            visited = {span["span_id"]}
            while ancestor:
                if ancestor["span_id"] in visited:
                    cycle = True
                    break
                visited.add(ancestor["span_id"])
                ancestor = by_id.get(ancestor["parent_span_id"])
            span["cycle_broken"] = cycle
            if parent and not cycle: parent["children"].append(span["span_id"])
            else: roots.append(span["span_id"])
        module_ms={}
        for module, ranges in intervals.items():
            total=0.0; current=None
            for start,end in sorted(ranges):
                if current is None or start>current[1]:
                    if current: total+=(current[1]-current[0]).total_seconds()*1000
                    current=[start,end]
                elif end>current[1]: current[1]=end
            if current: total+=(current[1]-current[0]).total_seconds()*1000
            module_ms[module]=round(total,3)
        spans.sort(key=lambda s:s["start_time"] or "")
        origin=min((instant(s["start_time"]) or instant(s["end_time"]) for s in spans
            if s["start_time"] or s["end_time"]),default=None)
        for span in spans:
            point=instant(span["start_time"]) or instant(span["end_time"])
            span["offset_ms"]=round((point-origin).total_seconds()*1000,3) if point and origin else None
        return spans, roots, module_ms

    @application.get("/cloud/logs")
    def logs(
        module: str | None = None,
        trace_id: str | None = None,
        job_id: str | None = None,
        limit: int = Query(100, ge=1, le=1000),
    ):
        return query(module=module, trace_id=trace_id, job_id=job_id, limit=limit)

    @application.get("/cloud/traces")
    def traces(
        trace_id: str | None = None,
        session_id: str | None = None,
        exclude_health: bool = True,
        limit: int = Query(50, ge=1, le=200),
    ):
        if trace_id is not None and not re.fullmatch(r"[0-9a-f]{32}", trace_id):
            raise HTTPException(400, "Invalid trace ID")
        if session_id is not None and not NAME.fullmatch(session_id): raise HTTPException(400, "Invalid session ID")
        result=query(trace_id=trace_id, limit=1000)
        grouped={}
        for event in result["items"]:
            tid=event.get("trace_id")
            if isinstance(tid,str) and re.fullmatch(r"[0-9a-f]{32}",tid): grouped.setdefault(tid,[]).append(event)
        items=[]
        for tid, events in grouped.items():
            ordered=sorted(events,key=lambda e:e.get("timestamp", "")); spans,_,module_ms=aggregate(ordered)
            modules = sorted({span["module"] for span in spans if span["module"]})
            if session_id and not any(e.get("session_id")==session_id for e in ordered): continue
            entry = next(
                (event for event in ordered
                 if event.get("module") == "api_gateway" and event.get("action") == "http_request"),
                None,
            )
            if entry is None:
                entry = next((event for event in ordered if event.get("action") == "http_request"), ordered[0])
            path = entry.get("path")
            noise_path = isinstance(path, str) and (
                path == "/metrics"
                or path.startswith("/health/")
                or path.startswith("/cloud/health/")
                or path == "/cloud/logs"
                or path.startswith("/cloud/logs/")
                or path == "/cloud/traces"
                or path.startswith("/cloud/traces/")
            )
            has_business_event = any(
                event.get("message_id")
                or event.get("action") in {"model_dispatch", "tool_call", "tool_result"}
                for event in ordered
            )
            if exclude_health and noise_path and not has_business_event:
                continue
            entry_duration = duration_value(entry)
            items.append({"trace_id":tid,"started_at":ordered[0].get("timestamp"),"ended_at":ordered[-1].get("timestamp"),
                "session_id":next((e.get("session_id") for e in reversed(ordered) if e.get("session_id")),None),
                "message_id":next((e.get("message_id") for e in reversed(ordered) if e.get("message_id")),None),
                "method":entry.get("method"),"path":path,
                "operation":entry.get("action") or entry.get("stage"),
                "duration_ms":round(entry_duration,3) if entry_duration is not None else None,
                "span_count":len(spans),"event_count":len(ordered),"modules":modules,
                "status_code":next((e.get("status_code") for e in reversed(ordered) if e.get("status_code") is not None),None),
                "error":any(span["status"] == "error" for span in spans)})
        items.sort(key=lambda item:item["ended_at"] or "",reverse=True)
        return {"items":items[:limit],"next_cursor":None,"truncated":result["truncated"] or len(items)>limit,
            "partial":result["coverage"]["partial"],"coverage":result["coverage"]}

    @application.get("/cloud/traces/{trace_id}")
    def trace(trace_id: str):
        if not re.fullmatch(r"[0-9a-f]{32}", trace_id):
            raise HTTPException(400, "Invalid trace ID")
        result = query(trace_id=trace_id, limit=1000)
        events = sorted(result["items"], key=lambda e: e.get("timestamp", ""))
        spans, roots, module_ms = aggregate(events)
        modules = sorted({span["module"] for span in spans if span["module"]})
        known_starts = [instant(span["start_time"]) for span in spans if span["start_time"]]
        known_ends = [instant(span["end_time"]) for span in spans if span["end_time"]]
        trace_duration = (
            (max(known_ends) - min(known_starts)).total_seconds() * 1000
            if known_starts and known_ends
            else None
        )
        return {
            "trace_id": trace_id,
            "spans": spans,
            "events": events,
            "truncated": result["truncated"],
            "partial": result["coverage"]["partial"],
            "coverage": result["coverage"],
            "span_tree": {"roots": roots, "children_are_span_ids": True},
            "summary": {"span_count": len(spans), "event_count": len(events),
                "modules": modules, "module_duration_ms": module_ms,
                "started_at": events[0].get("timestamp") if events else None,
                "ended_at": events[-1].get("timestamp") if events else None,
                "duration_ms": round(trace_duration, 3) if trace_duration is not None else None,
                "root_span_count": len(roots),
                "external_parent_count": sum(span["external_parent"] for span in spans),
                "error_span_count": sum(span["status"] == "error" for span in spans),
                "completeness":"partial_scanned_retention" if result["coverage"]["partial"] else "scanned_retention_window_only"},
        }

    return application


app = create_app()
if __name__ == "__main__":
    run("observability")
