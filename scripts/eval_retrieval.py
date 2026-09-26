"""Measure retrieval quality: vector-only vs hybrid, on the sample docs, with real embeddings.

Creates a throwaway user with two workspaces (sample_docs A and B), asks questions with a known
correct section, and reports hit@1, hit@3, MRR and how often the relevance gate lets the right
chunk through. Off-topic and wrong-workspace questions check that the gate refuses them.
Deletes everything it created. Uses 5 Gemini embedding requests (batched).

Usage: .venv/bin/python scripts/eval_retrieval.py
"""

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))

from _lib.auth import User, WorkspaceContext  # noqa: E402
from _lib.db import connect  # noqa: E402
from _lib.embeddings import embed_queries  # noqa: E402
from _lib.ingest import process_document  # noqa: E402
from _lib.retrieval import search  # noqa: E402

DOCS = {
    "A": ["workspace_a_acme_hr/handbook.md", "workspace_a_acme_hr/benefits.md"],
    "B": ["workspace_b_orion_eng/runbook.md", "workspace_b_orion_eng/vendor-notes.md"],
}
# (workspace, question, expected section suffix); None = should be refused ("I don't know").
CASES = [
    ("A", "What is the Q3 offsite codename?", "Offsite"),
    ("A", "how many vacation days do I get", "Leave"),
    ("A", "Can I expense alcohol?", "Expenses"),
    ("A", "What app do I use to submit expenses?", "Expenses"),
    ("A", "What is Ledgerly?", "Expenses"),
    ("A", "home office stipend", "Remote work"),
    ("A", "What are the core hours?", "Remote work"),
    ("A", "Who provides our health insurance?", "Health"),
    ("A", "Meridian Health", "Health"),
    ("A", "How big is the learning budget?", "Learning"),
    ("A", "gym membership reimbursement", "Wellbeing"),
    ("B", "When is the deploy freeze?", "Deploys"),
    ("B", "How do I roll back a release?", "Deploys"),
    ("B", "orion rollback command", "Deploys"),
    ("B", "Where are break-glass credentials stored?", "Access"),
    ("B", "orion/prod/breakglass", "Access"),
    ("B", "SEV2 postmortem deadline", "Incidents"),
    ("B", "Who is the incident commander for a SEV1?", "Incidents"),
    ("B", "When does the Nimbus contract renew?", "Hosting"),
    ("B", "What is Beacon used for?", "Monitoring"),
    ("B", "eu-west", "Hosting"),
    ("A", "What is the capital of France?", None),
    ("A", "How do I bake sourdough bread?", None),
    ("A", "When is the deploy freeze?", None),  # B's fact asked in A
    ("B", "What is the Q3 offsite codename?", None),  # A's fact asked in B
    ("B", "How much is the learning budget?", None),
    ("B", "Who won the 2022 World Cup?", None),
]


def main() -> None:
    uid = uuid.uuid4()
    with connect() as conn:
        conn.execute(
            "insert into auth.users (id, email, aud, role) values (%s, %s, 'authenticated', 'authenticated')",
            (uid, f"eval-{uid}@example.com"),
        )
        try:
            ctx = {}
            for name, files in DOCS.items():
                wid = conn.execute(
                    "insert into workspaces (name, created_by) values (%s, %s) returning id", (f"eval {name}", uid)
                ).fetchone()["id"]
                ctx[name] = WorkspaceContext(User(uid, None), wid, "owner")
                for f in files:
                    data = (ROOT / "sample_docs" / f).read_bytes()
                    did = conn.execute(
                        """insert into documents (workspace_id, filename, content_hash, size_bytes, storage_path)
                           values (%s, %s, %s, %s, 'eval') returning id""",
                        (wid, Path(f).name, uuid.uuid4().hex, len(data)),
                    ).fetchone()["id"]
                    process_document(conn, did, Path(f).name, data)
            run(conn, ctx)
        finally:
            conn.execute("delete from auth.users where id = %s", (uid,))


def run(conn, ctx) -> None:
    stats = {m: {"h1": 0, "h3": 0, "rr": 0.0, "gate_ok": 0, "refused": 0} for m in ("vector", "hybrid")}
    answerable = [c for c in CASES if c[2]]
    offtopic = [c for c in CASES if not c[2]]
    changed, notes = [], []
    embeddings = embed_queries([q for _, q, _ in CASES])  # one API call, not one per question
    for (ws, question, expected), emb in zip(CASES, embeddings, strict=True):
        ranks = {}
        for mode in ("vector", "hybrid"):
            hits = search(conn, ctx[ws], emb, 8, query_text=question, mode=mode)
            s = stats[mode]
            if expected is None:
                passing = [h for h in hits if h.relevant]
                s["refused"] += not passing
                if passing:
                    notes.append(f"  [{mode}] off-topic {question!r} ({ws}) passes the gate: {_desc(passing[0])}")
                continue
            pos = next((i for i, h in enumerate(hits) if (h.section or "").endswith(expected)), None)
            ranks[mode] = pos
            if pos is not None:
                s["h1"] += pos == 0
                s["h3"] += pos < 3
                s["rr"] += 1 / (pos + 1)
                s["gate_ok"] += hits[pos].relevant
                if not hits[pos].relevant:
                    notes.append(f"  [{mode}] right chunk for {question!r} is blocked by the gate: {_desc(hits[pos])}")
        if expected and ranks["vector"] != ranks["hybrid"]:
            changed.append(f"  {question!r}: rank {_r(ranks['vector'])} → {_r(ranks['hybrid'])}")

    n, m = len(answerable), len(offtopic)
    print(f"\n{n} answerable questions, {m} off-topic / wrong-workspace questions\n")
    print(f"{'mode':8} {'hit@1':>7} {'hit@3':>7} {'MRR':>6} {'gate passes right chunk':>24} {'off-topic refused':>18}")
    for mode, s in stats.items():
        print(f"{mode:8} {s['h1']:>4}/{n} {s['h3']:>4}/{n} {s['rr'] / n:>6.2f} {s['gate_ok']:>20}/{n} {s['refused']:>15}/{m}")
    print("\nrank changes (vector → hybrid, 1 = top):")
    print("\n".join(changed) or "  none")
    print("\ngate notes:")
    print("\n".join(notes) or "  none")


def _desc(h) -> str:
    return f"{h.section} sim={h.similarity:.3f} keyword_rank={h.keyword_rank}"


def _r(pos):
    return "miss" if pos is None else pos + 1


if __name__ == "__main__":
    main()
