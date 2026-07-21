"use client";

import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, ApiError, CostsForecast, CostsSummary, MeResponse, SecurityFinding } from "@/lib/api";
import { Card, DemoBanner, EmptyState, PageHeader, Skeleton, StatTile } from "@/components/ui";

const CYAN = "#22d3ee";

function fmtCurrency(n: number, currency: string) {
  const v = Object.is(n, -0) || Math.abs(n) < 1e-9 ? 0 : n;
  // adaptive precision: big numbers stay clean, sub-cent spend stays visible
  const digits = Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 1 ? 2 : 4;
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: digits }).format(v);
}

function daysInMonthSoFar() {
  const now = new Date();
  return now.getDate();
}

// "AWS KeyManagementService" -> "Key Management Service"
function prettyService(name: string) {
  return name
    .replace(/^(AWS|Amazon)\s*/i, "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .trim();
}

export default function OverviewPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [summary, setSummary] = useState<CostsSummary | null>(null);
  const [forecast, setForecast] = useState<CostsForecast | null>(null);
  const [findings, setFindings] = useState<SecurityFinding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [meRes, summaryRes, forecastRes, findingsRes] = await Promise.all([
          api.me(),
          api.costsSummary(30),
          api.costsForecast(30),
          api.securityFindings(),
        ]);
        if (cancelled) return;
        setMe(meRes);
        setSummary(summaryRes);
        setForecast(forecastRes);
        setFindings(findingsRes);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load overview");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const demo = me?.demo_mode ?? summary?.demo ?? false;

  // EOM = spend so far + forecast daily amounts for the rest of this month
  // (last forecast point alone is a per-day figure, not month total)
  const monthPrefix = new Date().toISOString().slice(0, 7);
  const forecastEom =
    forecast && summary
      ? summary.daily
          .filter((d) => d.date.startsWith(monthPrefix))
          .reduce((acc, d) => acc + d.amount, 0) +
        forecast.forecast
          .filter((f) => f.date.startsWith(monthPrefix))
          .reduce((acc, f) => acc + f.amount, 0)
      : undefined;
  const dailyAvg = summary && summary.daily.length ? summary.total / summary.daily.length : 0;
  const deltaPct =
    summary && dailyAvg
      ? ((summary.total / Math.max(1, daysInMonthSoFar())) / dailyAvg - 1) * 100
      : 0;

  const chartData = buildChartData(summary, forecast);

  const severityCounts = (findings ?? []).reduce<Record<string, number>>((acc, f) => {
    acc[f.severity] = (acc[f.severity] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div>
      <PageHeader title="Overview" description="Spend, forecast, and security posture at a glance." />

      <div className="mb-6">
        <DemoBanner show={demo} />
      </div>

      {error && (
        <p className="mb-6 rounded-lg border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error}
        </p>
      )}

      {loading ? (
        <div className="grid grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-4">
          <StatTile
            label="Spend, MTD"
            value={summary ? fmtCurrency(summary.total, summary.currency) : "—"}
          />
          <StatTile
            label="Forecast, EOM"
            value={forecastEom !== undefined ? fmtCurrency(forecastEom, summary?.currency ?? "USD") : "—"}
            sub={forecast ? `via ${forecast.method}` : undefined}
          />
          <StatTile
            label="Trend vs. avg"
            value={`${deltaPct >= 0 ? "+" : ""}${deltaPct.toFixed(1)}%`}
            tone={deltaPct > 0 ? "up" : deltaPct < 0 ? "down" : "default"}
            sub="Today vs. 30-day daily average"
          />
          <StatTile
            label="Security findings"
            value={String(findings?.length ?? 0)}
            sub={
              severityCounts.critical
                ? `${severityCounts.critical} critical`
                : severityCounts.high
                  ? `${severityCounts.high} high`
                  : "No critical issues"
            }
            tone={severityCounts.critical ? "up" : "default"}
          />
        </div>
      )}

      <div className="mt-6 grid grid-cols-3 gap-4">
        <Card className="col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-medium text-white/70">Daily cost &amp; forecast</h2>
            <div className="flex items-center gap-3 text-[11px] text-white/40">
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-1.5 w-3 rounded-full bg-cyan-400" /> Actual
              </span>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-1.5 w-3 rounded-full border border-cyan-400/60 border-dashed" /> Forecast
              </span>
            </div>
          </div>
          {loading ? (
            <Skeleton className="h-64" />
          ) : chartData.length === 0 ? (
            <EmptyState title="No cost data yet" description="Connect AWS credentials or wait for demo data to populate." />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={chartData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <defs>
                  <linearGradient id="actualFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={CYAN} stopOpacity={0.25} />
                    <stop offset="100%" stopColor={CYAN} stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="bandFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={CYAN} stopOpacity={0.12} />
                    <stop offset="100%" stopColor={CYAN} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#ffffff10" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fill: "#ffffff55", fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: "#ffffff15" }}
                  minTickGap={40}
                />
                <YAxis
                  tick={{ fill: "#ffffff55", fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={48}
                  tickFormatter={(v) => `$${v}`}
                />
                <Tooltip
                  contentStyle={{
                    background: "#0d0f14",
                    border: "1px solid #ffffff1a",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "#ffffffaa" }}
                  formatter={(value, name) => [
                    typeof value === "number" ? fmtCurrency(value, summary?.currency ?? "USD") : String(value),
                    String(name),
                  ]}
                />
                <Area
                  type="monotone"
                  dataKey="upper"
                  stroke="none"
                  fill="url(#bandFill)"
                  name="Forecast upper"
                  isAnimationActive={false}
                />
                <Area
                  type="monotone"
                  dataKey="lower"
                  stroke="none"
                  fill="#08090c"
                  fillOpacity={1}
                  name="Forecast lower"
                  isAnimationActive={false}
                  legendType="none"
                />
                <Area
                  type="monotone"
                  dataKey="actual"
                  stroke={CYAN}
                  strokeWidth={2}
                  fill="url(#actualFill)"
                  name="Actual"
                  connectNulls
                  isAnimationActive={false}
                />
                <Area
                  type="monotone"
                  dataKey="forecastAmount"
                  stroke={CYAN}
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  fill="none"
                  name="Forecast"
                  connectNulls
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>

        <TopServices loading={loading} summary={summary} />
      </div>
    </div>
  );
}

const PAGE_SIZE = 5;

function TopServices({ loading, summary }: { loading: boolean; summary: CostsSummary | null }) {
  const [page, setPage] = useState(0);
  const services = [...(summary?.by_service ?? [])]
    .sort((a, b) => b.amount - a.amount)
    .map((s) => ({ ...s, service: prettyService(s.service) }));
  const pages = Math.max(1, Math.ceil(services.length / PAGE_SIZE));
  const visible = services.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-medium text-white/70">Top services</h2>
        {pages > 1 && (
          <div className="flex items-center gap-2 text-[11px] text-white/40">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded px-1.5 py-0.5 hover:bg-white/5 disabled:opacity-30"
            >
              ‹
            </button>
            {page + 1}/{pages}
            <button
              onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}
              disabled={page === pages - 1}
              className="rounded px-1.5 py-0.5 hover:bg-white/5 disabled:opacity-30"
            >
              ›
            </button>
          </div>
        )}
      </div>
      {loading ? (
        <Skeleton className="h-64" />
      ) : !summary || services.length === 0 ? (
        <EmptyState title="No service breakdown" />
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart
            data={visible}
            layout="vertical"
            margin={{ top: 4, right: 16, left: 0, bottom: 0 }}
          >
            <CartesianGrid stroke="#ffffff10" horizontal={false} />
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="service"
              tick={{ fill: "#ffffff70", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={110}
            />
            <Tooltip
              cursor={{ fill: "#ffffff08" }}
              contentStyle={{
                background: "#0d0f14",
                border: "1px solid #ffffff1a",
                borderRadius: 8,
                fontSize: 12,
              }}
              formatter={(value) =>
                typeof value === "number" ? fmtCurrency(value, summary.currency) : String(value)
              }
            />
            <Bar dataKey="amount" fill={CYAN} fillOpacity={0.75} radius={[0, 4, 4, 0]} barSize={16} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

function buildChartData(summary: CostsSummary | null, forecast: CostsForecast | null) {
  if (!summary) return [];
  const rows: Record<string, number | string | null>[] = summary.daily.map((d) => ({
    date: d.date,
    actual: d.amount,
    forecastAmount: null,
    lower: null,
    upper: null,
  }));

  const lastActual = summary.daily[summary.daily.length - 1];
  if (forecast && lastActual) {
    // Bridge the forecast dashed line to the last actual point so it reads
    // as a continuation rather than a gap.
    rows[rows.length - 1] = {
      ...rows[rows.length - 1],
      forecastAmount: lastActual.amount,
      lower: lastActual.amount,
      upper: lastActual.amount,
    };
    for (const f of forecast.forecast) {
      rows.push({
        date: f.date,
        actual: null,
        forecastAmount: f.amount,
        lower: f.lower,
        upper: f.upper,
      });
    }
  }
  return rows;
}
