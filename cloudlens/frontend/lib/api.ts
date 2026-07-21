// Typed API client for CloudLens backend. Matches REST contract in SPEC.md exactly.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

const TOKEN_KEY = "cloudlens_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function redirectToLogin() {
  clearToken();
  if (typeof window !== "undefined") {
    window.location.href = "/login";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (res.status === 401) {
    redirectToLogin();
    throw new ApiError(401, "Unauthorized");
  }

  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body?.detail || body?.message || message;
    } catch {
      // ignore non-json error body
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ---------- Types (contract) ----------

export interface AuthResponse {
  token: string;
}

export interface MeResponse {
  email: string;
  created_at: string;
  has_aws_credentials: boolean;
  demo_mode: boolean;
}

export interface CredentialsPutResponse {
  ok: boolean;
  last4: string;
}

export interface OkResponse {
  ok: boolean;
}

export interface Thread {
  thread_id: string;
  title: string;
  updated_at: string;
}

export interface ThreadMessage {
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface CostsSummary {
  total: number;
  currency: string;
  by_service: { service: string; amount: number }[];
  daily: { date: string; amount: number }[];
  demo: boolean;
}

export interface CostsForecast {
  forecast: { date: string; amount: number; lower: number; upper: number }[];
  method: string;
  demo: boolean;
}

// Resource item shapes aren't pinned down further by SPEC.md beyond the
// top-level {ec2,s3,rds,lambda,demo} envelope. We model each with the
// common fields AWS inventories expose and keep components defensive
// (optional chaining) against any that are absent.
export interface Ec2Instance {
  instance_id: string;
  name?: string;
  instance_type: string;
  state: string;
  region: string;
  launched_at?: string;
}

export interface S3Bucket {
  bucket: string;
  region: string;
  public: boolean;
  size_gb?: number | null;
  objects?: number | null;
}

export interface RdsInstance {
  db_instance_id: string;
  engine: string;
  status: string;
  instance_class?: string;
  multi_az?: boolean;
}

export interface LambdaFunction {
  function_name: string;
  runtime: string;
  memory_mb?: number | null;
  invocations_24h?: number | null;
}

export interface AwsResource {
  arn: string;
  service: string;
  type: string;
  id: string;
  region: string;
  name: string;
}

export interface ResourcesResponse {
  all: AwsResource[];
  ec2: Ec2Instance[];
  s3: S3Bucket[];
  rds: RdsInstance[];
  lambda: LambdaFunction[];
  demo: boolean;
}

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export interface SecurityFinding {
  id: string;
  severity: Severity;
  kind: string;
  resource: string;
  summary: string;
  detected_at: string;
}

export type ApprovalStatus = "pending" | "approved" | "rejected";

export interface Approval {
  id: string;
  action: string;
  params: Record<string, unknown>;
  requested_by_agent: string;
  reason: string;
  status: ApprovalStatus;
  created_at: string;
}

export interface AuditEntry {
  ts: string;
  agent: string;
  tool: string;
  status: string;
  latency_ms: number;
  tokens: number;
}

// ---------- SSE chat event types ----------

export type ChatEvent =
  | { type: "agent_started"; agent: string }
  | { type: "tool_called"; agent: string; tool: string; args?: Record<string, unknown> }
  | {
      type: "tool_result";
      agent: string;
      tool: string;
      status?: string;
      latency_ms?: number;
      result?: unknown;
    }
  | { type: "message_delta"; agent?: string; content: string }
  | {
      type: "approval_required";
      agent?: string;
      approval_id: string;
      action: string;
      params: Record<string, unknown>;
      reason: string;
    }
  | {
      type: "done";
      thread_id: string;
      usage: { tokens: number; latency_ms: number };
    }
  | { type: "error"; error: string };

// ---------- API calls ----------

export const api = {
  register: (email: string, password: string) =>
    request<AuthResponse>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    request<AuthResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<MeResponse>("/api/v1/me"),

  putCredentials: (access_key_id: string, secret_access_key: string, region: string) =>
    request<CredentialsPutResponse>("/api/v1/credentials", {
      method: "PUT",
      body: JSON.stringify({ access_key_id, secret_access_key, region }),
    }),

  deleteCredentials: () =>
    request<OkResponse>("/api/v1/credentials", { method: "DELETE" }),

  threads: () => request<Thread[]>("/api/v1/threads"),

  threadMessages: (thread_id: string) =>
    request<ThreadMessage[]>(`/api/v1/threads/${thread_id}/messages`),

  deleteThread: (thread_id: string) =>
    request<OkResponse>(`/api/v1/threads/${thread_id}`, { method: "DELETE" }),

  costsSummary: (days = 30) =>
    request<CostsSummary>(`/api/v1/costs/summary?days=${days}`),

  costsForecast: (days = 30) =>
    request<CostsForecast>(`/api/v1/costs/forecast?days=${days}`),

  resources: () => request<ResourcesResponse>("/api/v1/resources"),

  securityFindings: () => request<SecurityFinding[]>("/api/v1/security/findings"),

  approvals: () => request<Approval[]>("/api/v1/approvals"),

  decideApproval: (id: string, decision: "approve" | "reject", note?: string) =>
    request<{ ok: boolean; status: string }>(`/api/v1/approvals/${id}/decide`, {
      method: "POST",
      body: JSON.stringify({ decision, note }),
    }),

  audit: (limit = 100) => request<AuditEntry[]>(`/api/v1/audit?limit=${limit}`),
};

// ---------- SSE streaming chat ----------
// EventSource can't POST, so we stream the fetch response body ourselves and
// parse SSE "data: {...}\n\n" frames by hand.
export async function* streamChat(
  message: string,
  thread_id: string | undefined,
  signal?: AbortSignal
): AsyncGenerator<ChatEvent> {
  const token = getToken();
  const res = await fetch(`${API_URL}/api/v1/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ message, thread_id }),
    signal,
  });

  if (res.status === 401) {
    redirectToLogin();
    throw new ApiError(401, "Unauthorized");
  }
  if (!res.ok || !res.body) {
    throw new ApiError(res.status, res.statusText || "Chat stream failed");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const dataLines = frame
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).trim());
      if (dataLines.length === 0) continue;
      const raw = dataLines.join("\n");
      try {
        yield JSON.parse(raw) as ChatEvent;
      } catch {
        // ignore malformed frame
      }
    }
  }
}
