# CloudLens — Agentic Cloud Operations Platform

"Claude Code for your cloud." Companies plug in AWS credentials; a multi-agent system monitors resources, audits security, predicts costs, and executes deployments behind human-approval guardrails.

## Stack

- **Backend**: Python 3.11, FastAPI (async), LangGraph (agent orchestration), Groq LLM (primary) with Azure OpenAI gpt-4.1-mini fallback, boto3 for AWS. Deployed on **Render free tier** (512MB RAM, ephemeral disk, sleeps after idle — design for cold starts, no heavy deps like torch/scipy).
- **Frontend**: Next.js 15 (App Router), TypeScript, Tailwind CSS, Recharts. Deployed on **Vercel**.
- **DB**: Postgres via `DATABASE_URL` env (Neon/Supabase free tier) for production; SQLite fallback for local dev when `DATABASE_URL` unset. Use SQLAlchemy 2.x async.

## Directory layout

```
Readme.md
cloudlens/
  backend/
    app/
      main.py               # FastAPI app factory, CORS, middleware, routers
      config.py             # pydantic-settings, all env vars
      db.py                 # SQLAlchemy async engine, models, session
      auth.py               # JWT auth (register/login), password hashing
      credentials.py        # Fernet-encrypted AWS credential storage
      guardrails.py         # permission tiers, prompt-injection screen, approval gate
      audit.py              # audit log writer + query
      cache.py              # TTL cache for AWS reads
      llm.py                # provider abstraction: Groq primary, Azure OpenAI fallback on 429/5xx
      memory.py             # memory layer: LangGraph checkpointer + long-term findings store
      aws/
        client.py           # boto3 session per-tenant from decrypted creds, demo-mode fake data
        tools.py            # all AWS tool functions (typed, docstringed)
      agents/
        graph.py            # LangGraph supervisor graph wiring all agents
        supervisor.py       # routes user intent to specialist agents
        cost_analyst.py     # Cost Explorer queries, spend breakdown
        forecaster.py       # cost prediction (linear trend + moving average, pure python/numpy)
        resource_monitor.py # EC2/S3/RDS/Lambda inventory, CloudWatch metrics
        security_auditor.py # IAM audit, public S3, open security groups
        deploy_operator.py  # EXECUTE-tier ops (start/stop EC2, scale ASG) — approval-gated
      a2a/
        server.py           # A2A protocol: agent cards + JSON-RPC message/send per agent
        client.py           # A2A client used by supervisor to delegate
      mcp_server.py         # FastMCP server exposing AWS tools at /mcp (streamable HTTP)
      routers/
        auth.py, chat.py, costs.py, resources.py, security.py,
        approvals.py, audit.py, credentials.py, health.py
    tests/                  # pytest: guardrails, auth, forecaster, demo-mode e2e
    requirements.txt
    render.yaml
    .env.example
    README.md
  frontend/
    (Next.js app — see Frontend section)
```

## Agents (LangGraph)

Supervisor pattern. Supervisor receives user message, classifies intent, delegates to specialists **via the A2A client** (agent-to-agent protocol over local HTTP routes — real A2A shape, no extra infra). Each specialist is a LangGraph ReAct-style agent with its own tool subset.

| Agent | Tools | Tier |
|---|---|---|
| supervisor | delegate_to(agent, task) via A2A | — |
| cost_analyst | get_cost_summary, get_cost_by_service, get_cost_by_tag | READ |
| forecaster | get_daily_costs, forecast_costs | READ |
| resource_monitor | list_ec2, list_s3, list_rds, list_lambda, get_cloudwatch_metrics | READ |
| security_auditor | audit_iam_users, find_public_buckets, find_open_security_groups | READ |
| deploy_operator | start_ec2, stop_ec2, scale_asg | EXECUTE |

## Guardrails (non-negotiable, enterprise requirement)

