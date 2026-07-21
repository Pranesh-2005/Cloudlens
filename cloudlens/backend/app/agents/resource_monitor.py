"""resource_monitor: EC2/S3/RDS/Lambda inventory, CloudWatch metrics. READ-tier only."""
from __future__ import annotations

from functools import partial

from app.agents.graph import build_tool_agent, tool_schema
from app.aws import tools as aws_tools
from app.llm import LLMClient

NAME = "resource_monitor"
SYSTEM_PROMPT = (
    "You are CloudLens's resource monitor agent. You inventory AWS resources (EC2, S3, RDS, "
    "Lambda) and report CloudWatch metrics using the tools available - never invent resources."
)

TOOL_FUNCS = {
    "list_ec2": aws_tools.list_ec2,
    "list_s3": aws_tools.list_s3,
    "list_rds": aws_tools.list_rds,
    "list_lambda": aws_tools.list_lambda,
    "get_cloudwatch_metrics": aws_tools.get_cloudwatch_metrics,
}

SCHEMAS = [
    tool_schema("list_ec2", "List EC2 instances with id, type, state, region."),
    tool_schema("list_s3", "List S3 buckets with public-access flag."),
    tool_schema("list_rds", "List RDS instances with engine, class, status."),
    tool_schema("list_lambda", "List Lambda functions with runtime and memory config."),
    tool_schema("get_cloudwatch_metrics", "CPU/network metrics for an EC2 instance.",
                {"instance_id": {"type": "string"}}, required=["instance_id"]),
]


def build(ctx, llm: LLMClient):
    bound = {n: partial(fn, ctx) for n, fn in TOOL_FUNCS.items()}
    return build_tool_agent(NAME, bound, SCHEMAS, SYSTEM_PROMPT, llm)


def card() -> dict:
    return {
        "name": NAME,
        "description": "Inventories AWS resources and reports CloudWatch metrics.",
        "tier": "READ",
        "skills": [{"name": n, "description": s["description"]} for n, s in zip(TOOL_FUNCS, SCHEMAS)],
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
    }
