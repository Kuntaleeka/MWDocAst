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

export type StreamEvent =
  | { event: "meta"; data: { conversation_id: string; user_message: Message; assistant_message_id: string } }
  | { event: "status"; data: { stage: "searching" | "writing" | "tool"; name?: string } }
  | { event: "token"; data: { text: string } }
  | { event: "tool"; data: { name: string; status: "ok" | "rejected" | "error"; error: string | null } }
  | { event: "done"; data: { message: Message } };

/** POSTs to a Server-Sent Events endpoint and calls onEvent for each event as it arrives. */
export async function apiStream(
  path: string,
  body: unknown,
  onEvent: (e: StreamEvent) => void,
): Promise<void> {
  const {
    data: { session },
  } = await createClient().auth.getSession();
  if (!session) throw new ApiError(401, "Not signed in");

  const res = await fetch(`/api/py${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      Authorization: `Bearer ${session.access_token}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({}));
    throw new ApiError(res.status, typeof err.detail === "string" ? err.detail : res.statusText);
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) onEvent({ event, data: JSON.parse(data) } as StreamEvent);
    }
  }
}
