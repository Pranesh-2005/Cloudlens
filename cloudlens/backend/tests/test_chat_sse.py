import json

import pytest

pytestmark = pytest.mark.asyncio


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


async def test_chat_sse_happy_path(app, client, registered_user):
    from app.llm import FakeLLM, LLMResponse, ToolCall

    calls = {"n": 0}

    def responder(messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return LLMResponse(content="", tool_calls=[ToolCall(id="tc1", name="get_cost_summary", args={"days": 30})])
        return LLMResponse(content="Your trailing 30-day AWS spend looks stable.", tokens=12)

    app.state.llm = FakeLLM(responder)

    resp = await client.post(
        "/api/v1/chat", json={"message": "what is my cost this month?"}, headers=registered_user["headers"]
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]

    assert types[0] == "agent_started"
    assert "tool_called" in types
    assert "tool_result" in types
    assert "message_delta" in types
    assert types[-1] == "done"

    done_event = events[-1]
    assert done_event["thread_id"]
    assert "tokens" in done_event["usage"]

    message_event = next(e for e in events if e["type"] == "message_delta")
    assert "stable" in message_event["content"]


async def test_threads_listed_after_chat(app, client, registered_user):
    from app.llm import FakeLLM

    app.state.llm = FakeLLM()  # default responder: no tool calls, immediate final answer
    resp = await client.post("/api/v1/chat", json={"message": "hello there"}, headers=registered_user["headers"])
    assert resp.status_code == 200

    threads = await client.get("/api/v1/threads", headers=registered_user["headers"])
    assert threads.status_code == 200
    assert len(threads.json()) == 1
    assert threads.json()[0]["title"].startswith("hello there")
