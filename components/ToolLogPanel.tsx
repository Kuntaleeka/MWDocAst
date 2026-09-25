"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, type ToolCall } from "@/lib/api";

const STATUS_STYLE: Record<ToolCall["status"], string> = {
  ok: "bg-green-600/15 text-green-700 dark:text-green-400",
  rejected: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  error: "bg-red-600/15 text-red-700 dark:text-red-400",
};

export function ToolLogPanel({ workspaceId }: { workspaceId: string }) {
  const [calls, setCalls] = useState<ToolCall[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    apiFetch<ToolCall[]>(`/workspaces/${workspaceId}/tool-calls`)
      .then(setCalls)
      .catch(() => setError("Could not load the tool log."));
  }, [workspaceId]);

  useEffect(refresh, [refresh]);

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Tool log</h2>
        <button onClick={refresh} className="text-sm underline">
          Refresh
        </button>
      </div>
      <p className="text-xs opacity-60">
        Every tool call the model requested in this workspace, including ones that were rejected
        (unknown tool, invalid arguments, or not requested by the user).
      </p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {calls?.length === 0 && <p className="text-sm opacity-70">No tool calls yet.</p>}
      {calls && calls.length > 0 && (
        <ul className="divide-y divide-black/10 rounded border border-black/10 dark:divide-white/10 dark:border-white/10">
          {calls.map((c) => (
            <li key={c.id} className="px-3 py-2 text-sm">
              <details>
                <summary className="flex cursor-pointer flex-wrap items-center gap-2">
                  <span className="font-mono">{c.name}</span>
                  <span className={`rounded px-2 py-0.5 text-xs ${STATUS_STYLE[c.status]}`}>{c.status}</span>
                  <span className="text-xs opacity-60">
                    {new Date(c.created_at).toLocaleString()} · {c.latency_ms} ms
                  </span>
                  {c.error && <span className="w-full text-xs text-red-600">{c.error}</span>}
                </summary>
                <div className="mt-2 grid gap-2 text-xs md:grid-cols-2">
                  <Json label="Arguments" value={c.args} />
                  <Json label="Result" value={c.result} />
                </div>
              </details>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Json({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-w-0">
      <p className="mb-1 opacity-60">{label}</p>
      <pre className="max-h-60 overflow-auto rounded bg-black/5 p-2 dark:bg-white/5">
        {value == null ? "—" : JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
