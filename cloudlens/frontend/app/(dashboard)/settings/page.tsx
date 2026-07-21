"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, ApiError, MeResponse } from "@/lib/api";
import { Button, Card, Input, PageHeader, Skeleton } from "@/components/ui";

const REGIONS = [
  "us-east-1",
  "us-east-2",
  "us-west-1",
  "us-west-2",
  "eu-west-1",
  "eu-central-1",
  "ap-southeast-1",
  "ap-southeast-2",
  "ap-south-1",
];

export default function SettingsPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [accessKeyId, setAccessKeyId] = useState("");
  const [secretAccessKey, setSecretAccessKey] = useState("");
  const [region, setRegion] = useState(REGIONS[0]);
  const [last4, setLast4] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    api
      .me()
      .then(setMe)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load account"))
      .finally(() => setLoading(false));
  }, []);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setSaving(true);
    try {
      const res = await api.putCredentials(accessKeyId, secretAccessKey, region);
      setLast4(res.last4);
      setAccessKeyId("");
      setSecretAccessKey("");
      setSuccess("Credentials saved.");
      setMe((prev) => (prev ? { ...prev, has_aws_credentials: true } : prev));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save credentials");
    } finally {
      setSaving(false);
    }
  }

  async function onDelete() {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setDeleting(true);
    setError(null);
    setSuccess(null);
    try {
      await api.deleteCredentials();
      setLast4(null);
      setMe((prev) => (prev ? { ...prev, has_aws_credentials: false } : prev));
      setSuccess("Credentials removed. Demo mode is now active.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete credentials");
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  }

  return (
    <div className="max-w-xl">
      <PageHeader title="Settings" description="Manage your account and AWS credentials." />

      {loading ? (
        <Skeleton className="h-40" />
      ) : (
        <Card className="mb-6">
          <h2 className="text-sm font-medium text-white/70">Account</h2>
          <div className="mt-3 space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-white/40">Email</span>
              <span className="text-white/85">{me?.email}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-white/40">Created</span>
              <span className="text-white/85">
                {me?.created_at ? new Date(me.created_at).toLocaleDateString() : "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-white/40">Mode</span>
              <span className="text-white/85">{me?.demo_mode ? "Demo" : "Live"}</span>
            </div>
          </div>
        </Card>
      )}

      <Card>
        <h2 className="text-sm font-medium text-white/70">AWS credentials</h2>
        <p className="mt-1 text-xs text-white/40">
          Stored Fernet-encrypted server-side. Only the last 4 characters of the access key are
          ever shown here.
        </p>

        {(me?.has_aws_credentials || last4) && (
          <div className="mt-4 flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
            <span className="text-sm text-white/70">
              Access key ending in{" "}
              <span className="font-mono text-white/90">•••• {last4 ?? "····"}</span>
            </span>
            <Button
              variant={confirmDelete ? "danger" : "secondary"}
              disabled={deleting}
              onClick={onDelete}
            >
              {deleting ? "Removing…" : confirmDelete ? "Confirm remove" : "Remove"}
            </Button>
          </div>
        )}

        <form onSubmit={onSave} className="mt-4 space-y-3">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-white/50">
              Access key ID
            </label>
            <Input
              required
              value={accessKeyId}
              onChange={(e) => setAccessKeyId(e.target.value)}
              placeholder="AKIA…"
              autoComplete="off"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-white/50">
              Secret access key
            </label>
            <Input
              type="password"
              required
              value={secretAccessKey}
              onChange={(e) => setSecretAccessKey(e.target.value)}
              placeholder="••••••••••••••••••••••••"
              autoComplete="off"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-white/50">Region</label>
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white/90 outline-none focus:border-cyan-400/50 focus:ring-1 focus:ring-cyan-400/30"
            >
              {REGIONS.map((r) => (
                <option key={r} value={r} className="bg-[#0d0f14]">
                  {r}
                </option>
              ))}
            </select>
          </div>

          {error && (
            <p className="rounded-lg border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
              {error}
            </p>
          )}
          {success && (
            <p className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
              {success}
            </p>
          )}

          <Button type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save credentials"}
          </Button>
        </form>
      </Card>
    </div>
  );
}
