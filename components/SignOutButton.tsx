"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

/** Signed-in user's email plus a sign-out button. `compact` hides the email (mobile header). */
export function SignOutButton({ compact = false }: { compact?: boolean }) {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  useEffect(() => {
    createClient()
      .auth.getSession()
      .then(({ data }) => setEmail(data.session?.user.email ?? null));
  }, []);

  async function signOut() {
    await createClient().auth.signOut();
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="flex min-w-0 items-center gap-2.5">
      {!compact && email && (
        <>
          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-subtle text-xs font-semibold uppercase text-muted">
            {email[0]}
          </span>
          <span className="min-w-0 flex-1 truncate text-sm text-muted" title={email}>
            {email}
          </span>
        </>
      )}
      <button onClick={signOut} className="btn-icon" title="Sign out" aria-label="Sign out">
        <LogOut className="size-4" />
      </button>
    </div>
  );
}
