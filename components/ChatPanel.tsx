"use client";

import {
  ArrowUp,
  Ban,
  Check,
  ChevronDown,
  FileText,
  MessageSquarePlus,
  RotateCw,
  Sparkles,
  TriangleAlert,
  Wrench,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, apiStream, type Citation, type Conversation, type Message } from "@/lib/api";
import { RichText } from "./RichText";
import { cn, Pill, Spinner, type Tone } from "./ui";

const TOOL_TONE: Record<"ok" | "rejected" | "error", Tone> = { ok: "success", rejected: "warning", error: "danger" };
const TOOL_ICON = { ok: Check, rejected: Ban, error: X } as const;

const SUGGESTIONS = [
  "What topics do these documents cover?",
  "Summarize the key policies in three bullets",
  "List my open tasks",
  "Save a task to review these documents by Friday",
];

const STAGE_LABEL = {
  searching: "Searching this workspace's documents…",
  writing: "Writing…",
  tool: "Running a tool…",
} as const;

// Local view of a message while it streams in.
type LiveMessage = Message & { stage?: keyof typeof STAGE_LABEL };

export function ChatPanel({ workspaceId, workspaceName }: { workspaceId: string; workspaceName: string }) {
  const base = `/workspaces/${workspaceId}`;
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<LiveMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const loadConversations = useCallback(() => {
    apiFetch<Conversation[]>(`${base}/conversations`)
      .then(setConversations)
      .catch(() => setError("Could not load chat history."));
  }, [base]);

  useEffect(loadConversations, [loadConversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [draft]);

  async function openConversation(id: string) {
    setActiveId(id);
    setError(null);
    try {
      setMessages(await apiFetch<Message[]>(`${base}/conversations/${id}/messages`));
    } catch {
      setError("Could not load this conversation.");
    }
  }

  function newChat() {
    setActiveId(null);
    setMessages([]);
    setError(null);
  }

  function patch(id: string, update: (m: LiveMessage) => LiveMessage) {
    setMessages((ms) => ms.map((m) => (m.id === id ? update(m) : m)));
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    setError(null);
    setDraft("");
    const now = new Date().toISOString();
    const blank = { error: null, citations: [], tools: [], created_at: now };
    setMessages((m) => [
      ...m,
      { ...blank, id: "tmp-user", role: "user", content: text, status: "done" },
      { ...blank, id: "tmp-assistant", role: "assistant", content: "", status: "pending", stage: "searching" },
    ]);

    let assistantId = "tmp-assistant";
    let conversationId = activeId;
    let saved = false; // has the server stored the question?
    let finished = false;
    try {
      await apiStream(`${base}/chat/stream`, { message: text, conversation_id: activeId }, (ev) => {
        switch (ev.event) {
          case "meta":
            saved = true;
            conversationId = ev.data.conversation_id;
            setMessages((ms) =>
              ms.map((m) =>
                m.id === "tmp-user"
                  ? ev.data.user_message
                  : m.id === "tmp-assistant"
                    ? { ...m, id: ev.data.assistant_message_id }
                    : m,
              ),
            );
            assistantId = ev.data.assistant_message_id;
            if (conversationId !== activeId) {
              setActiveId(conversationId);
              loadConversations();
            }
            break;
          case "status":
            patch(assistantId, (m) => ({ ...m, stage: ev.data.stage }));
            break;
          case "token":
            patch(assistantId, (m) => ({ ...m, content: m.content + ev.data.text }));
            break;
          case "tool":
            patch(assistantId, (m) => ({ ...m, tools: [...(m.tools ?? []), ev.data] }));
            break;
          case "done":
            // The saved message replaces the provisional streamed text (citations validated).
            finished = true;
            patch(assistantId, () => ev.data.message);
            break;
        }
      });
      if (!finished) throw new Error("The connection closed before the answer finished.");
    } catch (err) {
      if (saved && conversationId) {
        // The question is stored server-side; show whatever state the server has.
        await openConversation(conversationId);
      } else {
        // The request never reached the server: put the question back so nothing is lost.
        setMessages((m) => m.filter((x) => !x.id.startsWith("tmp-")));
        setDraft(text);
        setError(err instanceof Error ? err.message : "Could not send the message.");
      }
    } finally {
      setSending(false);
    }
  }

  async function retry(id: string) {
    setMessages((m) => m.map((x) => (x.id === id ? { ...x, status: "pending", error: null } : x)));
    try {
      const updated = await apiFetch<Message>(`${base}/messages/${id}/retry`, { method: "POST" });
      setMessages((m) => m.map((x) => (x.id === id ? updated : x)));
    } catch {
      setMessages((m) =>
        m.map((x) => (x.id === id ? { ...x, status: "failed", error: "Retry failed. Try again." } : x)),
      );
    }
  }

  return (
    <div className="flex h-full min-h-[32rem] gap-4">
      {/* Conversation history */}
      <aside className="card hidden w-60 shrink-0 flex-col gap-2 p-2 lg:flex">
        <button onClick={newChat} className="btn btn-secondary w-full justify-start">
          <MessageSquarePlus className="size-4" aria-hidden /> New chat
        </button>
        <p className="px-2 pt-2 text-[0.7rem] font-medium uppercase tracking-wide text-muted">History</p>
        <ul className="scroll-thin flex flex-1 flex-col gap-0.5 overflow-y-auto">
          {conversations.length === 0 && <li className="px-2 text-xs text-muted">No conversations yet.</li>}
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => openConversation(c.id)}
                title={c.title}
                className={cn(
                  "w-full truncate rounded-md px-2 py-1.5 text-left text-sm transition",
                  c.id === activeId ? "bg-accent-soft font-medium text-accent" : "text-muted hover:bg-subtle hover:text-foreground",
                )}
              >
                {c.title}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="card flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Mobile history picker */}
        <div className="flex items-center gap-2 border-b border-border p-2 lg:hidden">
          <select
            aria-label="Conversation"
            className="input py-1.5"
            value={activeId ?? ""}
            onChange={(e) => (e.target.value ? openConversation(e.target.value) : newChat())}
          >
            <option value="">New chat</option>
            {conversations.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
          <button onClick={newChat} className="btn-icon" aria-label="New chat">
            <MessageSquarePlus className="size-4" />
          </button>
        </div>

        <div className="scroll-thin flex flex-1 flex-col overflow-y-auto">
          {messages.length === 0 ? (
            <div className="m-auto flex max-w-lg flex-col items-center gap-5 px-6 py-10 text-center">
              <div className="flex size-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white shadow-md">
                <Sparkles className="size-6" aria-hidden />
              </div>
              <div className="flex flex-col gap-1.5">
                <h2 className="text-xl font-semibold tracking-tight">Ask about {workspaceName}</h2>
                <p className="text-sm text-muted">
                  Answers come only from this workspace&apos;s documents and cite their sources. If the
                  documents don&apos;t cover it, the assistant says so.
                </p>
              </div>
              <div className="grid w-full gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => {
                      setDraft(q);
                      inputRef.current?.focus();
                    }}
                    className="rounded-xl border border-border bg-card px-3 py-2.5 text-left text-sm text-muted transition hover:border-accent/40 hover:bg-accent-soft hover:text-foreground"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6 md:px-6">
              {messages.map((m) => (
                <MessageRow key={m.id} message={m} onRetry={() => retry(m.id)} />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <div className="border-t border-border p-3 md:p-4">
          <div className="mx-auto w-full max-w-3xl">
            {error && (
              <p className="mb-2 flex items-center gap-2 text-sm text-rose-600">
                <TriangleAlert className="size-4" aria-hidden /> {error}
              </p>
            )}
            <form
              onSubmit={send}
              className="flex items-end gap-2 rounded-2xl border border-border bg-card p-2 pl-4 shadow-sm transition focus-within:border-accent focus-within:ring-4 focus-within:ring-ring"
            >
              <textarea
                ref={inputRef}
                className="max-h-[200px] min-h-6 flex-1 resize-none bg-transparent py-1.5 text-sm outline-none placeholder:text-muted"
                rows={1}
                maxLength={4000}
                placeholder={`Message ${workspaceName}…`}
                aria-label="Message"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    e.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <button
                disabled={sending || !draft.trim()}
                aria-label="Send"
                className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-foreground transition hover:opacity-90 disabled:opacity-40"
              >
                {sending ? <Spinner /> : <ArrowUp className="size-4" />}
              </button>
            </form>
            <p className="mt-1.5 hidden text-center text-[0.7rem] text-muted md:block">
              Enter to send · Shift + Enter for a new line
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

function AssistantAvatar() {
  return (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
      <Sparkles className="size-4" aria-hidden />
    </span>
  );
}

function MessageRow({ message: m, onRetry }: { message: LiveMessage; onRetry: () => void }) {
  if (m.role === "user") {
    return (
      <div className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-sm text-accent-foreground shadow-sm">
        {m.content}
      </div>
    );
  }
  return (
    <div className="flex gap-3">
      <AssistantAvatar />
      <div className="flex min-w-0 flex-1 flex-col gap-2.5 pt-0.5">
        <ToolBadges tools={m.tools} />
        {m.status === "pending" && !m.content && (
          <p className="flex items-center gap-2 text-sm text-muted">
            <Spinner /> {STAGE_LABEL[m.stage ?? "writing"]}
          </p>
        )}
        {m.status === "failed" && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-rose-500/20 bg-rose-500/8 px-3 py-2 text-sm text-rose-700 dark:text-rose-400">
            <TriangleAlert className="size-4 shrink-0" aria-hidden />
            <span className="flex-1">{m.error ?? "The answer failed."}</span>
            <button onClick={onRetry} className="btn btn-secondary px-2.5 py-1 text-xs text-foreground">
              <RotateCw className="size-3.5" aria-hidden /> Retry
            </button>
          </div>
        )}
        {m.content && m.status !== "failed" && (
          <div className="text-sm leading-relaxed">
            <RichText text={m.content} citations={m.citations} />
            {m.status === "pending" && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-accent align-middle" />}
          </div>
        )}
        {m.citations.length > 0 && <Sources citations={m.citations} />}
      </div>
    </div>
  );
}

function Sources({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const shown = citations.find((c) => c.label === open);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-muted">Sources</span>
        {citations.map((c) => (
          <button
            key={c.label}
            onClick={() => setOpen(open === c.label ? null : c.label)}
            aria-expanded={open === c.label}
            className={cn(
              "inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition",
              open === c.label ? "border-accent/40 bg-accent-soft text-accent" : "border-border bg-card text-muted hover:text-foreground",
            )}
          >
            <span className="font-mono font-semibold">{c.label}</span>
            <FileText className="size-3 shrink-0" aria-hidden />
            <span className="truncate">
              {c.filename}
              {c.section && ` · ${c.section}`}
            </span>
            <ChevronDown className={cn("size-3 shrink-0 transition", open === c.label && "rotate-180")} aria-hidden />
          </button>
        ))}
      </div>
      {shown && (
        <blockquote className="rounded-xl border border-border bg-subtle px-3.5 py-2.5 text-xs leading-relaxed text-muted">
          <p className="mb-1 font-medium text-foreground">
            {shown.filename}
            {shown.section && <span className="font-normal text-muted"> § {shown.section}</span>}
          </p>
          <p className="whitespace-pre-wrap">
            {shown.snippet}
            {shown.snippet.length >= 300 && "…"}
          </p>
        </blockquote>
      )}
    </div>
  );
}

function ToolBadges({ tools }: { tools?: Message["tools"] }) {
  if (!tools?.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Wrench className="size-3.5 text-muted" aria-hidden />
      {tools.map((t, i) => {
        const Icon = TOOL_ICON[t.status];
        return (
          <Pill key={i} tone={TOOL_TONE[t.status]} title={t.error ?? undefined} className="font-mono">
            <Icon className="size-3" aria-hidden /> {t.name}
          </Pill>
        );
      })}
    </div>
  );
}
