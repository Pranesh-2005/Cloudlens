"""deploy_operator: start/stop EC2, scale ASG. EXECUTE-tier - approval-gated via graph.py."""
from __future__ import annotations

from functools import partial

from app.agents.graph import build_tool_agent, tool_schema
from app.aws import tools as aws_tools
from app.llm import LLMClient

NAME = "deploy_operator"
SYSTEM_PROMPT = (
    "You are CloudLens's deploy operator agent. You can start/stop EC2 instances and scale "
    "Auto Scaling Groups. These are EXECUTE-tier actions and will always pause for human "
    "approval before running - tell the user you're requesting approval when you call one."
)

TOOL_FUNCS = {
    "start_ec2": aws_tools.start_ec2,
    "stop_ec2": aws_tools.stop_ec2,
    "scale_asg": aws_tools.scale_asg,
}

SCHEMAS = [
    tool_schema("start_ec2", "Start a stopped EC2 instance.",
                {"instance_id": {"type": "string"}}, required=["instance_id"]),
    tool_schema("stop_ec2", "Stop a running EC2 instance.",
                {"instance_id": {"type": "string"}}, required=["instance_id"]),
    tool_schema("scale_asg", "Set the desired capacity of an Auto Scaling Group.",
                {"asg_name": {"type": "string"}, "desired_capacity": {"type": "integer"}},
                required=["asg_name", "desired_capacity"]),
]


def build(ctx, llm: LLMClient):
    bound = {n: partial(fn, ctx) for n, fn in TOOL_FUNCS.items()}
    return build_tool_agent(NAME, bound, SCHEMAS, SYSTEM_PROMPT, llm)


def card() -> dict:
    return {
        "name": NAME,
        "description": "Starts/stops EC2 and scales ASGs - all actions require human approval.",
        "tier": "EXECUTE",
        "skills": [{"name": n, "description": s["description"]} for n, s in zip(TOOL_FUNCS, SCHEMAS)],
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
    }
