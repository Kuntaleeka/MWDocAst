import { createClient } from "@/lib/supabase/client";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Calls the Python API with the user's Supabase access token. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  if (!session) throw new ApiError(401, "Not signed in");

  const res = await fetch(`/api/py${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
      Authorization: `Bearer ${session.access_token}`,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : res.statusText;
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type Workspace = { id: string; name: string; role: string };

export type DocumentInfo = {
  id: string;
  filename: string;
  status: "processing" | "ready" | "failed";
  error: string | null;
  size_bytes: number;
  chunk_count: number;
  created_at: string;
};

export type Citation = {
  label: string;
  chunk_id: string;
  document_id: string;
  filename: string;
  section: string | null;
  snippet: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "pending" | "done" | "failed";
  error: string | null;
  citations: Citation[];
  tools?: { name: string; status: "ok" | "rejected" | "error"; error: string | null }[];
  created_at: string;
};

export type Conversation = { id: string; title: string; updated_at: string };

export type Task = {
  id: string;
  title: string;
  notes: string | null;
  due_date: string | null;
  status: "open" | "done";
  source_message_id: string | null;
  created_at: string;
};

export type ToolCall = {
  id: string;
  message_id: string | null;
  name: string;
  args: unknown;
  status: "ok" | "rejected" | "error";
  result: unknown;
  error: string | null;
  latency_ms: number;
  created_at: string;
};
