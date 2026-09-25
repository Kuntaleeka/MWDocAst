import { createBrowserClient } from "@supabase/ssr";

// Browser client: only the public URL + anon key. All data access goes through the Python API.
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