1. **Permission tiers**: every tool tagged READ / PLAN / EXECUTE. READ+PLAN auto-run. EXECUTE tools NEVER run directly — they create an approval record and pause the graph via LangGraph `interrupt()`. Human approves/rejects in UI → graph resumes.
2. **Read-only IAM by default**: README documents the minimal IAM policy (ViewOnlyAccess + ce:Get*). Execute actions need a separate opt-in policy.
3. **Prompt-injection screen**: user input and tool outputs pass a lightweight heuristic filter (instruction-override patterns, e.g. "ignore previous instructions", role hijack, exfil URLs). Flagged content is wrapped/neutralized, never silently dropped; incident logged to audit.
4. **Audit log**: every tool call → DB row: user_id, agent, tool, args (secrets redacted), result status, latency_ms, tokens used, timestamp. Queryable via API.
5. **Auth**: JWT (HS256, `SECRET_KEY` env), passlib pbkdf2_sha256 password hashing. All routes except /auth/*, /healthz, /.well-known/* require Bearer token.
6. **Credentials at rest**: AWS keys Fernet-encrypted with `ENCRYPTION_KEY` env. Never returned by API (only last-4 of access key id). Never logged.
7. **Rate limiting**: slowapi — 5/min on auth routes, 20/min on /chat, 60/min elsewhere.
8. **CORS**: locked to `FRONTEND_ORIGIN` env.
9. **LLM output constraints**: agents cannot fabricate tool results; max 8 agent-loop iterations per request (runaway guard); per-request token budget cap.

## Latency

- SSE streaming on /chat (token-level where possible, at minimum step-level events: agent_started, tool_called, tool_result, message_delta, approval_required, done).
- TTL cache (in-memory dict, 5 min) on AWS read calls keyed by (tenant, tool, args-hash).
- boto3 calls wrapped in `asyncio.to_thread` (aioboto3 too heavy for 512MB).
- Groq = fastest inference free tier; fallback only on 429/5xx.

## Memory layer

- **Short-term / conversational**: LangGraph checkpointer — `AsyncPostgresSaver` when DATABASE_URL set, `AsyncSqliteSaver` locally. thread_id per conversation, persisted across Render restarts (Postgres).
- **Long-term**: `findings` table — agents write durable observations (e.g. "prod-db RDS is 40% of spend", "bucket X is public") with kind/severity/summary. Supervisor prepends relevant recent findings (simple recency + keyword match — no embeddings, keeps deps light) to context each turn.
- **User preferences**: key-value per user (default region, cost alert threshold) injected into system prompt.

## Demo mode

If a tenant has no AWS credentials stored, `aws/client.py` returns realistic generated fake data (deterministic seed: ~12 EC2, 8 S3 buckets incl. 1 public, 90 days of daily costs with trend+weekly seasonality, 2 IAM findings). Whole product demoable with zero AWS account. Response metadata flags `"demo": true`.

## A2A protocol surface

- `GET /.well-known/agent-card.json` — platform card listing all agents.
- `GET /a2a/{agent}/card` — per-agent card (name, description, skills, input/output modes).
- `POST /a2a/{agent}` — JSON-RPC 2.0 `message/send` → task result. Auth: same JWT.
Supervisor uses these routes internally via httpx (loopback) — external systems can also call any specialist directly.

## MCP surface

FastMCP server mounted at `/mcp` (streamable HTTP), exposing the READ-tier AWS tools. Lets Claude Code / any MCP client plug into a tenant's cloud (JWT via header). EXECUTE tools are NOT exposed over MCP.

## REST API contract (frontend builds against exactly this)

All under `/api/v1`, JSON, Bearer JWT unless noted.

- `POST /auth/register {email, password}` → `{token}` (no auth)
- `POST /auth/login {email, password}` → `{token}` (no auth)
- `GET /me` → `{email, created_at, has_aws_credentials, demo_mode}`
- `PUT /credentials {access_key_id, secret_access_key, region}` → `{ok, last4}`
- `DELETE /credentials` → `{ok}`
- `POST /chat {message, thread_id?}` → SSE stream. Events: `{type: agent_started|tool_called|tool_result|message_delta|approval_required|done|error, ...}`. `done` carries `{thread_id, usage:{tokens, latency_ms}}`
- `GET /threads` → `[{thread_id, title, updated_at}]`
- `GET /costs/summary?days=30` → `{total, currency, by_service:[{service, amount}], daily:[{date, amount}], demo}`
- `GET /costs/forecast?days=30` → `{forecast:[{date, amount, lower, upper}], method, demo}`
- `GET /resources` → `{ec2:[...], s3:[...], rds:[...], lambda:[...], demo}`
- `GET /security/findings` → `[{id, severity, kind, resource, summary, detected_at}]`
- `GET /approvals` → `[{id, action, params, requested_by_agent, reason, status, created_at}]`
- `POST /approvals/{id}/decide {decision: "approve"|"reject", note?}` → `{ok, status}` (resumes paused graph)
- `GET /audit?limit=100` → `[{ts, agent, tool, status, latency_ms, tokens}]`
- `GET /healthz` → `{ok: true}` (no auth)

## Frontend (Next.js on Vercel)

Env: `NEXT_PUBLIC_API_URL`. Design: dark, premium developer-tool aesthetic (think Vercel/Datadog quality — NOT generic bootstrap). Pages:

1. `/login`, `/register`
2. `/` **Overview**: spend stat tiles (MTD total, forecast EOM, delta %), daily cost area chart + forecast band, top-5 services bar, security findings count by severity, demo-mode banner.
3. `/chat` **Agent console**: streaming chat, visible agent/tool activity timeline (which agent ran, which tools, latencies), approval-required cards inline with approve/reject buttons, thread history sidebar.
4. `/resources`: tabbed inventory tables (EC2/S3/RDS/Lambda) with state badges.
5. `/security`: findings list, severity-colored.
6. `/approvals`: pending queue + history.
7. `/audit`: audit trail table.
8. `/settings`: AWS credential form (shows last4 only), delete creds, region select.

Auth: JWT in localStorage, fetch wrapper adds Bearer, 401 → redirect /login. SSE via fetch ReadableStream (POST — EventSource can't POST).

## Deployment

- `backend/render.yaml`: python web service, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check /healthz, env vars listed (sync:false).
- Frontend: standard Vercel Next.js — set `NEXT_PUBLIC_API_URL`.
- README: setup steps, IAM read-only policy JSON, Neon DB setup, env var table, architecture diagram (mermaid).

## Env vars (backend)

`SECRET_KEY`, `ENCRYPTION_KEY` (Fernet), `DATABASE_URL` (optional→sqlite), `GROQ_API_KEY`, `GROQ_MODEL` (default llama-3.3-70b-versatile), `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` (gpt-4.1-mini, optional fallback), `FRONTEND_ORIGIN`, `DEMO_SEED` (optional).

## Testing

pytest + httpx AsyncClient, demo mode, fake LLM (deterministic stub injected via llm.py seam — tests never call real APIs): auth flow, credentials encryption roundtrip, guardrail tier enforcement (EXECUTE tool blocked without approval), prompt-injection screen, forecaster math, /chat SSE happy path, approval resume flow.
