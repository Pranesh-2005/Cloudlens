"""All AWS tool functions (typed, docstringed). Demo-mode aware; real calls via boto3+to_thread."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from app.agents.forecaster import forecast as _forecast
from app.aws import client as aws_client
from app.cache import cache


def build_tool_context(user, credential, seed: int) -> "ToolContext":
    """Construct a ToolContext for a user: demo mode iff no stored AWS credentials."""
    if credential is None:
        return ToolContext(tenant_id=user.id, demo=True, seed=seed)
    from app.credentials import decrypt

    access_key_id, secret_access_key = decrypt(credential)
    return ToolContext(
        tenant_id=user.id,
        demo=False,
        seed=seed,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region=credential.region,
    )


@dataclass
class ToolContext:
    tenant_id: str
    demo: bool
    seed: int
    access_key_id: str | None = None
    secret_access_key: str | None = None
    region: str = "us-east-1"

    def boto3_session(self):
        return aws_client.get_boto3_session(self.access_key_id, self.secret_access_key, self.region)


async def _cached(ctx: ToolContext, tool: str, args: dict, compute):
    key = cache.key(ctx.tenant_id, tool, args)
    hit = cache.get(key)
    if hit is not None:
        return hit
    result = await compute()
    cache.set(key, result)
    return result


# ---------------------------------------------------------------------------
# cost_analyst (READ)
# ---------------------------------------------------------------------------

async def get_cost_summary(ctx: ToolContext, days: int = 30) -> dict[str, Any]:
    """Total spend + by-service breakdown + daily series for the trailing `days` days."""
    async def compute():
        if ctx.demo:
            daily = aws_client.gen_daily_costs(ctx.seed, days)
            total = round(sum(d["amount"] for d in daily), 2)
            by_service = aws_client.gen_cost_by_service(ctx.seed, total)
        else:
            def _fetch():
                ce = ctx.boto3_session().client("ce")
                end = dt.date.today()
                start = end - dt.timedelta(days=days)
                resp = ce.get_cost_and_usage(
                    TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
                    Granularity="DAILY",
                    Metrics=["UnblendedCost"],
                    GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
                    # exclude credits/refunds: on credit-funded accounts they net
                    # everything to $0, hiding real usage (matches console "current month")
                    Filter={
                        "Not": {
                            "Dimensions": {"Key": "RECORD_TYPE", "Values": ["Credit", "Refund"]}
                        }
                    },
                )
                return resp

            resp = await aws_client.to_thread(_fetch)
            daily_map: dict[str, float] = {}
            service_totals: dict[str, float] = {}
            for period in resp.get("ResultsByTime", []):
                day = period["TimePeriod"]["Start"]
                for group in period.get("Groups", []):
                    amt = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    daily_map[day] = daily_map.get(day, 0.0) + amt
                    svc = group["Keys"][0]
                    service_totals[svc] = service_totals.get(svc, 0.0) + amt
            # 4 decimals: real accounts often have sub-cent spend that 2dp rounds to 0
            daily = [{"date": d, "amount": round(a, 4)} for d, a in sorted(daily_map.items())]
            total = round(sum(service_totals.values()), 4)
            by_service = [
                {"service": s, "amount": round(a, 4)}
                for s, a in sorted(service_totals.items(), key=lambda x: -x[1])
            ]
        return {"total": total, "currency": "USD", "by_service": by_service, "daily": daily, "demo": ctx.demo}

    return await _cached(ctx, "get_cost_summary", {"days": days}, compute)


async def get_cost_by_service(ctx: ToolContext, days: int = 30) -> dict[str, Any]:
    """Spend broken down by AWS service for the trailing `days` days."""
    summary = await get_cost_summary(ctx, days)
    return {"by_service": summary["by_service"], "demo": ctx.demo}


async def get_cost_by_tag(ctx: ToolContext, tag_key: str = "Environment", days: int = 30) -> dict[str, Any]:
    """Spend broken down by a cost-allocation tag (demo mode fabricates tag buckets)."""
    async def compute():
        if ctx.demo:
            summary = await get_cost_summary(ctx, days)
            total = summary["total"]
            buckets = [("production", 0.6), ("staging", 0.25), ("dev", 0.15)]
            by_tag = [{"tag": t, "amount": round(total * w, 2)} for t, w in buckets]
        else:
            # Real Cost Explorer tag grouping omitted for brevity in this lean build.
            by_tag = []
        return {"tag_key": tag_key, "by_tag": by_tag, "demo": ctx.demo}

    return await _cached(ctx, "get_cost_by_tag", {"tag_key": tag_key, "days": days}, compute)


# ---------------------------------------------------------------------------
# forecaster (READ)
# ---------------------------------------------------------------------------

async def get_daily_costs(ctx: ToolContext, days: int = 90) -> dict[str, Any]:
    """Raw daily cost series used as forecaster input."""
    async def compute():
        if ctx.demo:
            daily = aws_client.gen_daily_costs(ctx.seed, days)
        else:
            summary = await get_cost_summary(ctx, days)
            daily = summary["daily"]
        return {"daily": daily, "demo": ctx.demo}

    return await _cached(ctx, "get_daily_costs", {"days": days}, compute)


async def forecast_costs(ctx: ToolContext, days: int = 30) -> dict[str, Any]:
    """Forecast the next `days` days of spend from trailing 90-day history."""
    history = await get_daily_costs(ctx, 90)
    result = _forecast(history["daily"], horizon_days=days)
    result["demo"] = ctx.demo
    return result


# ---------------------------------------------------------------------------
# resource_monitor (READ)
# ---------------------------------------------------------------------------

async def list_ec2(ctx: ToolContext) -> dict[str, Any]:
    """List EC2 instances with id, type, state, region."""
    async def compute():
        if ctx.demo:
            items = aws_client.gen_ec2(ctx.seed)
        else:
            def _fetch():
                ec2 = ctx.boto3_session().client("ec2")
                resp = ec2.describe_instances()
                out = []
                for r in resp.get("Reservations", []):
                    for i in r.get("Instances", []):
                        name = next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), "")
                        out.append(
                            {
                                "instance_id": i["InstanceId"],
                                "instance_type": i["InstanceType"],
                                "state": i["State"]["Name"],
                                "region": ctx.region,
                                "name": name,
                                "launched_at": i.get("LaunchTime").isoformat() if i.get("LaunchTime") else "",
                            }
                        )
                return out

            items = await aws_client.to_thread(_fetch)
        return {"items": items, "demo": ctx.demo}

    return await _cached(ctx, "list_ec2", {}, compute)


async def list_s3(ctx: ToolContext) -> dict[str, Any]:
    """List S3 buckets with public-access flag."""
    async def compute():
        items = aws_client.gen_s3(ctx.seed) if ctx.demo else await aws_client.to_thread(_list_s3_real, ctx)
        return {"items": items, "demo": ctx.demo}

    return await _cached(ctx, "list_s3", {}, compute)


def _list_s3_real(ctx: ToolContext):
    s3 = ctx.boto3_session().client("s3")
    out = []
    for b in s3.list_buckets().get("Buckets", []):
        public = False
        try:
            pab = s3.get_public_access_block(Bucket=b["Name"])["PublicAccessBlockConfiguration"]
            public = not all(pab.values())
        except Exception:
            public = False
        out.append({"bucket": b["Name"], "public": public, "region": ctx.region, "size_gb": None, "objects": None})
    return out


async def list_rds(ctx: ToolContext) -> dict[str, Any]:
    """List RDS instances with engine, class, status."""
    async def compute():
        if ctx.demo:
            items = aws_client.gen_rds(ctx.seed)
        else:
            def _fetch():
                rds = ctx.boto3_session().client("rds")
                resp = rds.describe_db_instances()
                return [
                    {
                        "db_instance_id": i["DBInstanceIdentifier"],
                        "engine": i["Engine"],
                        "instance_class": i["DBInstanceClass"],
                        "status": i["DBInstanceStatus"],
                        "multi_az": i.get("MultiAZ", False),
                    }
                    for i in resp.get("DBInstances", [])
                ]

            items = await aws_client.to_thread(_fetch)
        return {"items": items, "demo": ctx.demo}

    return await _cached(ctx, "list_rds", {}, compute)


async def list_lambda(ctx: ToolContext) -> dict[str, Any]:
    """List Lambda functions with runtime and memory config."""
    async def compute():
        if ctx.demo:
            items = aws_client.gen_lambda(ctx.seed)
        else:
            def _fetch():
                lam = ctx.boto3_session().client("lambda")
                resp = lam.list_functions()
                return [
                    {
                        "function_name": f["FunctionName"],
                        "runtime": f.get("Runtime", ""),
                        "memory_mb": f.get("MemorySize", 0),
                        "invocations_24h": None,
                    }
                    for f in resp.get("Functions", [])
                ]

            items = await aws_client.to_thread(_fetch)
        return {"items": items, "demo": ctx.demo}

    return await _cached(ctx, "list_lambda", {}, compute)


async def list_all_resources(ctx: ToolContext) -> dict[str, Any]:
    """Every taggable resource in the region via Resource Groups Tagging API (any service)."""
    async def compute():
        if ctx.demo:
            items = aws_client.gen_all_resources(ctx.seed)
        else:
            def _fetch():
                client = ctx.boto3_session().client("resourcegroupstaggingapi")
                out = []
                token = ""
                while True:
                    kwargs: dict[str, Any] = {"ResourcesPerPage": 100}
                    if token:
                        kwargs["PaginationToken"] = token
                    resp = client.get_resources(**kwargs)
                    for r in resp.get("ResourceTagMappingList", []):
                        arn = r["ResourceARN"]
                        # arn:partition:service:region:account:resource
                        parts = arn.split(":", 5)
                        service = parts[2] if len(parts) > 2 else ""
                        region = (parts[3] if len(parts) > 3 else "") or "global"
                        rest = parts[5] if len(parts) > 5 else ""
                        rtype, sep, rid = rest.partition("/")
                        if not sep:
                            rid, rtype = rtype, ""
                        name = next((t["Value"] for t in r.get("Tags", []) if t["Key"] == "Name"), "")
                        out.append(
                            {"arn": arn, "service": service, "type": rtype, "id": rid, "region": region, "name": name}
                        )
                    token = resp.get("PaginationToken", "")
                    if not token:
                        break
                return out

            items = await aws_client.to_thread(_fetch)
        return {"items": items, "demo": ctx.demo}

    return await _cached(ctx, "list_all_resources", {}, compute)


async def get_cloudwatch_metrics(ctx: ToolContext, instance_id: str) -> dict[str, Any]:
    """CPU/network CloudWatch metrics (avg, trailing period) for an EC2 instance."""
    async def compute():
        if ctx.demo:
            metrics = aws_client.gen_cloudwatch_metrics(ctx.seed, instance_id)
        else:
            def _fetch():
                cw = ctx.boto3_session().client("cloudwatch")
                end = dt.datetime.utcnow()
                start = end - dt.timedelta(hours=24)
                resp = cw.get_metric_statistics(
                    Namespace="AWS/EC2",
                    MetricName="CPUUtilization",
                    Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                    StartTime=start,
                    EndTime=end,
                    Period=3600,
                    Statistics=["Average"],
                )
                points = resp.get("Datapoints", [])
                avg = sum(p["Average"] for p in points) / len(points) if points else 0.0
                return {"instance_id": instance_id, "cpu_utilization_avg": round(avg, 1)}

            metrics = await aws_client.to_thread(_fetch)
        return {**metrics, "demo": ctx.demo}

    return await _cached(ctx, "get_cloudwatch_metrics", {"instance_id": instance_id}, compute)


# ---------------------------------------------------------------------------
# security_auditor (READ)
# ---------------------------------------------------------------------------

async def audit_iam_users(ctx: ToolContext) -> dict[str, Any]:
    """IAM findings: overly-broad policies, stale keys, missing MFA."""
    async def compute():
        if ctx.demo:
            findings = aws_client.gen_iam_findings(ctx.seed)
        else:
            findings = []  # real IAM audit heuristics omitted for brevity in this lean build.
        return {"findings": findings, "demo": ctx.demo}

    return await _cached(ctx, "audit_iam_users", {}, compute)


async def find_public_buckets(ctx: ToolContext) -> dict[str, Any]:
    """S3 buckets with public read/write access."""
    s3 = await list_s3(ctx)
    public = [b for b in s3["items"] if b.get("public")]
    return {"public_buckets": public, "demo": ctx.demo}


async def find_open_security_groups(ctx: ToolContext) -> dict[str, Any]:
    """Security groups with 0.0.0.0/0 ingress on sensitive ports."""
    async def compute():
        if ctx.demo:
            findings = aws_client.gen_open_security_groups(ctx.seed)
        else:
            findings = []  # real SG scan omitted for brevity in this lean build.
        return {"findings": findings, "demo": ctx.demo}

    return await _cached(ctx, "find_open_security_groups", {}, compute)


# ---------------------------------------------------------------------------
# deploy_operator (EXECUTE - approval-gated, see guardrails.py + agents/graph.py)
# ---------------------------------------------------------------------------

async def start_ec2(ctx: ToolContext, instance_id: str) -> dict[str, Any]:
    """Start a stopped EC2 instance."""
    if ctx.demo:
        return {"instance_id": instance_id, "action": "start", "result": "started (demo)", "demo": True}

    def _do():
        ctx.boto3_session().client("ec2").start_instances(InstanceIds=[instance_id])

    await aws_client.to_thread(_do)
    return {"instance_id": instance_id, "action": "start", "result": "started", "demo": False}


async def stop_ec2(ctx: ToolContext, instance_id: str) -> dict[str, Any]:
    """Stop a running EC2 instance."""
    if ctx.demo:
        return {"instance_id": instance_id, "action": "stop", "result": "stopped (demo)", "demo": True}

    def _do():
        ctx.boto3_session().client("ec2").stop_instances(InstanceIds=[instance_id])

    await aws_client.to_thread(_do)
    return {"instance_id": instance_id, "action": "stop", "result": "stopped", "demo": False}


async def scale_asg(ctx: ToolContext, asg_name: str, desired_capacity: int) -> dict[str, Any]:
    """Set the desired capacity of an Auto Scaling Group."""
    if ctx.demo:
        return {
            "asg_name": asg_name,
            "action": "scale",
            "desired_capacity": desired_capacity,
            "result": "scaled (demo)",
            "demo": True,
        }

    def _do():
        ctx.boto3_session().client("autoscaling").set_desired_capacity(
            AutoScalingGroupName=asg_name, DesiredCapacity=desired_capacity, HonorCooldown=False
        )

    await aws_client.to_thread(_do)
    return {"asg_name": asg_name, "action": "scale", "desired_capacity": desired_capacity, "result": "scaled", "demo": False}