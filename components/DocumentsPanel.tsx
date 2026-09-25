"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, type DocumentInfo } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

type UploadRow = { name: string; state: "uploading" | "processing" | "done" | "error"; note?: string };

const ACCEPT = ".pdf,.md,.markdown,.txt";
const MAX_BYTES = 10 * 1024 * 1024;

const STATUS_STYLE: Record<DocumentInfo["status"], string> = {
  ready: "bg-green-600/15 text-green-700 dark:text-green-400",
  processing: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  failed: "bg-red-600/15 text-red-700 dark:text-red-400",
};

export function DocumentsPanel({ workspaceId }: { workspaceId: string }) {
  const base = `/workspaces/${workspaceId}/documents`;
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null);
  const [uploads, setUploads] = useState<UploadRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
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
        note: doc.duplicate ? "Already uploaded, no changes" : (doc.error ?? undefined),
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
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Documents</h2>
        <label className="cursor-pointer rounded bg-foreground px-3 py-1 text-sm text-background">
          Upload
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            multiple
            className="hidden"
            onChange={(e) => onFiles(e.target.files)}
          />
        </label>
      </div>
      <p className="text-xs opacity-60">PDF, Markdown or text, up to 10 MB each.</p>

      {uploads.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {uploads.map((u, i) => (
            <li key={i} className="flex flex-wrap gap-2">
              <span className="font-mono">{u.name}</span>
              <span className={u.state === "error" ? "text-red-600" : "opacity-70"}>
                {u.state === "uploading" && "uploading…"}
                {u.state === "processing" && "chunking & embedding…"}
                {u.state === "done" && "✓"}
                {u.state === "error" && "failed"}
              </span>
              {u.note && <span className="opacity-70">{u.note}</span>}
            </li>
          ))}
        </ul>
      )}

      {loadError && <p className="text-sm text-red-600">{loadError}</p>}
      {docs && docs.length === 0 && <p className="text-sm opacity-70">No documents yet.</p>}
      {docs && docs.length > 0 && (
        <ul className="divide-y divide-black/10 rounded border border-black/10 dark:divide-white/10 dark:border-white/10">
          {docs.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-sm">
              <span className="min-w-0 flex-1 truncate font-medium" title={d.filename}>
                {d.filename}
              </span>
              <span className={`rounded px-2 py-0.5 text-xs ${STATUS_STYLE[d.status]}`}>{d.status}</span>
              <span className="text-xs opacity-60">
                {d.chunk_count} chunks · {(d.size_bytes / 1024).toFixed(0)} KB
              </span>
              {d.status === "failed" && (
                <button className="text-xs underline" onClick={() => retry(d.id)}>
                  Retry
                </button>
              )}
              <button className="text-xs underline opacity-60" onClick={() => remove(d)}>
                Delete
              </button>
              {d.error && <p className="w-full text-xs text-red-600">{d.error}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
