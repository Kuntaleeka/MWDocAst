"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, apiStream, type Conversation, type Message } from "@/lib/api";
import { RichText } from "./RichText";

const TOOL_STYLE = {
  ok: "bg-green-600/15 text-green-700 dark:text-green-400",
  rejected: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  error: "bg-red-600/15 text-red-700 dark:text-red-400",
} as const;

const STAGE_LABEL = {
  searching: "Searching this workspace's documents…",
  writing: "Writing…",
  tool: "Running a tool…",
} as const;

// Local view of a message while it streams in.
type LiveMessage = Message & { stage?: keyof typeof STAGE_LABEL };

export function ChatPanel({ workspaceId }: { workspaceId: string }) {
  const base = `/workspaces/${workspaceId}`;
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<LiveMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadConversations = useCallback(() => {
    apiFetch<Conversation[]>(`${base}/conversations`)
      .then(setConversations)
      .catch(() => setError("Could not load chat history."));
  }, [base]);

  useEffect(loadConversations, [loadConversations]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

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
    <div className="flex min-h-[28rem] flex-col gap-4 md:flex-row">
      <aside className="flex flex-col gap-1 md:w-56 md:shrink-0">
        <button
          onClick={newChat}
          className="rounded border border-black/20 px-3 py-1.5 text-left text-sm dark:border-white/20"
        >
          + New chat
        </button>
        <ul className="flex max-h-40 flex-col gap-0.5 overflow-y-auto md:max-h-[26rem]">
          {conversations.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => openConversation(c.id)}
                className={`w-full truncate rounded px-3 py-1.5 text-left text-sm ${
                  c.id === activeId ? "bg-black/10 dark:bg-white/10" : "opacity-80 hover:bg-black/5 dark:hover:bg-white/5"
                }`}
                title={c.title}
              >
                {c.title}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col rounded border border-black/10 dark:border-white/10">
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
          {messages.length === 0 && (
            <p className="m-auto max-w-sm text-center text-sm opacity-60">
              Ask a question about this workspace&apos;s documents. Answers cite their sources, and the
              assistant says so when the documents don&apos;t cover it.
            </p>
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} onRetry={() => retry(m.id)} />
          ))}
          <div ref={bottomRef} />
        </div>
        {error && <p className="px-4 pb-2 text-sm text-red-600">{error}</p>}
        <form onSubmit={send} className="flex gap-2 border-t border-black/10 p-3 dark:border-white/10">
          <textarea
            className="min-h-10 flex-1 resize-none rounded border border-black/20 bg-transparent px-3 py-2 text-sm dark:border-white/20"
            rows={1}
            maxLength={4000}
            placeholder="Ask about your documents…"
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
            className="rounded bg-foreground px-4 text-sm text-background disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </section>
    </div>
  );
}

function MessageBubble({ message: m, onRetry }: { message: LiveMessage; onRetry: () => void }) {
  if (m.role === "user") {
    return (
      <div className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-lg bg-foreground px-3 py-2 text-sm text-background">
        {m.content}
      </div>
    );
  }
  if (m.status === "pending" && !m.content) {
    return (
      <div className="flex flex-col gap-2">
        <ToolBadges tools={m.tools} />
        <div className="animate-pulse text-sm opacity-60">{STAGE_LABEL[m.stage ?? "writing"]}</div>
      </div>
    );
  }
  if (m.status === "failed") {
    return (
      <div className="flex flex-wrap items-center gap-2 text-sm text-red-600">
        <span>{m.error ?? "The answer failed."}</span>
        <button onClick={onRetry} className="underline">
          Retry
        </button>
      </div>
    );
  }
  return (
    <div className="flex max-w-[85%] flex-col gap-2">
      <ToolBadges tools={m.tools} />
      <div className="text-sm leading-relaxed">
        <RichText text={m.content} citations={m.citations} />
        {m.status === "pending" && <span className="ml-0.5 inline-block w-2 animate-pulse">▍</span>}
      </div>
      {m.citations.length > 0 && (
        <ul className="flex flex-col gap-1">
          {m.citations.map((c) => (
            <li key={c.label}>
              <details className="text-xs">
                <summary className="cursor-pointer opacity-80">
                  <span className="mr-1 rounded bg-black/10 px-1 font-mono dark:bg-white/15">{c.label}</span>
                  {c.filename}
                  {c.section && <span className="opacity-70"> § {c.section}</span>}
                </summary>
                <p className="mt-1 whitespace-pre-wrap border-l-2 border-black/20 pl-2 opacity-80 dark:border-white/20">
                  {c.snippet}
                  {c.snippet.length >= 300 && "…"}
                </p>
              </details>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ToolBadges({ tools }: { tools?: Message["tools"] }) {
  if (!tools?.length) return null;
  return (
    <ul className="flex flex-wrap gap-1">
      {tools.map((t, i) => (
        <li
          key={i}
          title={t.error ?? undefined}
          className={`rounded px-1.5 py-0.5 font-mono text-[0.7rem] ${TOOL_STYLE[t.status]}`}
        >
          {t.status === "ok" ? "✓" : t.status === "rejected" ? "⊘" : "✗"} {t.name}
        </li>
      ))}
    </ul>
  );
}
