"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DocumentsPanel } from "@/components/DocumentsPanel";
import { SignOutButton } from "@/components/SignOutButton";
import { WorkspaceSwitcher } from "@/components/WorkspaceSwitcher";
import { ApiError, apiFetch, type Workspace } from "@/lib/api";

export default function WorkspaceDashboard() {
  const { wsId } = useParams<{ wsId: string }>();
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [active, setActive] = useState<Workspace | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      <main className="flex w-full max-w-4xl flex-1 flex-col gap-6 p-6">
        <h1 className="text-xl font-semibold">{active.name}</h1>
        {/* key: remount on workspace switch so no state leaks between workspaces */}
        <DocumentsPanel key={active.id} workspaceId={active.id} />
      </main>
    </div>
  );
}
