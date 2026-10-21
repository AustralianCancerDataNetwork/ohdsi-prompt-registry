"""Headless Codex app-server evaluation client; not a product UI or session store."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any


class CodexClient:
    def __init__(self, command: list[str], cwd: Path, trace_dir: Path) -> None:
        self.command = command
        self.cwd = cwd
        self.trace_dir = trace_dir
        self.pending: dict[int, asyncio.Future] = {}
        self.next_id = 0
        self.models: dict[str, str] = {}
        self.events: list[dict[str, Any]] = []
        self.native_answer: str | None = None
        self.completed: asyncio.Future | None = None
        self.native_requests: list[dict[str, Any]] = []

    async def start(self) -> None:
        self.stderr = (self.trace_dir / "app-server.stderr").open("w")
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=self.cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=self.stderr,
        )
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("Codex app-server did not expose stdio pipes")
        self.input = self.process.stdin
        self.output = self.process.stdout
        self.reader = asyncio.create_task(self._read())
        self.initialize = await self.request(
            "initialize",
            {
                "clientInfo": {"name": "groundworkers_m4", "version": "1.0"},
                "capabilities": {"experimentalApi": True},
            },
        )
        await self.send({"method": "initialized", "params": {}})

    async def send(self, message: dict[str, Any]) -> None:
        self.input.write((json.dumps(message) + "\n").encode())
        await self.input.drain()

    async def request(self, method: str, params: dict[str, Any]) -> Any:
        self.next_id += 1
        identity = self.next_id
        future = asyncio.get_running_loop().create_future()
        self.pending[identity] = future
        await self.send({"id": identity, "method": method, "params": params})
        return await asyncio.wait_for(future, 120)

    def _response(self, message: dict[str, Any]) -> None:
        future = self.pending.pop(message.get("id"), None)
        if future is None or future.done():
            return
        if "error" in message:
            future.set_exception(RuntimeError(json.dumps(message["error"])))
        else:
            future.set_result(message.get("result"))

    async def _server_request(self, message: dict[str, Any]) -> None:
        if message["method"] == "item/tool/requestUserInput":
            self.native_requests.append(message)
            answers = {
                question["id"]: {"answers": [self.native_answer]}
                for question in message["params"]["questions"]
                if self.native_answer is not None
            }
            await self.send({"id": message["id"], "result": {"answers": answers}})
            return
        # Unexpected approvals and host requests are never automatically accepted.
        await self.send(
            {
                "id": message["id"],
                "error": {
                    "code": -32601,
                    "message": "Unsupported evaluation client request",
                },
            }
        )

    async def _read(self) -> None:
        while line := await self.output.readline():
            message = json.loads(line)
            if "method" not in message:
                self._response(message)
                continue
            method = message["method"]
            if method.startswith(("thread/", "turn/", "item/", "error")):
                self.events.append(message)
            if "id" in message:
                await self._server_request(message)
            if (
                method == "turn/completed"
                and self.completed is not None
                and not self.completed.done()
            ):
                self.completed.set_result(message["params"])
        error = RuntimeError("Codex app-server closed its output")
        waiting = list(self.pending.values())
        if self.completed is not None:
            waiting.append(self.completed)
        for future in waiting:
            if not future.done():
                future.set_exception(error)

    async def thread(self, model: str) -> str:
        started = await self.request(
            "thread/start",
            {
                "cwd": str(self.cwd),
                "model": model,
                "ephemeral": True,
                "sandbox": "read-only",
                "approvalPolicy": "never",
                "multiAgentMode": "explicitRequestOnly",
            },
        )
        identity = started["thread"]["id"]
        self.models[identity] = model
        return identity

    async def turn(
        self,
        thread: str,
        text: str,
        mode: str,
        native_answer: str | None = None,
    ) -> dict[str, Any]:
        model = self.models[thread]
        self.events = []
        self.native_requests = []
        self.native_answer = native_answer
        self.completed = asyncio.get_running_loop().create_future()
        started = time.monotonic()
        await self.request(
            "turn/start",
            {
                "threadId": thread,
                "input": [{"type": "text", "text": text}],
                "model": model,
                "effort": "low",
                "collaborationMode": {
                    "mode": mode,
                    "settings": {"model": model, "reasoning_effort": "low"},
                },
            },
        )
        completed = await asyncio.wait_for(self.completed, 240)
        messages = [
            event["params"]["item"]
            for event in self.events
            if event["method"] == "item/completed"
        ]
        return {
            "elapsed_seconds": time.monotonic() - started,
            "completion": completed,
            "items": messages,
            "events": self.events,
            "native_requests": self.native_requests,
        }

    async def close(self) -> None:
        self.input.close()
        try:
            await asyncio.wait_for(self.process.wait(), 15)
        except TimeoutError:
            self.process.terminate()
            await self.process.wait()
        self.reader.cancel()
        self.stderr.close()
