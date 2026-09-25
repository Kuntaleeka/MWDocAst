"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ChatPanel } from "@/components/ChatPanel";
import { DocumentsPanel } from "@/components/DocumentsPanel";
import { SignOutButton } from "@/components/SignOutButton";
import { TasksPanel } from "@/components/TasksPanel";
import { ToolLogPanel } from "@/components/ToolLogPanel";
import { WorkspaceSwitcher } from "@/components/WorkspaceSwitcher";
import { ApiError, apiFetch, type Workspace } from "@/lib/api";

const TABS = ["chat", "documents", "tasks", "tool log"] as const;
type Tab = (typeof TABS)[number];

export default function WorkspaceDashboard() {
  const { wsId } = useParams<{ wsId: string }>();
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [active, setActive] = useState<Workspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("chat");

  useEffect(() => {
    // The server re-checks membership; a workspace you don't belong to is a 404.
    Promise.all([apiFetch<Workspace[]>("/workspaces"), apiFetch<Workspace>(`/workspaces/${wsId}`)])
      .then(([all, ws]) => {
        setError(null);
        setWorkspaces(all);
        setActive(ws);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) router.replace("/dashboard");
        else setError("Could not load this workspace.");
      });
  }, [wsId, router]);

  if (error) return <p className="p-6 text-red-600">{error}</p>;
  if (!workspaces || !active) return <p className="p-6 opacity-70">Loading…</p>;

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-black/10 px-6 py-3 dark:border-white/10">
        <WorkspaceSwitcher workspaces={workspaces} activeId={active.id} />
        <SignOutButton />
      </header>
      <main className="flex w-full max-w-5xl flex-1 flex-col gap-6 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-xl font-semibold">{active.name}</h1>
          <nav className="flex gap-1 text-sm">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded px-3 py-1 capitalize ${
                  tab === t ? "bg-foreground text-background" : "opacity-70 hover:opacity-100"
                }`}
              >
                {t}
              </button>
            ))}
          </nav>
        </div>
        {/* key: remount on workspace switch so no state leaks between workspaces */}
        {tab === "chat" && <ChatPanel key={active.id} workspaceId={active.id} />}
        {tab === "documents" && <DocumentsPanel key={active.id} workspaceId={active.id} />}
        {tab === "tasks" && <TasksPanel key={active.id} workspaceId={active.id} />}
        {tab === "tool log" && <ToolLogPanel key={active.id} workspaceId={active.id} />}
      </main>
    </div>
  );
}
