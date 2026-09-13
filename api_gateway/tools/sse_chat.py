#!/usr/bin/env python3
"""Terminal SSE client: pip install httpx; set --base-url to the server API."""

import argparse
import asyncio
import json
import sys
import uuid
import os
from pathlib import Path

import httpx


# IDE 直接点击 Run：修改这里即可，无需设置命令行参数。
# 已验证的服务器 API；其他服务器可通过 --base-url 指定地址。
BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:18080")
AGENT = "agent-code"
USERNAME = "local-demo"
MODEL = "coding-fast"  # MiniMax M3；改为 coding-quality 使用 GLM。
PROMPT = "请实际执行 pwd，并用 Python 计算 sum(range(1,101))，然后用中文说明结果。"
TIMEOUT_SECONDS = 600
RAW_EVENTS = False  # True：打印原始 SSE JSON；False：显示回答和工具状态。


async def events(response):
    data = []
    size = 0
    async for line in response.aiter_lines():
        if line == "":
            if data:
                yield json.loads("\n".join(data))
            data, size = [], 0
        elif line.startswith("data:"):
            value = line[5:]
            if value.startswith(" "):
                value = value[1:]
            size += len(value)
            if size > 1024 * 1024:
                raise ValueError("SSE frame exceeds 1 MiB")
            data.append(value)


class Display:
    def __init__(self, session, raw=False):
        self.session, self.raw = session, raw
        self.assistants = set()
        self.texts = {}
        self.tools = {}
        self.busy = False

    def accept(self, event):
        props = event.get("properties", {})
        info = props.get("info", {})
        part = props.get("part", {})
        sid = props.get("sessionID") or info.get("sessionID") or part.get("sessionID")
        if sid != self.session:
            return False
        kind = event.get("type")
        if self.raw:
            print(json.dumps(event, ensure_ascii=False), flush=True)
        if kind == "session.error":
            raise RuntimeError(
                "Session error: " + json.dumps(props.get("error"), ensure_ascii=False)
            )
        if kind == "message.updated" and info.get("role") == "assistant":
            self.assistants.add(info["id"])
            if info.get("error"):
                raise RuntimeError(
                    "Model error: " + json.dumps(info["error"], ensure_ascii=False)
                )
        if kind == "session.status":
            status = props.get("status", {}).get("type")
            if status in {"busy", "retry"}:
                self.busy = True
            if status == "idle" and self.busy:
                return True
        if kind == "session.idle" and self.busy:
            return True
        if (
            kind == "message.part.delta"
            and props.get("messageID") in self.assistants
            and props.get("field") == "text"
        ):
            key = props["partID"]
            delta = props.get("delta", "")
            self.texts[key] = self.texts.get(key, "") + delta
            if not self.raw:
                print(delta, end="", flush=True)
        if kind == "message.part.updated" and part.get("messageID") in self.assistants:
            key = part["id"]
            if part.get("type") == "text":
                text = part.get("text", "")
                old = self.texts.get(key, "")
                if text.startswith(old):
                    if not self.raw:
                        print(text[len(old) :], end="", flush=True)
                    self.texts[key] = text
            if part.get("type") == "tool":
                status = part.get("state", {}).get("status")
                if self.tools.get(key) != status:
                    self.tools[key] = status
                    if not self.raw:
                        print(f"\n[tool: {part.get('tool')} / {status}]", flush=True)
        return False


async def chat(args):
    headers = {"X-Cloud-Agent-ID": args.agent, "X-Cloud-Username": args.username}
    token = os.environ.get("CLOUD_AGENT_ADMIN_TOKEN", "")
    if getattr(args, "token_file", None):
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
    if not token:
        try:
            import keyring

            token = (
                keyring.get_password("opencode-cloud-web", args.base_url.rstrip("/"))
                or ""
            )
        except Exception:
            pass
    auth_headers = {"Authorization": "Bearer " + token} if token else {}
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        trust_env=False,
        headers=auth_headers,
        timeout=httpx.Timeout(60, connect=10),
    ) as client:
        created = await client.post(
            "/session",
            json={"_cloud": {"agent_id": args.agent, "username": args.username}},
        )
        created.raise_for_status()
        session = created.json()["id"]
        print(f"Session: {session} (preserved on server)", file=sys.stderr)
        submitted = False
        completed = False
        try:
            async with asyncio.timeout(args.timeout):
                async with client.stream(
                    "GET",
                    "/event",
                    headers={**headers, "Accept": "text/event-stream"},
                    timeout=httpx.Timeout(None, connect=10),
                ) as stream:
                    stream.raise_for_status()
                    if not stream.headers.get("content-type", "").startswith(
                        "text/event-stream"
                    ):
                        raise RuntimeError("Expected SSE content type")
                    iterator = events(stream)
                    # OpenCode sends server.connected after the subscription is established.
                    while True:
                        initial = await asyncio.wait_for(anext(iterator), 15)
                        if initial.get("type") == "server.connected":
                            break
                    display = Display(session, args.raw)
                    submitted = True
                    response = await client.post(
                        f"/session/{session}/prompt_async",
                        json={
                            "messageID": "msg_" + uuid.uuid4().hex,
                            "model": {
                                "providerID": "cloud-model-gateway",
                                "modelID": args.model,
                            },
                            "parts": [{"type": "text", "text": args.prompt}],
                        },
                    )
                    response.raise_for_status()
                    print("Streaming...", file=sys.stderr)
                    async for event in iterator:
                        if display.accept(event):
                            completed = True
                            print("\n[done]", file=sys.stderr)
                            return
                    raise RuntimeError(
                        "SSE disconnected before completion; request is not resent automatically"
                    )
        finally:
            if submitted and not completed:
                # Abort only the new session created by this invocation.
                try:
                    response = await client.post(
                        f"/session/{session}/abort", timeout=10
                    )
                    response.raise_for_status()
                    print("\nAbort requested for this session.", file=sys.stderr)
                except Exception:
                    print(
                        f"Abort unconfirmed; check session {session} on the server.",
                        file=sys.stderr,
                    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument(
        "--token-file",
        help="Administrator token file; alternatively use CLOUD_AGENT_ADMIN_TOKEN or the Web credential vault",
    )
    parser.add_argument("--agent", default=AGENT)
    parser.add_argument("--username", default=USERNAME)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--prompt", default=PROMPT)
    parser.add_argument("--timeout", type=float, default=TIMEOUT_SECONDS)
    parser.add_argument(
        "--raw",
        action="store_true",
        default=RAW_EVENTS,
        help="Print original session SSE JSON instead of text",
    )
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        asyncio.run(chat(args))
    except httpx.ConnectError:
        print(
            f"无法连接 {args.base_url}。请检查服务器地址、API 监听端口及网络访问规则。",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
