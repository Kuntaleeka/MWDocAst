"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Workspace } from "@/lib/api";
import { CreateWorkspaceForm } from "./CreateWorkspaceForm";

export function WorkspaceSwitcher({
  workspaces,
  activeId,
}: {
  workspaces: Workspace[];
  activeId: string;
}) {
  const router = useRouter();
  const [creating, setCreating] = useState(false);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="text-sm opacity-70" htmlFor="ws-switch">
        Workspace
      </label>
      <select
        id="ws-switch"
        className="rounded border border-black/20 bg-transparent px-2 py-1 text-sm dark:border-white/20"
        value={activeId}
        onChange={(e) => router.push(`/dashboard/${e.target.value}`)}
      >
        {workspaces.map((w) => (
          <option key={w.id} value={w.id}>
            {w.name}
          </option>
        ))}
      </select>
      {creating ? (
        <CreateWorkspaceForm onCreated={(ws) => router.push(`/dashboard/${ws.id}`)} />
      ) : (
        <button className="text-sm underline" onClick={() => setCreating(true)}>
          + New
        </button>
      )}
    </div>
  );
}
