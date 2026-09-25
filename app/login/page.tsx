"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { cn, ErrorNote, Logo, Spinner } from "@/components/ui";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const supabase = createClient();
    const { data, error } =
      mode === "signin"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });
    setBusy(false);
    if (error) return setError(error.message);
    if (!data.session) return setError("Check your inbox to confirm your email, then sign in.");
    router.replace("/dashboard");
    router.refresh();
  }

  return (
    <main className="relative flex min-h-dvh items-center justify-center overflow-hidden p-6">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 left-1/2 h-96 w-[40rem] -translate-x-1/2 rounded-full bg-gradient-to-r from-indigo-500/20 via-violet-500/20 to-fuchsia-500/10 blur-3xl"
      />
      <div className="relative flex w-full max-w-sm flex-col gap-6">
        <Logo className="justify-center text-lg" />
        <form onSubmit={submit} className="card flex flex-col gap-4 p-6 shadow-lg">
          <div className="grid grid-cols-2 gap-1 rounded-lg bg-subtle p-1">
            {(["signin", "signup"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => {
                  setMode(m);
                  setError(null);
                }}
                className={cn(
                  "rounded-md py-1.5 text-sm font-medium transition",
                  mode === m ? "bg-card shadow-sm" : "text-muted hover:text-foreground",
                )}
              >
                {m === "signin" ? "Sign in" : "Create account"}
              </button>
            ))}
          </div>
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Email
            <input
              className="input font-normal"
              type="email"
              placeholder="you@example.com"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Password
            <input
              className="input font-normal"
              type="password"
              placeholder={mode === "signup" ? "At least 6 characters" : "••••••••"}
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              minLength={6}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && <ErrorNote>{error}</ErrorNote>}
          <button disabled={busy} className="btn btn-primary w-full">
            {busy && <Spinner />}
            {mode === "signin" ? "Sign in" : "Create account"}
          </button>
        </form>
        <p className="text-center text-xs text-muted">
          Each workspace&apos;s documents stay isolated, even from your other workspaces.
        </p>
      </div>
    </main>
  );
}
