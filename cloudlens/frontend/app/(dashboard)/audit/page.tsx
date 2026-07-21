"use client";

import { useEffect, useState } from "react";
import { api, ApiError, AuditEntry } from "@/lib/api";
import { Card, EmptyState, PageHeader, Skeleton } from "@/components/ui";

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .audit(100)
      .then((res) => {
        if (!cancelled) setEntries(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load audit log");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <PageHeader title="Audit log" description="Every tool call made by every agent, in order." />

      {error && (
        <p className="mb-6 rounded-lg border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error}
        </p>
      )}

      {loading ? (
        <Skeleton className="h-72" />
      ) : !entries || entries.length === 0 ? (
        <EmptyState title="No audit entries yet" description="Tool calls made during chat sessions will show up here." />
      ) : (
        <Card className="p-0 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr>
                <Th>Time</Th>
                <Th>Agent</Th>
                <Th>Tool</Th>
                <Th>Status</Th>
                <Th align="right">Latency</Th>
                <Th align="right">Tokens</Th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e, i) => (
                <tr key={i} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
                  <td className="px-4 py-2.5 text-xs text-white/40">
                    {new Date(e.ts).toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5 text-sm text-white/70">{e.agent}</td>
                  <td className="px-4 py-2.5 text-sm font-mono text-white/85">{e.tool}</td>
                  <td className="px-4 py-2.5 text-sm">
                    <span
                      className={
                        e.status === "ok" || e.status === "success"
                          ? "text-emerald-400"
                          : "text-rose-400"
                      }
                    >
                      {e.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right text-xs text-white/40">{e.latency_ms} ms</td>
                  <td className="px-4 py-2.5 text-right text-xs text-white/40">{e.tokens}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}

function Th({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return (
    <th
      className={`border-b border-white/8 px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-white/35 ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      {children}
    </th>
  );
}
