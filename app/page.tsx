export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-3xl font-semibold">Workspace Doc Assistant</h1>
      <p className="max-w-md text-sm opacity-70">
        Upload documents into a workspace and ask grounded questions. Sign-in
        and the dashboard are coming in the next phase.
      </p>
      <a className="text-sm underline" href="/api/py/health">
        API health check
      </a>
    </main>
  );
}
