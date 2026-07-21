"use client";

import { useEffect, useState } from "react";
import {
  api,
  ApiError,
  AwsResource,
  Ec2Instance,
  LambdaFunction,
  RdsInstance,
  ResourcesResponse,
  S3Bucket,
} from "@/lib/api";
import { Card, DemoBanner, EmptyState, PageHeader, Skeleton, StateBadge } from "@/components/ui";

type Tab = "all" | "ec2" | "s3" | "rds" | "lambda";

const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "All" },
  { key: "ec2", label: "EC2" },
  { key: "s3", label: "S3" },
  { key: "rds", label: "RDS" },
  { key: "lambda", label: "Lambda" },
];

export default function ResourcesPage() {
  const [data, setData] = useState<ResourcesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("ec2");

  useEffect(() => {
    let cancelled = false;
    api
      .resources()
      .then((res) => {
        if (cancelled) return;
        setData(res);
        // land on the first tab that actually has resources
        const firstNonEmpty = TABS.find((t) => (res[t.key]?.length ?? 0) > 0);
        if (firstNonEmpty) setTab(firstNonEmpty.key);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Failed to load resources");
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
      <PageHeader title="Resources" description="Inventory across your connected AWS account." />
      <div className="mb-6">
        <DemoBanner show={!!data?.demo} />
      </div>

      {error && (
        <p className="mb-6 rounded-lg border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {error}
        </p>
      )}

      <div className="mb-4 flex gap-1 border-b border-white/8">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`relative px-3 py-2 text-sm transition-colors ${
              tab === t.key ? "text-white/90" : "text-white/40 hover:text-white/70"
            }`}
          >
            {t.label}
            {data && (
              <span className="ml-1.5 text-xs text-white/30">{data[t.key]?.length ?? 0}</span>
            )}
            {tab === t.key && (
              <span className="absolute inset-x-0 -bottom-px h-px bg-cyan-400" />
            )}
          </button>
        ))}
      </div>

      {loading ? (
        <Skeleton className="h-72" />
      ) : (
        <Card className="p-0 overflow-hidden">
          {tab === "all" && <AllTable rows={data?.all ?? []} />}
          {tab === "ec2" && <Ec2Table rows={data?.ec2 ?? []} />}
          {tab === "s3" && <S3Table rows={data?.s3 ?? []} />}
          {tab === "rds" && <RdsTable rows={data?.rds ?? []} />}
          {tab === "lambda" && <LambdaTable rows={data?.lambda ?? []} />}
        </Card>
      )}
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="border-b border-white/8 px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wide text-white/35">
      {children}
    </th>
  );
}
function Td({ children }: { children: React.ReactNode }) {
  return <td className="px-4 py-2.5 text-sm text-white/75">{children}</td>;
}

function AllTable({ rows }: { rows: AwsResource[] }) {
  if (rows.length === 0)
    return <EmptyState title="No resources found (tag:GetResources permission may be missing)" />;
  return (
    <table className="w-full">
      <thead>
        <tr>
          <Th>Service</Th>
          <Th>Type</Th>
          <Th>Resource</Th>
          <Th>Region</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.arn} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
            <Td>
              <span className="font-medium text-white/85">{r.service}</span>
            </Td>
            <Td>{r.type || "—"}</Td>
            <Td>
              <span title={r.arn}>{r.name || r.id}</span>
            </Td>
            <Td>{r.region}</Td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Ec2Table({ rows }: { rows: Ec2Instance[] }) {
  if (rows.length === 0) return <EmptyState title="No EC2 instances found" />;
  return (
    <table className="w-full">
      <thead>
        <tr>
          <Th>Instance</Th>
          <Th>Type</Th>
          <Th>State</Th>
          <Th>Region</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.instance_id} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
            <Td>
              <span className="font-medium text-white/85">{r.name || r.instance_id}</span>
              <span className="ml-2 text-xs text-white/30">{r.instance_id}</span>
            </Td>
            <Td>{r.instance_type}</Td>
            <Td>
              <StateBadge state={r.state} />
            </Td>
            <Td>{r.region}</Td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function S3Table({ rows }: { rows: S3Bucket[] }) {
  if (rows.length === 0) return <EmptyState title="No S3 buckets found" />;
  return (
    <table className="w-full">
      <thead>
        <tr>
          <Th>Bucket</Th>
          <Th>Region</Th>
          <Th>Access</Th>
          <Th>Size</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.bucket} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
            <Td>{r.bucket}</Td>
            <Td>{r.region}</Td>
            <Td>
              {r.public ? (
                <StateBadge state="terminated" />
              ) : (
                <span className="text-xs text-white/40">private</span>
              )}
            </Td>
            <Td>{r.size_gb != null ? `${r.size_gb} GB` : "—"}</Td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function RdsTable({ rows }: { rows: RdsInstance[] }) {
  if (rows.length === 0) return <EmptyState title="No RDS instances found" />;
  return (
    <table className="w-full">
      <thead>
        <tr>
          <Th>Instance</Th>
          <Th>Engine</Th>
          <Th>Status</Th>
          <Th>Class</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.db_instance_id} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
            <Td>{r.db_instance_id}</Td>
            <Td>{r.engine}</Td>
            <Td>
              <StateBadge state={r.status} />
            </Td>
            <Td>{r.instance_class ?? "—"}</Td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function LambdaTable({ rows }: { rows: LambdaFunction[] }) {
  if (rows.length === 0) return <EmptyState title="No Lambda functions found" />;
  return (
    <table className="w-full">
      <thead>
        <tr>
          <Th>Function</Th>
          <Th>Runtime</Th>
          <Th>Memory</Th>
          <Th>Invocations (24h)</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.function_name} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
            <Td>{r.function_name}</Td>
            <Td>{r.runtime}</Td>
            <Td>{r.memory_mb ? `${r.memory_mb} MB` : "—"}</Td>
            <Td>{r.invocations_24h != null ? r.invocations_24h.toLocaleString() : "—"}</Td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

