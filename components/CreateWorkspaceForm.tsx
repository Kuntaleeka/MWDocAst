"use client";

import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { apiFetch, type Workspace } from "@/lib/api";
import { Spinner } from "./ui";

export function CreateWorkspaceForm({
  onCreated,
  compact = false,
}: {
  onCreated: (ws: Workspace) => void;
  compact?: boolean;
}) {
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
    <form onSubmit={submit} className="flex w-full flex-col gap-2">
      <div className="flex gap-2">
        <input
          className={compact ? "input py-1.5" : "input"}
          placeholder="e.g. Acme HR"
          aria-label="Workspace name"
          maxLength={80}
          required
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button disabled={busy || !name.trim()} className={`btn btn-primary ${compact ? "px-2.5 py-1.5" : ""}`}>
          {busy ? <Spinner /> : compact ? <ArrowRight className="size-4" aria-label="Create" /> : "Create"}
        </button>
      </div>
      {error && <span className="text-xs text-rose-600">{error}</span>}
    </form>
  );
}
