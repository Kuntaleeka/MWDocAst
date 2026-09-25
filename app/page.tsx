import Link from "next/link";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-3xl font-semibold">Workspace Doc Assistant</h1>
      <p className="max-w-md text-sm opacity-70">
        Upload documents into a workspace and ask grounded questions, with answers cited from that
        workspace only.
      </p>
      <Link className="rounded bg-foreground px-4 py-2 text-sm text-background" href="/dashboard">
        Open dashboard
      </Link>
    </main>
  );
}
