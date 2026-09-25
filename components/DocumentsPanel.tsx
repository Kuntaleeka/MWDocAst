"use client";

import { CircleCheck, CircleX, FileText, RotateCw, Trash2, UploadCloud } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, type DocumentInfo } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { cn, EmptyState, ErrorNote, Pill, Spinner, type Tone } from "./ui";

type UploadRow = { name: string; state: "uploading" | "processing" | "done" | "error"; note?: string };

const ACCEPT = ".pdf,.md,.markdown,.txt";
const MAX_BYTES = 10 * 1024 * 1024;

const STATUS_TONE: Record<DocumentInfo["status"], Tone> = { ready: "success", processing: "warning", failed: "danger" };

function formatSize(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function DocumentsPanel({ workspaceId }: { workspaceId: string }) {
  const base = `/workspaces/${workspaceId}/documents`;
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null);
  const [uploads, setUploads] = useState<UploadRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    apiFetch<DocumentInfo[]>(base)
      .then((d) => {
        setDocs(d);
        setLoadError(null);
      })
      .catch(() => setLoadError("Could not load documents."));
  }, [base]);

  useEffect(refresh, [refresh]);

  // Another tab (or a slow ingest) may still be processing: poll until everything settles.
  const processing = docs?.some((d) => d.status === "processing") ?? false;
  useEffect(() => {
    if (!processing) return;
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [processing, refresh]);

  function setRow(i: number, row: Partial<UploadRow>) {
    setUploads((rows) => rows.map((r, j) => (j === i ? { ...r, ...row } : r)));
  }

  async function uploadOne(file: File, i: number) {
    if (file.size > MAX_BYTES) return setRow(i, { state: "error", note: "Larger than 10 MB" });
    try {
      // 1. Ask the API for a signed upload URL scoped to this workspace.
      const { path, token, content_type } = await apiFetch<{
        path: string;
        token: string;
        content_type: string;
      }>(`${base}/upload-url`, {
        method: "POST",
        body: JSON.stringify({ filename: file.name, size_bytes: file.size }),
      });
      // 2. Send the bytes straight to Supabase Storage (bypasses Vercel's 4.5 MB body limit).
      const { error } = await createClient()
        .storage.from("documents")
        .uploadToSignedUrl(path, token, file, { contentType: content_type });
      if (error) throw new Error(error.message);
      // 3. Ask the API to parse, chunk, embed and store it.
      setRow(i, { state: "processing" });
      const doc = await apiFetch<DocumentInfo & { duplicate: boolean }>(`${base}/ingest`, {
        method: "POST",
        body: JSON.stringify({ path, filename: file.name }),
      });
      setRow(i, {
        state: doc.status === "failed" ? "error" : "done",
        note: doc.duplicate ? "Already uploaded, no changes" : (doc.error ?? `${doc.chunk_count} chunks`),
      });
    } catch (err) {
      setRow(i, { state: "error", note: err instanceof Error ? err.message : "Upload failed" });
    }
  }

  async function onFiles(files: FileList | null) {
    if (!files?.length) return;
    const list = Array.from(files);
    const offset = uploads.length;
    setUploads((rows) => [...rows, ...list.map((f) => ({ name: f.name, state: "uploading" as const }))]);
    if (inputRef.current) inputRef.current.value = "";
    await Promise.all(list.map((f, k) => uploadOne(f, offset + k)));
    refresh();
  }

  async function retry(id: string) {
    setDocs((d) => d?.map((x) => (x.id === id ? { ...x, status: "processing", error: null } : x)) ?? d);
    await apiFetch(`${base}/${id}/retry`, { method: "POST" }).catch(() => {});
    refresh();
  }

  async function remove(doc: DocumentInfo) {
    if (!confirm(`Delete "${doc.filename}" and its chunks from this workspace?`)) return;
    await apiFetch(`${base}/${doc.id}`, { method: "DELETE" }).catch(() => {});
    refresh();
  }

  return (
    <div className="flex flex-col gap-6">
      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          onFiles(e.dataTransfer.files);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition",
          dragging ? "border-accent bg-accent-soft" : "border-border bg-card hover:border-accent/50 hover:bg-subtle",
        )}
      >
        <span className="flex size-11 items-center justify-center rounded-xl bg-accent-soft text-accent">
          <UploadCloud className="size-5" aria-hidden />
        </span>
        <span className="text-sm">
          <span className="font-medium text-accent">Choose files</span> or drag them here
        </span>
        <span className="text-xs text-muted">PDF, Markdown or text · up to 10 MB each</span>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          className="sr-only"
          onChange={(e) => onFiles(e.target.files)}
        />
      </label>

      {uploads.length > 0 && (
        <ul className="card divide-y divide-border">
          {uploads.map((u, i) => (
            <li key={i} className="flex items-center gap-3 px-4 py-2.5 text-sm">
              {u.state === "done" ? (
                <CircleCheck className="size-4 text-emerald-600" aria-hidden />
              ) : u.state === "error" ? (
                <CircleX className="size-4 text-rose-600" aria-hidden />
              ) : (
                <Spinner className="text-accent" />
              )}
              <span className="min-w-0 flex-1 truncate">{u.name}</span>
              <span className={cn("text-xs", u.state === "error" ? "text-rose-600" : "text-muted")}>
                {u.state === "uploading" && "Uploading…"}
                {u.state === "processing" && "Chunking & embedding…"}
                {(u.state === "done" || u.state === "error") && (u.note ?? (u.state === "done" ? "Done" : "Failed"))}
              </span>
            </li>
          ))}
        </ul>
      )}

      <section className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 className="font-semibold tracking-tight">In this workspace</h2>
          {docs && docs.length > 0 && (
            <span className="text-xs text-muted">
              {docs.length} document{docs.length === 1 ? "" : "s"} ·{" "}
              {docs.reduce((n, d) => n + d.chunk_count, 0)} chunks
            </span>
          )}
        </div>
        {loadError && <ErrorNote>{loadError}</ErrorNote>}
        {!docs && !loadError && (
          <p className="flex items-center gap-2 text-sm text-muted">
            <Spinner /> Loading…
          </p>
        )}
        {docs?.length === 0 && (
          <div className="card">
            <EmptyState icon={<FileText className="size-5" />} title="No documents yet">
              Upload a file above. The assistant only answers from documents in this workspace.
            </EmptyState>
          </div>
        )}
        {docs && docs.length > 0 && (
          <ul className="card divide-y divide-border">
            {docs.map((d) => (
              <li key={d.id} className="group flex flex-wrap items-center gap-3 px-4 py-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-subtle text-muted">
                  <FileText className="size-4" aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium" title={d.filename}>
                    {d.filename}
                  </p>
                  <p className="text-xs text-muted">
                    {d.chunk_count} chunks · {formatSize(d.size_bytes)} ·{" "}
                    {new Date(d.created_at).toLocaleDateString()}
                  </p>
                </div>
                <Pill tone={STATUS_TONE[d.status]}>
                  {d.status === "processing" && <Spinner className="size-3" />}
                  {d.status}
                </Pill>
                <div className="flex items-center">
                  {d.status === "failed" && (
                    <button className="btn-icon" onClick={() => retry(d.id)} title="Retry" aria-label={`Retry ${d.filename}`}>
                      <RotateCw className="size-4" />
                    </button>
                  )}
                  <button
                    className="btn-icon hover:text-rose-600"
                    onClick={() => remove(d)}
                    title="Delete"
                    aria-label={`Delete ${d.filename}`}
                  >
                    <Trash2 className="size-4" />
                  </button>
                </div>
                {d.error && <p className="w-full pl-12 text-xs text-rose-600">{d.error}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
