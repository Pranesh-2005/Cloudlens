"""security_auditor: IAM audit, public S3, open security groups. READ-tier only."""
from __future__ import annotations

from functools import partial

from app.agents.graph import build_tool_agent, tool_schema
from app.aws import tools as aws_tools
from app.llm import LLMClient

NAME = "security_auditor"
SYSTEM_PROMPT = (
    "You are CloudLens's security auditor agent. You find misconfigurations - overly-broad "
    "IAM policies, public S3 buckets, open security groups - using the tools available. "
    "Never invent findings; report only what the tools return, with severity."
)

TOOL_FUNCS = {
    "audit_iam_users": aws_tools.audit_iam_users,
    "find_public_buckets": aws_tools.find_public_buckets,
    "find_open_security_groups": aws_tools.find_open_security_groups,
}

SCHEMAS = [
    tool_schema("audit_iam_users", "IAM findings: overly-broad policies, stale keys, missing MFA."),
    tool_schema("find_public_buckets", "S3 buckets with public read/write access."),
    tool_schema("find_open_security_groups", "Security groups with 0.0.0.0/0 ingress on sensitive ports."),
]


def build(ctx, llm: LLMClient):
    bound = {n: partial(fn, ctx) for n, fn in TOOL_FUNCS.items()}
    return build_tool_agent(NAME, bound, SCHEMAS, SYSTEM_PROMPT, llm)


def card() -> dict:
    return {
        "name": NAME,
        "description": "Audits IAM, S3, and security groups for misconfigurations.",
        "tier": "READ",
        "skills": [{"name": n, "description": s["description"]} for n, s in zip(TOOL_FUNCS, SCHEMAS)],
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
    }
