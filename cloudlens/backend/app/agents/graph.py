"""Shared LangGraph ReAct-style tool-agent builder used by all 5 specialists.

One node calls the LLM with the agent's tool subset; if the LLM asks for a tool,
the tools node runs it - unless it's an EXECUTE-tier tool, in which case it calls
LangGraph's interrupt() to pause the graph and hand control back to a human via
the approval API (see routers/approvals.py + a2a/server.py). This is the single
choke point guardrail #1 (EXECUTE tools never run directly) routes through, so
every specialist gets it for free.
"""
from __future__ import annotations

import json
from typing import Any, Callable, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from app.guardrails import EXECUTE, MAX_ITERATIONS, TOOL_TIERS
from app.llm import LLMClient, ToolCall

ToolFn = Callable[..., Any]  # async, already bound to a ToolContext via functools.partial


class AgentState(TypedDict):
    messages: list[dict]
    iterations: int
    final_answer: str
    tool_trace: list[dict]  # [{tool, args, status}] for the SSE/audit trail


def build_tool_agent(
    name: str,
    tools: dict[str, ToolFn],
    schemas: list[dict[str, Any]],
    system_prompt: str,
    llm: LLMClient,
):
    async def agent_node(state: AgentState) -> AgentState:
        messages = [{"role": "system", "content": system_prompt}, *state["messages"]]
        response = await llm.acomplete(messages, tools=schemas)
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content}
        if response.tool_calls:
            assistant_msg["tool_calls"] = [
                {"id": tc.id, "name": tc.name, "args": tc.args} for tc in response.tool_calls
            ]
        new_messages = state["messages"] + [assistant_msg]
        final = response.content if not response.tool_calls else state.get("final_answer", "")
        return {**state, "messages": new_messages, "final_answer": final}

    async def tools_node(state: AgentState) -> AgentState:
        last = state["messages"][-1]
        calls: list[dict] = last.get("tool_calls", [])
        tool_messages: list[dict] = []
        trace = list(state.get("tool_trace", []))

        for call in calls:
            tool_name = call["name"]
            args = call.get("args", {})
            tier = TOOL_TIERS.get(tool_name, "READ")

            if tier == EXECUTE:
                decision = interrupt(
                    {
                        "agent": name,
                        "tool": tool_name,
                        "args": args,
                        "reason": f"{name} requested EXECUTE-tier action '{tool_name}'",
                    }
                )
                approved = isinstance(decision, dict) and decision.get("decision") == "approve"
                if not approved:
                    result = {"skipped": True, "reason": "rejected by approver"}
                    status = "rejected"
                else:
                    fn = tools[tool_name]
                    try:
                        result = await fn(**args)
                        status = "ok"
                    except Exception as exc:  # noqa: BLE001
                        result = {"error": str(exc)}
                        status = "error"
            else:
                fn = tools[tool_name]
                try:
                    result = await fn(**args)
                    status = "ok"
                except Exception as exc:  # noqa: BLE001
                    result = {"error": str(exc)}
                    status = "error"

            trace.append({"tool": tool_name, "args": args, "status": status})
            tool_messages.append(
                {"role": "tool", "tool_call_id": call["id"], "name": tool_name, "content": json.dumps(result, default=str)}
            )

        return {
            **state,
            "messages": state["messages"] + tool_messages,
            "iterations": state["iterations"] + 1,
            "tool_trace": trace,
        }

    def route_after_agent(state: AgentState) -> str:
        last = state["messages"][-1]
        if last.get("tool_calls"):
            return "tools"
        return END

    def route_after_tools(state: AgentState) -> str:
        if state["iterations"] >= MAX_ITERATIONS:
            return END
        return "agent"

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    graph.add_conditional_edges("tools", route_after_tools, {"agent": "agent", END: END})
    return graph


def tool_schema(name: str, description: str, properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties or {},
            "required": required or [],
        },
    }


def initial_state(user_message: str) -> AgentState:
    return {"messages": [{"role": "user", "content": user_message}], "iterations": 0, "final_answer": "", "tool_trace": []}


def _registry() -> dict[str, Any]:
    """Wires all 5 specialist agent modules together. Imported lazily to dodge a circular
    import (each specialist imports build_tool_agent/tool_schema from this module)."""
    from app.agents import cost_analyst, deploy_operator, forecaster, resource_monitor, security_auditor

    return {
        cost_analyst.NAME: cost_analyst,
        forecaster.NAME: forecaster,
        resource_monitor.NAME: resource_monitor,
        security_auditor.NAME: security_auditor,
        deploy_operator.NAME: deploy_operator,
    }


AGENT_NAMES = ["cost_analyst", "forecaster", "resource_monitor", "security_auditor", "deploy_operator"]


def get_agent_module(name: str):
    return _registry()[name]


def all_agent_cards() -> list[dict]:
    return [mod.card() for mod in _registry().values()]
