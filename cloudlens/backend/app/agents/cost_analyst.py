"""cost_analyst: Cost Explorer queries, spend breakdown. READ-tier only."""
from __future__ import annotations

from functools import partial

from app.agents.graph import build_tool_agent, tool_schema
from app.aws import tools as aws_tools
from app.llm import LLMClient

NAME = "cost_analyst"
SYSTEM_PROMPT = (
    "You are CloudLens's cost analyst agent. You answer questions about AWS spend using "
    "the tools available - never invent numbers. Call a tool for any factual cost question, "
    "then summarize the result concisely for the user."
)

TOOL_FUNCS = {
    "get_cost_summary": aws_tools.get_cost_summary,
    "get_cost_by_service": aws_tools.get_cost_by_service,
    "get_cost_by_tag": aws_tools.get_cost_by_tag,
}

SCHEMAS = [
    tool_schema("get_cost_summary", "Total spend + by-service + daily series for trailing N days.",
                {"days": {"type": "integer", "description": "lookback window, default 30"}}),
    tool_schema("get_cost_by_service", "Spend broken down by AWS service.",
                {"days": {"type": "integer"}}),
    tool_schema("get_cost_by_tag", "Spend broken down by a cost-allocation tag.",
                {"tag_key": {"type": "string"}, "days": {"type": "integer"}}),
]


def build(ctx, llm: LLMClient):
    bound = {n: partial(fn, ctx) for n, fn in TOOL_FUNCS.items()}
    return build_tool_agent(NAME, bound, SCHEMAS, SYSTEM_PROMPT, llm)


def card() -> dict:
    return {
        "name": NAME,
        "description": "Answers AWS cost/spend questions via Cost Explorer.",
        "tier": "READ",
        "skills": [{"name": n, "description": s["description"]} for n, s in zip(TOOL_FUNCS, SCHEMAS)],
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
    }
