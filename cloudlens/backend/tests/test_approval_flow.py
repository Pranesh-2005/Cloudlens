import pytest

pytestmark = pytest.mark.asyncio


async def test_approval_resume_flow_end_to_end(app, client, registered_user):
    from app.llm import FakeLLM, LLMResponse, ToolCall

    calls = {"n": 0}

    def responder(messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return LLMResponse(content="", tool_calls=[ToolCall(id="tc1", name="stop_ec2", args={"instance_id": "i-demo123"})])
        return LLMResponse(content="Instance i-demo123 has been stopped.", tokens=8)

    app.state.llm = FakeLLM(responder)

    chat_resp = await client.post(
        "/api/v1/chat", json={"message": "please stop instance i-demo123"}, headers=registered_user["headers"]
    )
    assert chat_resp.status_code == 200
    assert "approval_required" in chat_resp.text
    assert calls["n"] == 1  # graph paused before executing the EXECUTE-tier tool

    approvals = await client.get("/api/v1/approvals", headers=registered_user["headers"])
    assert approvals.status_code == 200
    pending = approvals.json()
    assert len(pending) == 1
    approval = pending[0]
    assert approval["status"] == "pending"
    assert approval["action"] == "stop_ec2"
    assert approval["params"] == {"instance_id": "i-demo123"}

    decide_resp = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "approve"},
        headers=registered_user["headers"],
    )
    assert decide_resp.status_code == 200
    assert decide_resp.json() == {"ok": True, "status": "approved"}
    assert calls["n"] == 2  # graph resumed and made a second LLM call after the tool ran

    approvals_after = await client.get("/api/v1/approvals", headers=registered_user["headers"])
    assert approvals_after.json()[0]["status"] == "approved"

    # deciding twice is rejected
    redecide = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide", json={"decision": "approve"}, headers=registered_user["headers"]
    )
    assert redecide.status_code == 409


async def test_approval_rejected_skips_tool_execution(app, client, registered_user):
    from app.llm import FakeLLM, LLMResponse, ToolCall

    calls = {"n": 0}

    def responder(messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return LLMResponse(content="", tool_calls=[ToolCall(id="tc1", name="stop_ec2", args={"instance_id": "i-demo999"})])
        # after rejection, the tool message will say it was skipped
        tool_msg = messages[-1]
        assert "skipped" in tool_msg["content"]
        return LLMResponse(content="Understood, I will not stop the instance.")

    app.state.llm = FakeLLM(responder)
    await client.post("/api/v1/chat", json={"message": "stop instance i-demo999"}, headers=registered_user["headers"])
    approval = (await client.get("/api/v1/approvals", headers=registered_user["headers"])).json()[0]

    decide_resp = await client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        json={"decision": "reject", "note": "not authorized right now"},
        headers=registered_user["headers"],
    )
    assert decide_resp.status_code == 200
    assert decide_resp.json()["status"] == "rejected"
