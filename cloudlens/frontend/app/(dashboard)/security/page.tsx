"use client";

import { useEffect, useState } from "react";
import { api, ApiError, SecurityFinding } from "@/lib/api";
import { Card, EmptyState, PageHeader, SeverityBadge, Skeleton } from "@/components/ui";

export default function SecurityPage() {
  const [findings, setFindings] = useState<SecurityFinding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .securityFindings()
      .then((res) => {
        if (!cancelled) setFindings(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load findings");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const severityOrder = ["critical", "high", "medium", "low", "info"];
  const sorted = [...(findings ?? [])].sort(
    (a, b) => severityOrder.indexOf(a.severity) - severityOrder.indexOf(b.severity)
  );

  return (
    <div>
      <PageHeader title="Security" description="Findings from the security-auditor agent." />

      {error && (
        <p className="mb-6 rounded-lg border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error}
        </p>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : sorted.length === 0 ? (
        <EmptyState title="No findings" description="Your account looks clean — nothing flagged by the auditor." />
      ) : (
        <div className="space-y-2">
          {sorted.map((f) => (
            <Card key={f.id} className="flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={f.severity} />
                  <span className="text-sm font-medium text-white/85">{f.kind}</span>
                </div>
                <p className="mt-1.5 text-sm text-white/55">{f.summary}</p>
                <p className="mt-1 text-xs text-white/30">{f.resource}</p>
              </div>
              <span className="shrink-0 text-xs text-white/30">
                {new Date(f.detected_at).toLocaleString()}
              </span>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
