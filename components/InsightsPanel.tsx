"use client";

import { Ban, Check, Gauge, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, type Insights } from "@/lib/api";
import { cn, EmptyState, ErrorNote, Pill, Spinner } from "./ui";

const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
const ms = (v: number | null) => (v == null ? "—" : v < 1000 ? `${Math.round(v)} ms` : `${(v / 1000).toFixed(1)} s`);

export function InsightsPanel({ workspaceId }: { workspaceId: string }) {
  const [days, setDays] = useState(7);
  const [data, setData] = useState<Insights | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiFetch<Insights>(`/workspaces/${workspaceId}/insights?days=${days}`)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch(() => setError("Could not load insights."));
  }, [workspaceId, days]);

  useEffect(load, [load]);

  const a = data?.answers;
  const r = data?.retrieval;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex gap-1 self-start rounded-lg bg-subtle p-1" role="tablist" aria-label="Time range">
        {[7, 30].map((d) => (
          <button
            key={d}
            role="tab"
            aria-selected={days === d}
            onClick={() => setDays(d)}
            className={cn(
              "rounded-md px-3 py-1 text-xs font-medium transition",
              days === d ? "bg-card shadow-sm" : "text-muted hover:text-foreground",
            )}
          >
            Last {d} days
          </button>
        ))}
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}
      {!data && !error && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Spinner /> Loading…
        </p>
      )}
      {data && a && r && a.total === 0 && (
        <div className="card">
          <EmptyState icon={<Gauge className="size-5" />} title="No activity in this period">
            Ask something in Chat and the numbers show up here.
          </EmptyState>
        </div>
      )}
      {data && a && r && a.total > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Answers" value={compact.format(a.total)} note={`${a.failed} failed`} />
            <Stat label="Median answer time" value={ms(a.p50_ms)} note={`p95 ${ms(a.p95_ms)}`} />
            <Stat
              label="Retrieval hit rate"
              value={r.total ? `${Math.round((100 * r.hits) / r.total)}%` : "—"}
              note={`${r.hits} of ${r.total} questions found relevant passages`}
            />
            <Stat
              label="Tokens"
              value={compact.format(data.tokens.prompt + data.tokens.completion)}
              note={`${compact.format(data.tokens.prompt)} in · ${compact.format(data.tokens.completion)} out`}
            />
          </div>

          <DailyChart daily={data.daily} />

          <section className="card overflow-x-auto">
            <h3 className="px-4 pt-4 text-sm font-semibold">Model calls</h3>
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="px-4 py-2 font-medium">Model</th>
                  <th className="px-4 py-2 text-right font-medium">Calls</th>
                  <th className="px-4 py-2 text-right font-medium">Errors</th>
                  <th className="px-4 py-2 text-right font-medium">Tokens in / out</th>
                  <th className="px-4 py-2 text-right font-medium">Avg latency</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border tabular-nums">
                {data.models.map((m) => (
                  <tr key={m.model}>
                    <td className="px-4 py-2 font-mono text-xs">{m.model}</td>
                    <td className="px-4 py-2 text-right">{m.calls}</td>
                    <td className="px-4 py-2 text-right">{m.errors}</td>
                    <td className="px-4 py-2 text-right">
                      {compact.format(m.prompt_tokens)} / {compact.format(m.completion_tokens)}
                    </td>
                    <td className="px-4 py-2 text-right">{ms(m.avg_ms)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="card overflow-x-auto">
            <h3 className="px-4 pt-4 text-sm font-semibold">Tool calls</h3>
            {data.tools.length === 0 ? (
              <p className="px-4 pb-4 pt-2 text-sm text-muted">No tool calls in this period.</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted">
                  <tr>
                    <th className="px-4 py-2 font-medium">Tool</th>
                    <th className="px-4 py-2 font-medium">Outcomes</th>
                    <th className="px-4 py-2 text-right font-medium">Avg latency</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border tabular-nums">
                  {data.tools.map((t) => (
                    <tr key={t.name}>
                      <td className="px-4 py-2 font-mono text-xs">{t.name}</td>
                      <td className="px-4 py-2">
                        <div className="flex flex-wrap gap-1.5">
                          <Pill tone="success"><Check className="size-3" aria-hidden /> {t.ok} ok</Pill>
                          {t.rejected > 0 && <Pill tone="warning"><Ban className="size-3" aria-hidden /> {t.rejected} rejected</Pill>}
                          {t.error > 0 && <Pill tone="danger"><X className="size-3" aria-hidden /> {t.error} failed</Pill>}
                        </div>
                      </td>
                      <td className="px-4 py-2 text-right">{ms(t.avg_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="card flex flex-col gap-1 p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="text-2xl font-semibold tracking-tight">{value}</p>
      <p className="text-xs text-muted">{note}</p>
    </div>
  );
}

/** Single-series column chart: answers per day. One series → no legend; the title names it. */
function DailyChart({ daily }: { daily: Insights["daily"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...daily.map((d) => d.answers));
  const label = (day: string) => new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const peak = daily.reduce((best, d, i) => (d.answers > daily[best].answers ? i : best), 0);

  return (
    <section className="card p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold">Answers per day</h3>
        <span className="text-xs text-muted">peak {max}</span>
      </div>
      <div className="relative">
        <div className="flex h-36 items-end gap-0.5 border-b border-border" role="img" aria-label="Answers per day">
          {daily.map((d, i) => (
            <div
              key={d.day}
              className="group relative flex h-full flex-1 items-end justify-center"
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              <div
                className={cn("w-full max-w-6 rounded-t bg-chart transition-opacity", hover !== null && hover !== i && "opacity-40")}
                style={{ height: `${(100 * d.answers) / max}%`, minHeight: d.answers ? 2 : 0 }}
              />
              {i === peak && d.answers > 0 && hover === null && (
                <span className="absolute text-[0.65rem] font-medium tabular-nums text-muted" style={{ bottom: `calc(${(100 * d.answers) / max}% + 4px)` }}>
                  {d.answers}
                </span>
              )}
              {hover === i && (
                <div className="pointer-events-none absolute bottom-full z-10 mb-1 whitespace-nowrap rounded-md border border-border bg-card px-2 py-1 text-xs shadow-md">
                  <span className="text-muted">{label(d.day)}</span> · <span className="font-medium tabular-nums">{d.answers}</span>
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="mt-1.5 flex justify-between text-[0.65rem] text-muted">
          <span>{label(daily[0].day)}</span>
          <span>{label(daily[daily.length - 1].day)}</span>
        </div>
      </div>
      {/* Table view of the same data for screen readers. */}
      <table className="sr-only">
        <caption>Answers per day</caption>
        <tbody>
          {daily.map((d) => (
            <tr key={d.day}>
              <th scope="row">{d.day}</th>
              <td>{d.answers}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
