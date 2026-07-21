// Small shared UI primitives used across pages. Kept in one file on purpose —
// none of these carry enough logic to earn their own module.
"use client";

import { ReactNode } from "react";
import type { Severity } from "@/lib/api";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-white/8 bg-white/[0.02] p-5 ${className}`}
    >
      {children}
    </div>
  );
}

export function StatTile({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "default" | "up" | "down";
}) {
  const subColor =
    tone === "up"
      ? "text-rose-400"
      : tone === "down"
        ? "text-emerald-400"
        : "text-white/40";
  return (
    <Card>
      <div className="text-xs font-medium uppercase tracking-wide text-white/40">
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight text-white/90">
        {value}
      </div>
      {sub && <div className={`mt-1 text-xs ${subColor}`}>{sub}</div>}
    </Card>
  );
}

export function DemoBanner({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div className="flex items-center gap-2 rounded-lg border border-cyan-400/20 bg-cyan-400/[0.06] px-4 py-2.5 text-sm text-cyan-300">
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-cyan-400" />
      Demo mode — showing generated sample data. Connect AWS credentials in{" "}
      <a href="/settings" className="underline underline-offset-2 hover:text-cyan-200">
        Settings
      </a>{" "}
      to see your real account.
    </div>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-white/10 py-16 text-center">
      <div className="text-sm font-medium text-white/60">{title}</div>
      {description && (
        <div className="mt-1 max-w-sm text-xs text-white/35">{description}</div>
      )}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse-soft rounded-md bg-white/[0.06] ${className}`}
    />
  );
}

const severityStyles: Record<Severity, string> = {
  critical: "bg-rose-500/15 text-rose-300 border-rose-500/25",
  high: "bg-orange-500/15 text-orange-300 border-orange-500/25",
  medium: "bg-amber-500/15 text-amber-300 border-amber-500/25",
  low: "bg-sky-500/15 text-sky-300 border-sky-500/25",
  info: "bg-white/10 text-white/50 border-white/15",
};

export function SeverityBadge({ severity }: { severity: string }) {
  const style = severityStyles[severity as Severity] ?? severityStyles.info;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize ${style}`}
    >
      {severity}
    </span>
  );
}

const stateStyles: Record<string, string> = {
  running: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
  available: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
  active: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
  stopped: "bg-white/10 text-white/45 border-white/15",
  stopping: "bg-amber-500/15 text-amber-300 border-amber-500/25",
  pending: "bg-amber-500/15 text-amber-300 border-amber-500/25",
  terminated: "bg-rose-500/15 text-rose-300 border-rose-500/25",
};

export function StateBadge({ state }: { state: string }) {
  const style = stateStyles[state?.toLowerCase()] ?? stateStyles.stopped;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium capitalize ${style}`}
    >
      {state}
    </span>
  );
}

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled,
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  const base =
    "inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40";
  const styles: Record<string, string> = {
    primary: "bg-cyan-400 text-black hover:bg-cyan-300",
    secondary: "border border-white/12 text-white/80 hover:bg-white/5",
    danger: "bg-rose-500/90 text-white hover:bg-rose-500",
    ghost: "text-white/60 hover:text-white/90 hover:bg-white/5",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${base} ${styles[variant]} ${className}`}
    >
      {children}
    </button>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { className = "", ...rest } = props;
  return (
    <input
      {...rest}
      className={`w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white/90 placeholder:text-white/25 outline-none focus:border-cyan-400/50 focus:ring-1 focus:ring-cyan-400/30 ${className}`}
    />
  );
}

export function PageHeader({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="mb-6">
      <h1 className="text-xl font-semibold tracking-tight text-white/90">
        {title}
      </h1>
      {description && (
        <p className="mt-1 text-sm text-white/40">{description}</p>
      )}
    </div>
  );
}
