import { ArrowRight, MessageSquareQuote, ShieldCheck, Wrench } from "lucide-react";
import Link from "next/link";
import { Logo } from "@/components/ui";

const FEATURES = [
  {
    icon: ShieldCheck,
    title: "Isolated workspaces",
    body: "Every workspace shares one vector store, but retrieval is filtered inside the query, so one workspace never sees another's content.",
  },
  {
    icon: MessageSquareQuote,
    title: "Grounded answers",
    body: "Answers come from your documents with inline citations, and the assistant says “I don't know” when they don't cover it.",
  },
  {
    icon: Wrench,
    title: "Tools with guardrails",
    body: "Save tasks or post to Discord. Every call is schema-validated, logged, and only offered when you ask for that action.",
  },
];

export default function Home() {
  return (
    <div className="relative flex min-h-dvh flex-col overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-48 left-1/2 h-[28rem] w-[56rem] -translate-x-1/2 rounded-full bg-gradient-to-r from-indigo-500/20 via-violet-500/20 to-fuchsia-500/10 blur-3xl"
      />
      <header className="relative mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-5">
        <Logo />
        <Link href="/login" className="btn btn-ghost">
          Sign in
        </Link>
      </header>
      <main className="relative mx-auto flex w-full max-w-5xl flex-1 flex-col items-center gap-14 px-6 pb-16 pt-12 text-center md:pt-20">
        <div className="flex flex-col items-center gap-6">
          <span className="pill bg-accent-soft text-accent">RAG · tool calling · multi-workspace</span>
          <h1 className="max-w-3xl text-4xl font-semibold tracking-tight md:text-6xl">
            Ask your documents.{" "}
            <span className="bg-gradient-to-r from-indigo-500 to-violet-500 bg-clip-text text-transparent">
              Get cited answers.
            </span>
          </h1>
          <p className="max-w-xl text-base text-muted md:text-lg">
            Upload documents into separate workspaces and chat with an assistant that answers only from
            them, cites its sources, and can take actions for you.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Link href="/dashboard" className="btn btn-primary px-5 py-2.5">
              Open dashboard <ArrowRight className="size-4" aria-hidden />
            </Link>
            <Link href="/login" className="btn btn-secondary px-5 py-2.5">
              Create an account
            </Link>
          </div>
        </div>
        <div className="grid w-full gap-4 text-left md:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="card flex flex-col gap-3 p-5">
              <span className="flex size-9 items-center justify-center rounded-lg bg-accent-soft text-accent">
                <Icon className="size-4.5" aria-hidden />
              </span>
              <h2 className="font-semibold">{title}</h2>
              <p className="text-sm text-muted">{body}</p>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
