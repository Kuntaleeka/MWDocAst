"use client";

import { ShieldCheck, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { apiFetch, type MessageDebug } from "@/lib/api";
import { cn, Pill, Spinner } from "./ui";

/** Retrieval debug for one answer: which workspace and chunks it drew on, and proof of isolation. */
export function DebugPanel({ workspaceId, messageId }: { workspaceId: string; messageId: string }) {
  const [data, setData] = useState<MessageDebug | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    apiFetch<MessageDebug>(`/workspaces/${workspaceId}/messages/${messageId}/debug`)
      .then(setData)
      .catch(() => setError(true));
  }, [workspaceId, messageId]);

  if (error) return <p className="text-xs text-rose-600">No debug record for this answer.</p>;
  if (!data)
    return (
      <p className="flex items-center gap-2 text-xs text-muted">
        <Spinner className="size-3" /> Loading debug info…
      </p>
    );

  const ok = data.isolation.violations === 0;
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-subtle/60 p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={ok ? "success" : "danger"}>
          {ok ? <ShieldCheck className="size-3" aria-hidden /> : <ShieldAlert className="size-3" aria-hidden />}
          {ok
            ? `Isolation verified: ${data.isolation.checked} chunk${data.isolation.checked === 1 ? "" : "s"}, all from this workspace or shared into it`
            : `${data.isolation.violations} chunk(s) from another workspace`}
        </Pill>
        <span className="text-muted">
          workspace <code className="font-mono">{data.workspace_id.slice(0, 8)}</code> · retrieval {data.retrieval_ms ?? "—"} ms ·
          total {data.total_ms != null ? `${(data.total_ms / 1000).toFixed(1)} s` : "—"}
        </span>
      </div>

      {data.hits.length === 0 ? (
        <p className="text-muted">Retrieval returned no chunks.</p>
      ) : (
        <div className="scroll-thin overflow-x-auto">
          <table className="w-full min-w-[34rem]">
            <thead className="text-left text-muted">
              <tr>
                <th className="py-1 pr-2 font-medium">Chunk</th>
                <th className="py-1 pr-2 text-right font-medium" title="Cosine similarity">Sim</th>
                <th className="py-1 pr-2 text-right font-medium" title="Rank in vector search">Vec</th>
                <th className="py-1 pr-2 text-right font-medium" title="Rank in keyword search">Kw</th>
                <th className="py-1 pr-2 font-medium">Source</th>
                <th className="py-1 font-medium">Used</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border tabular-nums">
              {data.hits.map((h) => (
                <tr key={h.chunk_id} className={cn(!h.used && "text-muted")} title={h.preview}>
                  <td className="max-w-56 truncate py-1 pr-2">
                    {h.filename}
                    {h.section && <span className="text-muted"> § {h.section}</span>}
                  </td>
                  <td className="py-1 pr-2 text-right">{h.similarity.toFixed(3)}</td>
                  <td className="py-1 pr-2 text-right">{h.vector_rank ?? "—"}</td>
                  <td className="py-1 pr-2 text-right">{h.keyword_rank ?? "—"}</td>
                  <td className="py-1 pr-2">
                    <Pill tone={h.access === "own" ? "neutral" : h.access === "shared" ? "accent" : "danger"}>
                      {h.access === "shared" ? `shared from ${h.workspace_name}` : h.access}
                    </Pill>
                  </td>
                  <td className="py-1">{h.used ? "✓" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data.llm_calls.length > 0 && (
        <p className="text-muted">
          Model calls:{" "}
          {data.llm_calls
            .map((c) => `${c.model} (${c.prompt_tokens ?? "?"}→${c.completion_tokens ?? "?"} tokens, ${c.latency_ms} ms${c.error ? ", failed" : ""})`)
            .join(" · ")}
        </p>
      )}
    </div>
  );
}
