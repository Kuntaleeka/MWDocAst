"use client";

import { FolderPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CreateWorkspaceForm } from "@/components/CreateWorkspaceForm";
import { SignOutButton } from "@/components/SignOutButton";
import { ErrorNote, Logo, Spinner } from "@/components/ui";
import { apiFetch, type Workspace } from "@/lib/api";

// Sends the user to their first workspace, or asks them to create one.
export default function DashboardIndex() {
  const router = useRouter();
  const [state, setState] = useState<"loading" | "empty" | "error">("loading");

  useEffect(() => {
    apiFetch<Workspace[]>("/workspaces")
      .then((ws) => (ws.length ? router.replace(`/dashboard/${ws[0].id}`) : setState("empty")))
      .catch(() => setState("error"));
  }, [router]);

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex items-center justify-between border-b border-border bg-card/60 px-6 py-3">
        <Logo />
        <SignOutButton />
      </header>
      <main className="flex flex-1 items-center justify-center p-6">
        {state === "loading" && (
          <p className="flex items-center gap-2 text-sm text-muted">
            <Spinner /> Loading workspaces…
          </p>
        )}
        {state === "error" && <ErrorNote>Could not load workspaces. Refresh to try again.</ErrorNote>}
        {state === "empty" && (
          <div className="card flex w-full max-w-md flex-col gap-5 p-8">
            <div className="flex size-11 items-center justify-center rounded-xl bg-accent-soft text-accent">
              <FolderPlus className="size-5" aria-hidden />
            </div>
            <div className="flex flex-col gap-1">
              <h1 className="text-xl font-semibold tracking-tight">Create your first workspace</h1>
              <p className="text-sm text-muted">
                Each workspace keeps its own documents, chats and tasks. Nothing is shared between them.
              </p>
            </div>
            <CreateWorkspaceForm onCreated={(ws) => router.replace(`/dashboard/${ws.id}`)} />
          </div>
        )}
      </main>
    </div>
  );
}
