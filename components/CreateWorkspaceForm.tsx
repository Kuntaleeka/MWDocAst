"use client";

import { useState } from "react";
import { apiFetch, type Workspace } from "@/lib/api";

export function CreateWorkspaceForm({ onCreated }: { onCreated: (ws: Workspace) => void }) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const ws = await apiFetch<Workspace>("/workspaces", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      setName("");
      onCreated(ws);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create workspace");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
      <input
        className="rounded border border-black/20 bg-transparent px-2 py-1 text-sm dark:border-white/20"
        placeholder="Workspace name"
        maxLength={80}
        required
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <button
        disabled={busy}
        className="rounded bg-foreground px-3 py-1 text-sm text-background disabled:opacity-50"
      >
        Create
      </button>
      {error && <span className="text-sm text-red-600">{error}</span>}
    </form>
  );
}
