"use client";

import { Activity, BarChart3, FileText, ListChecks, MessageSquare, type LucideIcon } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ChatPanel } from "@/components/ChatPanel";
import { DocumentsPanel } from "@/components/DocumentsPanel";
import { InsightsPanel } from "@/components/InsightsPanel";
import { SignOutButton } from "@/components/SignOutButton";
import { TasksPanel } from "@/components/TasksPanel";
import { ToolLogPanel } from "@/components/ToolLogPanel";
import { cn, ErrorNote, Logo, Spinner } from "@/components/ui";
import { WorkspaceSwitcher } from "@/components/WorkspaceSwitcher";
import { ApiError, apiFetch, type Workspace } from "@/lib/api";

const TABS: { id: Tab; label: string; icon: LucideIcon; blurb: string }[] = [
  { id: "chat", label: "Chat", icon: MessageSquare, blurb: "Answers grounded in this workspace's documents, with citations." },
  { id: "documents", label: "Documents", icon: FileText, blurb: "Files the assistant can read in this workspace." },
  { id: "tasks", label: "Tasks", icon: ListChecks, blurb: "Tasks the assistant saved when you asked it to." },
  { id: "tool-log", label: "Tool log", icon: Activity, blurb: "Every tool call the model requested, including refused ones." },
  { id: "insights", label: "Insights", icon: BarChart3, blurb: "Latency, retrieval hit rate, token use and tool outcomes." },
];
type Tab = "chat" | "documents" | "tasks" | "tool-log" | "insights";

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

  if (error)
    return (
      <div className="m-auto p-6">
        <ErrorNote>{error}</ErrorNote>
      </div>
    );
  if (!workspaces || !active)
    return (
      <div className="m-auto flex items-center gap-2 p-6 text-sm text-muted">
        <Spinner /> Loading workspace…
      </div>
    );

  const current = TABS.find((t) => t.id === tab)!;
  const nav = (
    <nav className="flex gap-1 md:flex-col" aria-label="Workspace sections">
      {TABS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => setTab(id)}
          aria-current={tab === id ? "page" : undefined}
          className={cn(
            "flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition",
            tab === id ? "bg-accent-soft text-accent" : "text-muted hover:bg-subtle hover:text-foreground",
          )}
        >
          <Icon className="size-4" aria-hidden />
          {label}
        </button>
      ))}
    </nav>
  );

  return (
    <div className="flex h-dvh flex-col md:flex-row">
      {/* Sidebar (desktop) */}
      <aside className="hidden w-64 shrink-0 flex-col gap-5 border-r border-border bg-card/60 p-4 md:flex">
        <Logo className="px-1" />
        <WorkspaceSwitcher workspaces={workspaces} activeId={active.id} />
        {nav}
        <div className="mt-auto border-t border-border pt-3">
          <SignOutButton />
        </div>
      </aside>

      {/* Top bar (mobile) */}
      <header className="flex flex-col gap-3 border-b border-border bg-card/60 p-3 md:hidden">
        <div className="flex items-center justify-between">
          <Logo />
          <SignOutButton compact />
        </div>
        <WorkspaceSwitcher workspaces={workspaces} activeId={active.id} />
        <div className="scroll-thin -mx-3 overflow-x-auto px-3">{nav}</div>
      </header>

      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="hidden border-b border-border px-8 py-5 md:block">
          <h1 className="text-lg font-semibold tracking-tight">{current.label}</h1>
          <p className="text-sm text-muted">{current.blurb}</p>
        </div>
        {/* key: remount on workspace switch so no state leaks between workspaces */}
        <div
          className={cn(
            "min-h-0 flex-1",
            tab === "chat" ? "p-3 md:p-6" : "scroll-thin overflow-y-auto p-4 md:px-8 md:py-6",
          )}
        >
          <div className={cn("mx-auto h-full w-full", tab === "chat" ? "max-w-6xl" : "max-w-4xl")}>
            {tab === "chat" && <ChatPanel key={active.id} workspaceId={active.id} workspaceName={active.name} />}
            {tab === "documents" && (
              <DocumentsPanel key={active.id} workspaceId={active.id} workspaces={workspaces} />
            )}
            {tab === "tasks" && <TasksPanel key={active.id} workspaceId={active.id} />}
            {tab === "tool-log" && <ToolLogPanel key={active.id} workspaceId={active.id} />}
            {tab === "insights" && <InsightsPanel key={active.id} workspaceId={active.id} />}
          </div>
        </div>
      </main>
    </div>
  );
}
