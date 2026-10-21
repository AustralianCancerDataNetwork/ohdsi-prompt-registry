"""Transport safety checks with a local scripted peer; these do not call a model."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest
from evaluation.codex_client import CodexClient

PEER = """import json,sys
kind=sys.argv[1]
def send(value):
    print(json.dumps(value),flush=True)
for line in sys.stdin:
    message=json.loads(line)
    method=message.get("method")
    if method=="initialize":
        send({"id":message["id"],"result":{"userAgent":"scripted-peer"}})
    elif method=="thread/start":
        send({"id":message["id"],"result":{"thread":{"id":"synthetic-thread"}}})
    elif method=="turn/start":
        send({"id":message["id"],"result":{}})
        request="item/tool/requestUserInput" if kind!="unexpected" else "item/commandExecution/requestApproval"
        send({"id":"server-question","method":request,"params":{"questions":[{"id":"period","header":"Period","question":"Which period?"}]}})
    elif message.get("id")=="server-question":
        send({"method":"item/completed","params":{"item":{"type":"agentMessage","text":json.dumps(message)}}})
        send({"method":"turn/completed","params":{"turn":{"status":"completed"}}})
"""


@pytest.mark.parametrize("kind", ["answer", "empty", "unexpected"])
def test_native_transport_correlates_scripted_answers_and_rejects_approvals(
    tmp_path, kind
):
    peer = tmp_path / "peer.py"
    peer.write_text(PEER)

    async def exercise():
        client = CodexClient([sys.executable, str(peer), kind], tmp_path, tmp_path)
        try:
            await client.start()
            thread = await client.thread("synthetic-model-not-called")
            result = await client.turn(
                thread,
                "Synthetic test",
                "default",
                "365 days" if kind == "answer" else None,
            )
            reply = json.loads(result["items"][0]["text"])
            assert reply["id"] == "server-question"
            if kind == "unexpected":
                assert "result" not in reply
                assert reply["error"]["code"] == -32601
                assert result["native_requests"] == []
            else:
                expected = (
                    {"period": {"answers": ["365 days"]}} if kind == "answer" else {}
                )
                assert reply["result"]["answers"] == expected
                assert len(result["native_requests"]) == 1
        finally:
            await client.close()

    asyncio.run(exercise())
