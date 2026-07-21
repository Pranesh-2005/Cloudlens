import datetime as dt

from app.agents.forecaster import forecast


def _daily(days=90, base=40.0, trend=0.3):
    today = dt.date.today()
    out = []
    for i in range(days):
        day = today - dt.timedelta(days=days - 1 - i)
        out.append({"date": day.isoformat(), "amount": round(base + trend * i, 2)})
    return out


def test_forecast_empty_input():
    result = forecast([])
    assert result["forecast"] == []


def test_forecast_shape_and_method():
    result = forecast(_daily(), horizon_days=14)
    assert result["method"] == "linear_trend+weekly_seasonality"
    assert len(result["forecast"]) == 14
    for point in result["forecast"]:
        assert set(point) == {"date", "amount", "lower", "upper"}
        assert point["lower"] <= point["amount"] <= point["upper"]


def test_forecast_follows_upward_trend():
    result = forecast(_daily(base=40.0, trend=1.0), horizon_days=30)
    amounts = [p["amount"] for p in result["forecast"]]
    assert amounts[-1] > amounts[0]  # continues the upward trend


def test_forecast_band_widens_further_out():
    result = forecast(_daily(), horizon_days=30)
    first_width = result["forecast"][0]["upper"] - result["forecast"][0]["lower"]
    last_width = result["forecast"][-1]["upper"] - result["forecast"][-1]["lower"]
    assert last_width >= first_width
