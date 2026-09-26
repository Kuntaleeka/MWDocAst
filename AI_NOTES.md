# AI Notes

## Tools and how the work was split

- **Claude Code** (VS Code extension), model **Claude Opus 5.5**. Its context files are committed as
  used: [CLAUDE.md](CLAUDE.md) (project rules, grown after each lesson) and [AGENTS.md](AGENTS.md)
  (Next.js 16 rules from `create-next-app`). [Implementation_Plan.md](Implementation_Plan.md) was the
  shared design doc, updated after every phase with measurements and what broke. No other
  instruction files were used.
- **Me:** chose the stack and host, created the accounts and keys (Supabase, Gemini, Discord,
  Vercel), set the phase order, reviewed each phase on its own branch before merging, and checked
  the live URL after every deploy, including the isolation case.
- **The AI:** wrote the plan, nearly all the code and the tests, and checked risky behaviour with
  real calls: storage uploads, embeddings, Supabase logins, and model calls through the Next.js proxy.

**Why this stack:** Python + Next.js + Supabase is a strong combination for a RAG-based
document/workspace manager because each technology handles a different part of the system
efficiently: **Next.js** provides a modern, interactive frontend for managing workspaces, documents,
uploads and chat; **Python** is ideal for the RAG/AI backend because of its ecosystem for document
processing, embeddings and LLM APIs; and **Supabase** provides PostgreSQL for structured data,
**pgvector** for storing and searching embeddings, Storage for uploaded documents, and Authentication
for users, with Row Level Security as a second wall that keeps the browser out of the tables
(isolation itself is enforced in the API and inside the SQL search). This means you can build the
core system without immediately needing separate services for a database, vector database, file
storage, and authentication, while still having an architecture that can later scale into a more
enterprise-grade RAG platform.

## Key decisions

1. **Isolation inside the SQL query; the workspace never comes from the model.** `search_chunks()`
   filters on the workspace inside both halves of hybrid search, vector and keyword. Its workspace
   comes only from a verified login and membership check, and no tool accepts a workspace ID. We hit
   a real pgvector trap: a filtered approximate search can return **zero rows** for a small
   workspace, because other workspaces' neighbours fill the candidate list. A test forces that path
   and shows 0 rows without `hnsw.iterative_scan` and 5 correct rows with it.
2. **Two layers for "I don't know".** Measured Gemini similarity: 0.68–0.79 for on-topic questions,
   0.52–0.61 for off-topic ones. Below 0.6 the model isn't called at all. Above it, the prompt makes
   the model refuse when the sources don't cover the question. Citations are checked afterwards, and
   invented ones are removed.
3. **Side-effect tools are only offered when the user asks.** Schema validation stops bad arguments,
   not a well-formed call that a document tricked the model into. So `save_task` and
   `send_discord_summary` are only offered when the *user's* message shows that intent; document text
   can't unlock them. A live injection document demanding `delete_everything` and a "PWNED" task
   produced neither.

## Hardest bug: a fallback model that never worked

**What the AI got wrong.** After a free-tier rate limit in Phase 4, the AI added a fallback: on a 429,
switch to `gemini-2.5-flash-lite`. It picked the model from memory, saw it in the API's model list,
tested the fallback with **fake** clients, and reported it done. On this key the model was retired:

```
gemini gemini-2.5-flash error 429: You exceeded your current quota…
gemini gemini-2.5-flash-lite error 404: This model models/gemini-2.5-flash-lite is no longer available to new users.
```

Once the main model hit its quota, **every** answer failed, and the 404 hid the rate-limit message
behind a vague "failed to answer".

**The wrong turn before it.** In Phase 5 a live multi-step request failed exactly this way. The AI
re-ran it, it passed, and the failure was written off as "transient". It added error-code logging but
didn't dig further.

**How it was noticed.** A live streaming test in Phase 6 failed right after a tool call. A stale dev
server from an earlier session briefly confused the diagnosis. Once it was stopped, the Phase 5
logging printed the two lines above.

**How it was fixed.** A tested model chain (`gemini-3.5-flash-lite` → `gemini-3-flash-preview` →
`gemini-2.5-flash`). A script, `scripts/check_models.py`, makes a real streaming call and a real tool
call per model. "Rate-limited" is always the error reported. Along the way we found Gemini 3.x rejects
`thinking_budget=0`, so the thinking setting is now chosen per model family.

**Lesson (now in CLAUDE.md):** fakes prove your own logic, not an outside service's behaviour. Anything
that depends on one gets at least one real call before it's called done.

**Smaller catches:** database tests silently skipped because a dummy DB URL was set before `.env`
loaded. A question and its answer got the same timestamp, since `now()` is fixed inside a transaction.
And the secret audit reported "clean" while scanning only committed files. Each fix is in the commit
history.

## What I'd improve with more time

- **Retrieval:** a re-ranking step, and a larger, messier evaluation corpus. On the 12-section sample
  corpus, vector ranking was already perfect; hybrid's only measured gain was exact terms.
- **Intent gate:** a small classifier call on the user's message, or one-click confirmation for
  side-effect tools, instead of keywords that can miss unusual phrasing.
- **Ingestion** as a background job, rather than inside a request with a 300-second limit.
- **Faster tests:** reuse connections and roll back per test; the suite takes about 6 minutes against
  the remote database.
