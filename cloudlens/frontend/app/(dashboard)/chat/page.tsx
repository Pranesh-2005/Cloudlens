"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ChevronDown, Plus, Send, Trash2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { api, ApiError, Approval, ChatEvent, streamChat, Thread } from "@/lib/api";
import { Button, EmptyState, PageHeader, Skeleton } from "@/components/ui";

type TimelineItem =
  | { kind: "agent_started"; agent: string }
  | { kind: "tool_called"; agent: string; tool: string; args?: Record<string, unknown> }
  | { kind: "tool_result"; agent: string; tool: string; status?: string; latency_ms?: number };

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timeline: TimelineItem[];
  approval?: Approval;
  approvalDecision?: "approve" | "reject";
  error?: string;
  streaming?: boolean;
}

function uid() {
  return Math.random().toString(36).slice(2);
}

export default function ChatPage() {
  const [threads, setThreads] = useState<Thread[] | null>(null);
  const [threadId, setThreadId] = useState<string | undefined>(undefined);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  function loadThreads() {
    api.threads().then(setThreads).catch(() => setThreads([]));
  }

  useEffect(loadThreads, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  function updateLast(fn: (m: ChatMessage) => ChatMessage) {
    setMessages((prev) => {
      const next = [...prev];
      const last = next[next.length - 1];
      if (last) next[next.length - 1] = fn(last);
      return next;
    });
  }

  function applyEvent(assistantId: string, ev: ChatEvent) {
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== assistantId) return m;
        switch (ev.type) {
          case "agent_started":
            return { ...m, timeline: [...m.timeline, { kind: "agent_started", agent: ev.agent }] };
          case "tool_called":
            return {
              ...m,
              timeline: [
                ...m.timeline,
                { kind: "tool_called", agent: ev.agent, tool: ev.tool, args: ev.args },
              ],
            };
          case "tool_result":
            return {
              ...m,
              timeline: [
                ...m.timeline,
                {
                  kind: "tool_result",
                  agent: ev.agent,
                  tool: ev.tool,
                  status: ev.status,
                  latency_ms: ev.latency_ms,
                },
              ],
            };
          case "message_delta":
            return { ...m, content: m.content + ev.content };
          case "approval_required":
            return {
              ...m,
              approval: {
                id: ev.approval_id,
                action: ev.action,
                params: ev.params,
                requested_by_agent: ev.agent ?? "",
                reason: ev.reason,
                status: "pending" as const,
                created_at: new Date().toISOString(),
              },
            };
          case "done":
            return { ...m, streaming: false };
          case "error":
            return { ...m, streaming: false, error: ev.error };
          default:
            return m;
        }
      })
    );
  }

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);

    const userMsg: ChatMessage = { id: uid(), role: "user", content: text, timeline: [] };
    const assistantId = uid();
    const assistantMsg: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      timeline: [],
      streaming: true,
    };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);

    try {
      for await (const ev of streamChat(text, threadId)) {
        if (ev.type === "done") {
          setThreadId(ev.thread_id);
        }
        applyEvent(assistantId, ev);
      }
      loadThreads();
    } catch (err) {
      applyEvent(assistantId, {
        type: "error",
        error: err instanceof ApiError ? err.message : "Connection lost",
      });
    } finally {
      setSending(false);
      updateLast((m) => (m.id === assistantId ? { ...m, streaming: false } : m));
    }
  }

  async function decide(assistantId: string, approval: Approval, decision: "approve" | "reject") {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === assistantId ? { ...m, approvalDecision: decision === "approve" ? "approve" : "reject" } : m
      )
    );
    try {
      await api.decideApproval(approval.id, decision);
    } catch {
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, approvalDecision: undefined } : m))
      );
    }
  }

  function newThread() {
    setThreadId(undefined);
    setMessages([]);
  }

  function openThread(id: string) {
    setThreadId(id);
    setMessages([]);
    api
      .threadMessages(id)
      .then((history) =>
        setMessages(
          history.map((h) => ({ id: uid(), role: h.role, content: h.content, timeline: [] }))
        )
      )
      .catch(() => {});
  }

  async function removeThread(id: string) {
    try {
      await api.deleteThread(id);
    } catch {
      return;
    }
    if (threadId === id) newThread();
    loadThreads();
  }

  return (
    <div className="flex h-[calc(100vh-3rem)] gap-4">
      <aside className="flex w-56 shrink-0 flex-col border-r border-white/8 pr-3">
        <Button variant="secondary" onClick={newThread} className="mb-3 w-full justify-start">
          <Plus size={14} /> New chat
        </Button>
        <div className="flex-1 space-y-1 overflow-y-auto">
          {threads === null ? (
            <Skeleton className="h-8" />
          ) : threads.length === 0 ? (
            <p className="px-2 text-xs text-white/30">No previous threads</p>
          ) : (
            threads.map((t) => (
              <div
                key={t.thread_id}
                className={`group flex w-full items-center rounded-lg transition-colors ${
                  threadId === t.thread_id
                    ? "bg-cyan-400/10 text-cyan-300"
                    : "text-white/50 hover:bg-white/5 hover:text-white/80"
                }`}
              >
                <button
                  onClick={() => openThread(t.thread_id)}
                  className="min-w-0 flex-1 truncate px-2.5 py-2 text-left text-sm"
                >
                  {t.title || "Untitled"}
                </button>
                <button
                  onClick={() => removeThread(t.thread_id)}
                  title="Delete chat"
                  className="mr-1.5 hidden shrink-0 rounded p-1 text-white/30 hover:bg-rose-500/15 hover:text-rose-300 group-hover:block"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>
      </aside>

      <div className="flex flex-1 flex-col">
        <PageHeader title="Agent console" description="Ask about spend, resources, or security. Execute actions require approval." />

        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto pr-1">
          {messages.length === 0 ? (
            <EmptyState
              title="Start a conversation"
              description='Try "what is my current AWS spend?" or "are there any public S3 buckets?"'
            />
          ) : (
            messages.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className="flex justify-end">
                  <div className="max-w-lg rounded-xl rounded-br-sm bg-cyan-400/10 px-4 py-2.5 text-sm text-cyan-100">
                    {m.content}
                  </div>
                </div>
              ) : (
                <AssistantBubble key={m.id} message={m} onDecide={decide} />
              )
            )
          )}
        </div>

        <form onSubmit={send} className="mt-4 flex items-center gap-2 border-t border-white/8 pt-4">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask CloudLens…"
            disabled={sending}
            className="flex-1 rounded-lg border border-white/10 bg-white/[0.03] px-3.5 py-2.5 text-sm text-white/90 placeholder:text-white/25 outline-none focus:border-cyan-400/50 focus:ring-1 focus:ring-cyan-400/30 disabled:opacity-50"
          />
          <Button type="submit" disabled={sending || !input.trim()}>
            <Send size={14} />
          </Button>
        </form>
      </div>
    </div>
  );
}

function AssistantBubble({
  message,
  onDecide,
}: {
  message: ChatMessage;
  onDecide: (assistantId: string, approval: Approval, decision: "approve" | "reject") => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex flex-col gap-2">
      {message.timeline.length > 0 && (
        <div className="max-w-lg">
          <button
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-1.5 text-xs text-white/35 hover:text-white/60"
          >
            <ChevronDown size={12} className={`transition-transform ${open ? "rotate-180" : ""}`} />
            {message.streaming ? "Working…" : `${message.timeline.length} steps`}
          </button>
          {open && (
            <ol className="mt-1.5 space-y-1 border-l border-white/8 pl-3">
              {message.timeline.map((item, i) => (
                <li key={i} className="text-xs text-white/45">
                  {item.kind === "agent_started" && (
                    <span className="text-cyan-400/80">agent</span>
                  )}{" "}
                  {item.kind === "agent_started" && item.agent}
                  {item.kind === "tool_called" && (
                    <>
                      <span className="text-white/30">{item.agent}</span>{" "}
                      called <span className="font-mono text-white/70">{item.tool}</span>
                    </>
                  )}
                  {item.kind === "tool_result" && (
                    <>
                      <span className="font-mono text-white/70">{item.tool}</span>{" "}
                      <span
                        className={item.status === "error" ? "text-rose-400" : "text-emerald-400/80"}
                      >
                        {item.status ?? "ok"}
                      </span>
                      {item.latency_ms !== undefined && (
                        <span className="text-white/30"> · {item.latency_ms}ms</span>
                      )}
                    </>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      {message.content && (
        <div className="chat-markdown max-w-lg rounded-xl rounded-bl-sm border border-white/8 bg-white/[0.02] px-4 py-2.5 text-sm text-white/85">
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>
      )}

      {message.streaming && !message.content && (
        <div className="flex items-center gap-1 px-1 text-white/30">
          <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-white/40" />
          <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-white/40 [animation-delay:0.2s]" />
          <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-white/40 [animation-delay:0.4s]" />
        </div>
      )}

      {message.error && (
        <p className="max-w-lg rounded-lg border border-rose-500/25 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">
          {message.error}
        </p>
      )}

      {message.approval && (
        <div className="max-w-lg rounded-xl border border-amber-500/25 bg-amber-500/[0.06] p-4">
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-300">
              Approval required
            </span>
            <span className="text-xs text-white/35">{message.approval.action}</span>
          </div>
          <p className="mt-1.5 text-sm text-white/70">{message.approval.reason}</p>
          {message.approval.params && Object.keys(message.approval.params).length > 0 && (
            <pre className="mt-2 overflow-x-auto rounded-md bg-black/30 px-3 py-2 text-xs text-white/45">
              {JSON.stringify(message.approval.params, null, 2)}
            </pre>
          )}
          {message.approvalDecision ? (
            <p className="mt-3 text-xs text-white/40">
              You {message.approvalDecision === "approve" ? "approved" : "rejected"} this action.
            </p>
          ) : (
            <div className="mt-3 flex gap-2">
              <Button
                variant="secondary"
                onClick={() => onDecide(message.id, message.approval!, "reject")}
              >
                Reject
              </Button>
              <Button variant="primary" onClick={() => onDecide(message.id, message.approval!, "approve")}>
                Approve
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
