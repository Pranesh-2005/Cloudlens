"""Pure-python cost forecaster: linear trend + weekly seasonality + simple confidence band.

No numpy/scipy - Render free tier has 512MB RAM. Just least-squares by hand.
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Any

METHOD = "linear_trend+weekly_seasonality"

NAME = "forecaster"


def _linear_fit(y: list[float]) -> tuple[float, float]:
    """Ordinary least squares y = a + b*x, x = 0..n-1. Returns (a, b)."""
    n = len(y)
    if n < 2:
        return (y[0] if y else 0.0, 0.0)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(y) / n
    num = sum((x - mean_x) * (yv - mean_y) for x, yv in zip(xs, y))
    den = sum((x - mean_x) ** 2 for x in xs)
    b = num / den if den else 0.0
    a = mean_y - b * mean_x
    return a, b


def _weekday_seasonality(dates: list[dt.date], y: list[float], a: float, b: float) -> dict[int, float]:
    """Average residual (actual - trend) per weekday, used as an additive seasonal offset."""
    buckets: dict[int, list[float]] = {i: [] for i in range(7)}
    for i, (d, actual) in enumerate(zip(dates, y)):
        trend = a + b * i
        buckets[d.weekday()].append(actual - trend)
    return {wd: (sum(vals) / len(vals) if vals else 0.0) for wd, vals in buckets.items()}


def _residual_stddev(y: list[float], a: float, b: float) -> float:
    n = len(y)
    if n < 2:
        return 0.0
    residuals = [yv - (a + b * i) for i, yv in enumerate(y)]
    mean_r = sum(residuals) / n
    var = sum((r - mean_r) ** 2 for r in residuals) / max(n - 1, 1)
    return math.sqrt(var)


def forecast(daily: list[dict[str, Any]], horizon_days: int = 30, z: float = 1.28) -> dict[str, Any]:
    """daily: [{"date": "YYYY-MM-DD", "amount": float}, ...] sorted ascending.

    z=1.28 ~ 80% confidence band (kept simple, no scipy norm.ppf).
    """
    if not daily:
        return {"forecast": [], "method": METHOD}

    dates = [dt.date.fromisoformat(d["date"]) for d in daily]
    y = [float(d["amount"]) for d in daily]
    n = len(y)

    a, b = _linear_fit(y)
    seasonal = _weekday_seasonality(dates, y, a, b)
    stddev = _residual_stddev(y, a, b)

    out = []
    last_date = dates[-1]
    for h in range(1, horizon_days + 1):
        x = n - 1 + h
        future_date = last_date + dt.timedelta(days=h)
        trend = a + b * x
        point = max(0.0, trend + seasonal.get(future_date.weekday(), 0.0))
        # widen the band the further out we forecast
        band = z * stddev * math.sqrt(1 + h / max(n, 1))
        out.append(
            {
                "date": future_date.isoformat(),
                "amount": round(point, 2),
                "lower": round(max(0.0, point - band), 2),
                "upper": round(point + band, 2),
            }
        )
    return {"forecast": out, "method": METHOD}


# ---------------------------------------------------------------------------
# LangGraph agent wrapper (spec's agent table lists forecaster as an agent too,
# reusing this same module rather than a second file).
# ---------------------------------------------------------------------------
from functools import partial  # noqa: E402

SYSTEM_PROMPT = (
    "You are CloudLens's forecaster agent. You predict future AWS spend from historical daily "
    "costs using the tools available - never invent numbers, and always mention the forecast "
    "method and confidence band."
)

def _tool_funcs_and_schemas():
    # Imported lazily: app.aws.tools imports forecast() from this module at its own
    # top level, so importing app.aws.tools back at *our* top level would be circular.
    from app.agents.graph import tool_schema
    from app.aws import tools as aws_tools

    tool_funcs = {"get_daily_costs": aws_tools.get_daily_costs, "forecast_costs": aws_tools.forecast_costs}
    schemas = [
        tool_schema("get_daily_costs", "Raw daily cost series.", {"days": {"type": "integer"}}),
        tool_schema("forecast_costs", "Forecast the next N days of spend.", {"days": {"type": "integer"}}),
    ]
    return tool_funcs, schemas


def build(ctx, llm):
    from app.agents.graph import build_tool_agent

    tool_funcs, schemas = _tool_funcs_and_schemas()
    bound = {n: partial(fn, ctx) for n, fn in tool_funcs.items()}
    return build_tool_agent(NAME, bound, schemas, SYSTEM_PROMPT, llm)


def card() -> dict:
    tool_funcs, schemas = _tool_funcs_and_schemas()
    return {
        "name": NAME,
        "description": "Forecasts AWS spend via linear trend + weekly seasonality.",
        "tier": "READ",
        "skills": [{"name": n, "description": s["description"]} for n, s in zip(tool_funcs, schemas)],
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
    }
