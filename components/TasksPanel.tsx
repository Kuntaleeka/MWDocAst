"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, type Task } from "@/lib/api";

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

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">Tasks</h2>
      <p className="text-xs opacity-60">Saved by the assistant when you ask it to (e.g. “save a task to…”).</p>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {tasks?.length === 0 && <p className="text-sm opacity-70">No tasks yet.</p>}
      {tasks && tasks.length > 0 && (
        <ul className="divide-y divide-black/10 rounded border border-black/10 dark:divide-white/10 dark:border-white/10">
          {tasks.map((t) => (
            <li key={t.id} className="flex items-start gap-3 px-3 py-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={t.status === "done"}
                onChange={() => toggle(t)}
                aria-label={`Mark "${t.title}" ${t.status === "open" ? "done" : "open"}`}
              />
              <div className="min-w-0 flex-1">
                <p className={t.status === "done" ? "line-through opacity-60" : ""}>{t.title}</p>
                {t.notes && <p className="text-xs opacity-70">{t.notes}</p>}
              </div>
              {t.due_date && <span className="text-xs opacity-70">due {t.due_date}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
