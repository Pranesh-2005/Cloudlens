"""boto3 session per-tenant from decrypted creds; demo-mode deterministic fake data."""
from __future__ import annotations

import asyncio
import datetime as dt
import random
from typing import Any


async def to_thread(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def get_boto3_session(access_key_id: str, secret_access_key: str, region: str):
    import boto3

    return boto3.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region,
    )


# ---------------------------------------------------------------------------
# Demo mode: deterministic realistic fake data (no AWS account required).
# ---------------------------------------------------------------------------

_EC2_TYPES = ["t3.micro", "t3.small", "t3.medium", "m5.large", "m5.xlarge", "c5.large"]
_EC2_STATES = ["running", "running", "running", "stopped"]
_SERVICES = ["Amazon EC2", "Amazon RDS", "Amazon S3", "AWS Lambda", "Amazon CloudFront", "Amazon VPC"]


def _rng(seed: int) -> random.Random:
    return random.Random(seed)


def gen_ec2(seed: int, n: int = 12) -> list[dict[str, Any]]:
    r = _rng(seed)
    out = []
    for i in range(n):
        out.append(
            {
                "instance_id": f"i-{r.randrange(16**12):012x}",
                "instance_type": r.choice(_EC2_TYPES),
                "state": r.choice(_EC2_STATES),
                "region": "us-east-1",
                "name": f"app-server-{i+1}",
                "launched_at": (dt.date.today() - dt.timedelta(days=r.randrange(1, 400))).isoformat(),
            }
        )
    return out


def gen_s3(seed: int, n: int = 8) -> list[dict[str, Any]]:
    r = _rng(seed)
    out = []
    for i in range(n):
        out.append(
            {
                "bucket": f"cloudlens-demo-bucket-{i+1}",
                "public": i == 2,  # exactly 1 public bucket, deterministic
                "region": "us-east-1",
                "size_gb": round(r.uniform(0.1, 500), 2),
                "objects": r.randrange(10, 500_000),
            }
        )
    return out


def gen_rds(seed: int, n: int = 3) -> list[dict[str, Any]]:
    r = _rng(seed)
    engines = ["postgres", "mysql", "postgres"]
    out = []
    for i in range(n):
        out.append(
            {
                "db_instance_id": f"cloudlens-db-{i+1}",
                "engine": engines[i % len(engines)],
                "instance_class": r.choice(["db.t3.micro", "db.t3.small", "db.m5.large"]),
                "status": "available",
                "multi_az": i == 0,
            }
        )
    return out


def gen_lambda(seed: int, n: int = 6) -> list[dict[str, Any]]:
    r = _rng(seed)
    out = []
    for i in range(n):
        out.append(
            {
                "function_name": f"cloudlens-fn-{i+1}",
                "runtime": r.choice(["python3.12", "nodejs20.x"]),
                "memory_mb": r.choice([128, 256, 512, 1024]),
                "invocations_24h": r.randrange(0, 50_000),
            }
        )
    return out


def gen_all_resources(seed: int) -> list[dict[str, Any]]:
    out = []
    for e in gen_ec2(seed):
        out.append(
            {
                "arn": f"arn:aws:ec2:us-east-1:000000000000:instance/{e['instance_id']}",
                "service": "ec2", "type": "instance", "id": e["instance_id"],
                "region": "us-east-1", "name": e["name"],
            }
        )
    for b in gen_s3(seed):
        out.append(
            {
                "arn": f"arn:aws:s3:::{b['bucket']}",
                "service": "s3", "type": "bucket", "id": b["bucket"], "region": "global", "name": b["bucket"],
            }
        )
    for d in gen_rds(seed):
        out.append(
            {
                "arn": f"arn:aws:rds:us-east-1:000000000000:db:{d['db_instance_id']}",
                "service": "rds", "type": "db", "id": d["db_instance_id"], "region": "us-east-1", "name": "",
            }
        )
    for f in gen_lambda(seed):
        out.append(
            {
                "arn": f"arn:aws:lambda:us-east-1:000000000000:function:{f['function_name']}",
                "service": "lambda", "type": "function", "id": f["function_name"],
                "region": "us-east-1", "name": f["function_name"],
            }
        )
    out.append(
        {
            "arn": "arn:aws:bedrock-agentcore:us-east-1:000000000000:runtime/demo-agent-runtime",
            "service": "bedrock-agentcore", "type": "runtime", "id": "demo-agent-runtime",
            "region": "us-east-1", "name": "demo-agent-runtime",
        }
    )
    return out


def gen_daily_costs(seed: int, days: int = 90) -> list[dict[str, Any]]:
    r = _rng(seed)
    base = 40.0
    trend_per_day = 0.35
    out = []
    today = dt.date.today()
    for i in range(days):
        day = today - dt.timedelta(days=days - 1 - i)
        weekday_factor = 0.85 if day.weekday() >= 5 else 1.05  # weekend dip
        noise = r.uniform(-4, 4)
        amount = max(5.0, base + trend_per_day * i) * weekday_factor + noise
        out.append({"date": day.isoformat(), "amount": round(amount, 2)})
    return out


def gen_cost_by_service(seed: int, total: float) -> list[dict[str, Any]]:
    r = _rng(seed)
    weights = [r.uniform(0.5, 1.0) for _ in _SERVICES]
    wsum = sum(weights)
    return [
        {"service": s, "amount": round(total * w / wsum, 2)}
        for s, w in sorted(zip(_SERVICES, weights), key=lambda x: -x[1])
    ]


def gen_iam_findings(seed: int) -> list[dict[str, Any]]:
    return [
        {
            "kind": "iam",
            "severity": "high",
            "resource": "user:ci-deploy-bot",
            "summary": "IAM user has AdministratorAccess attached directly (not via a role) and an access key older than 180 days.",
        },
        {
            "kind": "iam",
            "severity": "medium",
            "resource": "user:legacy-svc-account",
            "summary": "IAM user has no MFA device configured.",
        },
    ]


def gen_open_security_groups(seed: int) -> list[dict[str, Any]]:
    return [
        {
            "group_id": "sg-0demo1234abcd",
            "port": 22,
            "cidr": "0.0.0.0/0",
            "summary": "SSH (22) open to the world on security group attached to app-server-1.",
        }
    ]


def gen_cloudwatch_metrics(seed: int, instance_id: str) -> dict[str, Any]:
    r = _rng(seed + hash(instance_id) % 1000)
    return {
        "instance_id": instance_id,
        "cpu_utilization_avg": round(r.uniform(5, 85), 1),
        "network_in_mb": round(r.uniform(10, 5000), 1),
        "network_out_mb": round(r.uniform(10, 5000), 1),
    }
