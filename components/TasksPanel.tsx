"use client";

import { CalendarDays, Check, ListChecks } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { apiFetch, type Task } from "@/lib/api";
import { cn, EmptyState, ErrorNote, Pill, Spinner } from "./ui";

export function TasksPanel({ workspaceId }: { workspaceId: string }) {
  const base = `/workspaces/${workspaceId}/tasks`;
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    apiFetch<Task[]>(base)
      .then(setTasks)
      .catch(() => setError("Could not load tasks."));
  }, [base]);

  useEffect(refresh, [refresh]);

  async function toggle(t: Task) {
    const status = t.status === "open" ? "done" : "open";
    setTasks((ts) => ts?.map((x) => (x.id === t.id ? { ...x, status } : x)) ?? ts);
    await apiFetch(`${base}/${t.id}`, { method: "PATCH", body: JSON.stringify({ status }) }).catch(refresh);
  }

  const today = new Date().toISOString().slice(0, 10);
  const open = tasks?.filter((t) => t.status === "open").length ?? 0;

  return (
    <div className="flex flex-col gap-3">
      {tasks && tasks.length > 0 && (
        <p className="text-xs text-muted">
          {open} open · {tasks.length - open} done
        </p>
      )}
      {error && <ErrorNote>{error}</ErrorNote>}
      {!tasks && !error && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Spinner /> Loading…
        </p>
      )}
      {tasks?.length === 0 && (
        <div className="card">
          <EmptyState icon={<ListChecks className="size-5" />} title="No tasks yet">
            Ask in Chat, e.g. “Save a task to review the runbook by Friday”.
          </EmptyState>
        </div>
      )}
      {tasks && tasks.length > 0 && (
        <ul className="card divide-y divide-border">
          {tasks.map((t) => {
            const done = t.status === "done";
            const overdue = !done && t.due_date !== null && t.due_date < today;
            return (
              <li key={t.id} className="flex items-start gap-3 px-4 py-3">
                <button
                  onClick={() => toggle(t)}
                  role="checkbox"
                  aria-checked={done}
                  aria-label={`Mark "${t.title}" ${done ? "open" : "done"}`}
                  className={cn(
                    "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border-2 transition",
                    done ? "border-accent bg-accent text-accent-foreground" : "border-border hover:border-accent",
                  )}
                >
                  {done && <Check className="size-3" strokeWidth={3} />}
                </button>
                <div className="min-w-0 flex-1">
                  <p className={cn("text-sm", done && "text-muted line-through")}>{t.title}</p>
                  {t.notes && <p className="mt-0.5 text-xs text-muted">{t.notes}</p>}
                </div>
                {t.due_date && (
                  <Pill tone={overdue ? "danger" : "neutral"}>
                    <CalendarDays className="size-3" aria-hidden />
                    {overdue ? "Overdue · " : ""}
                    {new Date(`${t.due_date}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                  </Pill>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
