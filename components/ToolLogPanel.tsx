"use client";

import { Activity, ChevronRight, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, type ToolCall } from "@/lib/api";
import { cn, EmptyState, ErrorNote, Pill, Spinner, type Tone } from "./ui";

const STATUS_TONE: Record<ToolCall["status"], Tone> = { ok: "success", rejected: "warning", error: "danger" };
const FILTERS = ["all", "ok", "rejected", "error"] as const;

export function ToolLogPanel({ workspaceId }: { workspaceId: string }) {
  const [calls, setCalls] = useState<ToolCall[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");

  const refresh = useCallback(() => {
    apiFetch<ToolCall[]>(`/workspaces/${workspaceId}/tool-calls`)
      .then(setCalls)
      .catch(() => setError("Could not load the tool log."));
  }, [workspaceId]);

  useEffect(refresh, [refresh]);

  const shown = calls?.filter((c) => filter === "all" || c.status === filter) ?? [];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-1 rounded-lg bg-subtle p-1" role="tablist" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button
              key={f}
              role="tab"
              aria-selected={filter === f}
              onClick={() => setFilter(f)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium capitalize transition",
                filter === f ? "bg-card shadow-sm" : "text-muted hover:text-foreground",
              )}
            >
              {f}
              {calls && f !== "all" && (
                <span className="ml-1 text-muted">{calls.filter((c) => c.status === f).length}</span>
              )}
            </button>
          ))}
        </div>
        <button onClick={refresh} className="btn btn-ghost px-2.5 py-1.5">
          <RefreshCw className="size-3.5" aria-hidden /> Refresh
        </button>
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}
      {!calls && !error && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Spinner /> Loading…
        </p>
      )}
      {calls && shown.length === 0 && (
        <div className="card">
          <EmptyState icon={<Activity className="size-5" />} title={calls.length ? "Nothing matches this filter" : "No tool calls yet"}>
            Calls appear here when the assistant saves a task, lists tasks, searches documents or posts to Discord.
          </EmptyState>
        </div>
      )}
      {shown.length > 0 && (
        <ul className="card divide-y divide-border">
          {shown.map((c) => (
            <li key={c.id}>
              <details className="group">
                <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 px-4 py-3 text-sm hover:bg-subtle/60 [&::-webkit-details-marker]:hidden">
                  <ChevronRight className="size-4 text-muted transition group-open:rotate-90" aria-hidden />
                  <span className="font-mono font-medium">{c.name}</span>
                  <Pill tone={STATUS_TONE[c.status]}>{c.status}</Pill>
                  <span className="ml-auto text-xs text-muted">
                    {new Date(c.created_at).toLocaleString()} · {c.latency_ms} ms
                  </span>
                  {c.error && <span className="w-full pl-7 text-xs text-rose-600">{c.error}</span>}
                </summary>
                <div className="grid gap-3 px-4 pb-4 pl-11 text-xs md:grid-cols-2">
                  <Json label="Arguments" value={c.args} />
                  <Json label="Result" value={c.result} />
                </div>
              </details>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Json({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-w-0">
      <p className="mb-1 font-medium text-muted">{label}</p>
      <pre className="scroll-thin max-h-60 overflow-auto rounded-lg border border-border bg-subtle p-3 font-mono">
        {value == null ? "—" : JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
