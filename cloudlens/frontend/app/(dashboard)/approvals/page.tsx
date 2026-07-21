"use client";

import { useEffect, useState } from "react";
import { api, ApiError, Approval } from "@/lib/api";
import { Button, Card, EmptyState, PageHeader, Skeleton } from "@/components/ui";

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<Approval[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deciding, setDeciding] = useState<string | null>(null);

  function load() {
    setLoading(true);
    api
      .approvals()
      .then(setApprovals)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load approvals"))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function decide(id: string, decision: "approve" | "reject") {
    setDeciding(id);
    try {
      await api.decideApproval(id, decision);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to record decision");
    } finally {
      setDeciding(null);
    }
  }

  const pending = (approvals ?? []).filter((a) => a.status === "pending");
  const history = (approvals ?? []).filter((a) => a.status !== "pending");

  return (
    <div>
      <PageHeader title="Approvals" description="EXECUTE-tier actions paused for human sign-off." />

      {error && (
        <p className="mb-6 rounded-lg border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error}
        </p>
      )}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : (
        <>
          <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-white/35">
            Pending ({pending.length})
          </h2>
          {pending.length === 0 ? (
            <EmptyState title="Nothing waiting on you" description="Pending EXECUTE actions will appear here." />
          ) : (
            <div className="space-y-2">
              {pending.map((a) => (
                <Card key={a.id}>
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-300">
                          {a.action}
                        </span>
                        <span className="text-xs text-white/35">via {a.requested_by_agent}</span>
                      </div>
                      <p className="mt-1.5 text-sm text-white/70">{a.reason}</p>
                      {a.params && Object.keys(a.params).length > 0 && (
                        <pre className="mt-2 max-w-lg overflow-x-auto rounded-md bg-black/30 px-3 py-2 text-xs text-white/45">
                          {JSON.stringify(a.params, null, 2)}
                        </pre>
                      )}
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        variant="secondary"
                        disabled={deciding === a.id}
                        onClick={() => decide(a.id, "reject")}
                      >
                        Reject
                      </Button>
                      <Button
                        variant="primary"
                        disabled={deciding === a.id}
                        onClick={() => decide(a.id, "approve")}
                      >
                        Approve
                      </Button>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}

          <h2 className="mb-2 mt-8 text-xs font-medium uppercase tracking-wide text-white/35">
            History
          </h2>
          {history.length === 0 ? (
            <EmptyState title="No decided approvals yet" />
          ) : (
            <Card className="p-0 overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="border-b border-white/8 px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-white/35">
                      Action
                    </th>
                    <th className="border-b border-white/8 px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-white/35">
                      Agent
                    </th>
                    <th className="border-b border-white/8 px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-white/35">
                      Status
                    </th>
                    <th className="border-b border-white/8 px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-white/35">
                      Requested
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((a) => (
                    <tr key={a.id} className="border-b border-white/5 last:border-0">
                      <td className="px-4 py-2.5 text-sm text-white/75">{a.action}</td>
                      <td className="px-4 py-2.5 text-sm text-white/50">{a.requested_by_agent}</td>
                      <td className="px-4 py-2.5 text-sm">
                        <span
                          className={
                            a.status === "approved"
                              ? "text-emerald-400"
                              : "text-rose-400"
                          }
                        >
                          {a.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-white/30">
                        {new Date(a.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
