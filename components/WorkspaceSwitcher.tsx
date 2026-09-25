"use client";

import { Check, ChevronsUpDown, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { Workspace } from "@/lib/api";
import { CreateWorkspaceForm } from "./CreateWorkspaceForm";
import { cn } from "./ui";

export function WorkspaceAvatar({ name, className }: { name: string; className?: string }) {
  const initials = name
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  return (
    <span
      className={cn(
        "flex size-7 shrink-0 items-center justify-center rounded-md bg-accent-soft text-[0.7rem] font-semibold text-accent",
        className,
      )}
    >
      {initials || "W"}
    </span>
  );
}

export function WorkspaceSwitcher({ workspaces, activeId }: { workspaces: Workspace[]; activeId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = workspaces.find((w) => w.id === activeId);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && close();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function close() {
    setOpen(false);
    setCreating(false);
  }

  function go(id: string) {
    close();
    if (id !== activeId) router.push(`/dashboard/${id}`);
  }

  return (
    <div ref={ref} className="relative w-full">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex w-full items-center gap-2.5 rounded-lg border border-border bg-card px-2 py-1.5 text-left text-sm transition hover:bg-subtle focus-visible:ring-4 focus-visible:ring-ring outline-none"
      >
        <WorkspaceAvatar name={active?.name ?? ""} />
        <span className="min-w-0 flex-1">
          <span className="block text-[0.7rem] leading-tight text-muted">Workspace</span>
          <span className="block truncate font-medium leading-tight">{active?.name}</span>
        </span>
        <ChevronsUpDown className="size-4 text-muted" aria-hidden />
      </button>

      {open && (
        <div
          role="menu"
          className="card absolute left-0 right-0 top-full z-30 mt-1.5 flex flex-col gap-0.5 p-1.5 shadow-lg md:min-w-60"
        >
          <p className="px-2 pb-1 pt-0.5 text-[0.7rem] font-medium uppercase tracking-wide text-muted">
            Your workspaces
          </p>
          <div className="scroll-thin flex max-h-64 flex-col gap-0.5 overflow-y-auto">
            {workspaces.map((w) => (
              <button
                key={w.id}
                role="menuitem"
                onClick={() => go(w.id)}
                className="flex items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm hover:bg-subtle"
              >
                <WorkspaceAvatar name={w.name} className="size-6" />
                <span className="min-w-0 flex-1 truncate">{w.name}</span>
                {w.id === activeId && <Check className="size-4 text-accent" aria-label="Active" />}
              </button>
            ))}
          </div>
          <div className="my-1 border-t border-border" />
          {creating ? (
            <div className="p-1">
              <CreateWorkspaceForm compact onCreated={(ws) => go(ws.id)} />
            </div>
          ) : (
            <button
              role="menuitem"
              onClick={() => setCreating(true)}
              className="flex items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm text-muted hover:bg-subtle hover:text-foreground"
            >
              <span className="flex size-6 items-center justify-center rounded-md border border-dashed border-border">
                <Plus className="size-3.5" aria-hidden />
              </span>
              New workspace
            </button>
          )}
        </div>
      )}
    </div>
  );
}
