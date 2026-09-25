"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

export function SignOutButton() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  useEffect(() => {
    createClient()
      .auth.getSession()
      .then(({ data }) => setEmail(data.session?.user.email ?? null));
  }, []);
  return (
    <div className="flex items-center gap-3">
      {email && <span className="text-xs opacity-60">{email}</span>}
      <button
        className="text-sm underline"
        onClick={async () => {
          await createClient().auth.signOut();
          router.replace("/login");
          router.refresh();
        }}
      >
        Sign out
      </button>
    </div>
  );
}
