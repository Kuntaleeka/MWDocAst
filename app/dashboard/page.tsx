"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CreateWorkspaceForm } from "@/components/CreateWorkspaceForm";
import { SignOutButton } from "@/components/SignOutButton";
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
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-6">
      {state === "loading" && <p className="opacity-70">Loading workspaces…</p>}
      {state === "error" && <p className="text-red-600">Could not load workspaces. Try again.</p>}
      {state === "empty" && (
        <>
          <h1 className="text-xl font-semibold">Create your first workspace</h1>
          <CreateWorkspaceForm onCreated={(ws) => router.replace(`/dashboard/${ws.id}`)} />
        </>
      )}
      <SignOutButton />
    </main>
  );
}
