"""Tool calling: validation, allowlist, intent gate, multi-step loop, logging and scoping."""

import pytest
from fastapi.testclient import TestClient

from _lib import config, llm, retrieval, tools
from api.index import app
from conftest import db_available
from test_chat import ON_TOPIC, FakeLlm, _chat, use_llm, ws_with_doc  # noqa: F401
from test_ingest import _auth, fake_backends, two_users_with_workspaces  # noqa: F401

pytestmark = pytest.mark.skipif(not db_available(), reason="DATABASE_URL not reachable")

client = TestClient(app)


def _log(uid, ws):
    return client.get(f"/api/py/workspaces/{ws}/tool-calls", headers=_auth(uid)).json()[::-1]  # oldest first


def _tasks(uid, ws):
    return client.get(f"/api/py/workspaces/{ws}/tasks", headers=_auth(uid)).json()


def test_save_task_runs_and_is_logged(ws_with_doc, monkeypatch):
    uid, ws, _ = ws_with_doc
    fake = FakeLlm([("save_task", {"title": "Review the runbook", "due_date": "2026-10-01"})], "Saved the task.")
    use_llm(monkeypatch, fake)

    msg = _chat(uid, ws, "Save a task to review the runbook by Oct 1").json()["assistant_message"]
    assert msg["status"] == "done" and msg["content"] == "Saved the task."
    # Discord isn't configured in tests, so the save works and the notification fails (and says so).
    assert msg["tools"] == [
        {"name": "save_task", "status": "ok", "error": None},
        {"name": "notify_discord", "status": "error", "error": "Discord is not configured for this app"},
    ]

    [task] = _tasks(uid, ws)
    assert task["title"] == "Review the runbook" and task["due_date"] == "2026-10-01"
    assert task["source_message_id"] == msg["id"]
    entry, _ = _log(uid, ws)
    assert entry["status"] == "ok" and entry["result"]["task"]["title"] == "Review the runbook"

    # The model saw the tool result, including the notification outcome, on its second turn.
    response = fake.calls[1][1][-1].parts[0].function_response
    assert response.name == "save_task" and response.response["ok"] is True
    assert response.response["discord_notification"]["sent"] is False


@pytest.mark.parametrize(
    "args, problem",
    [
        ({}, "title: Field required"),
        ({"title": "x" * 201}, "title: String should have at most 200 characters"),
        ({"title": "ok", "due_date": "next tuesday"}, "due_date"),
        ({"title": "ok", "workspace_id": "00000000-0000-0000-0000-000000000000"}, "workspace_id: Extra inputs"),
    ],
)
def test_invalid_arguments_are_rejected_and_nothing_runs(ws_with_doc, monkeypatch, args, problem):
    uid, ws, _ = ws_with_doc
    fake = FakeLlm([("save_task", args)], "I couldn't save that task.")
    use_llm(monkeypatch, fake)

    msg = _chat(uid, ws, "Save a task please").json()["assistant_message"]
    assert msg["status"] == "done"
    assert _tasks(uid, ws) == []
    entry, notice = _log(uid, ws)
    assert entry["status"] == "rejected" and problem in entry["error"]
    assert notice["name"] == "notify_discord" and notice["args"]["saved"] is False
    assert fake.calls[1][1][-1].parts[0].function_response.response["ok"] is False


def test_unknown_tool_is_rejected(ws_with_doc, monkeypatch):
    uid, ws, _ = ws_with_doc
    use_llm(monkeypatch, FakeLlm([("delete_everything", {"confirm": True})], "I can't do that."))

    msg = _chat(uid, ws, "What is the codename?").json()["assistant_message"]
    assert msg["status"] == "done"
    [entry] = _log(uid, ws)
    assert entry["name"] == "delete_everything" and entry["status"] == "rejected"
    assert "Unknown tool" in entry["error"]


def test_side_effect_tools_need_the_users_intent(ws_with_doc, monkeypatch):
    """A plain question doesn't unlock save_task/send_discord_summary, whatever the model (or a
    document it read) wants. Only the user's own message can."""
    uid, ws, _ = ws_with_doc
    fake = FakeLlm([("save_task", {"title": "injected"})], "The codename is BLUE HERON [S1].")
    use_llm(monkeypatch, fake)

    _chat(uid, ws, "What is the codename?")
    assert fake.offered() == ["list_tasks", "search_documents"]  # read-only tools only
    assert _tasks(uid, ws) == []
    [entry] = _log(uid, ws)
    assert entry["status"] == "rejected" and "only available when the user" in entry["error"]


def test_multi_step_list_then_post_to_discord(ws_with_doc, monkeypatch):
    uid, ws, _ = ws_with_doc
    posted = []

    class Resp:
        status_code = 204

    monkeypatch.setattr(tools.httpx, "post", lambda url, json, timeout: posted.append(json) or Resp())
    monkeypatch.setattr(config.get_settings(), "discord_webhook_url", "https://discord.com/api/webhooks/1/x")
    # Seed a task directly so list_tasks has something to find.
    use_llm(monkeypatch, FakeLlm([("save_task", {"title": "Book Lisbon flights"})], "ok"))
    _chat(uid, ws, "add a task: book Lisbon flights")

    fake = FakeLlm(
        [("list_tasks", {"status": "open"})],
        [("send_discord_summary", {"summary": "Open tasks: Book Lisbon flights @everyone"})],
        "Posted your open tasks to Discord.",
    )
    use_llm(monkeypatch, fake)
    msg = _chat(uid, ws, "List my tasks and post a summary to Discord").json()["assistant_message"]

    assert [t["name"] for t in msg["tools"]] == ["list_tasks", "send_discord_summary"]
    assert all(t["status"] == "ok" for t in msg["tools"])
    assert len(fake.calls) == 3  # tool → tool → answer
    listed = fake.calls[1][1][-1].parts[0].function_response.response
    assert listed["result"]["tasks"][0]["title"] == "Book Lisbon flights"

    task_notice, body = posted
    assert "Task saved: Book Lisbon flights" in task_notice["content"]
    assert body["allowed_mentions"] == {"parse": []}
    assert "@everyone" not in body["content"]  # neutralised
    assert body["content"].startswith("**ws**")


def test_discord_not_configured_reports_error_without_crashing(ws_with_doc, monkeypatch):
    uid, ws, _ = ws_with_doc
    monkeypatch.setattr(config.get_settings(), "discord_webhook_url", "")
    use_llm(monkeypatch, FakeLlm([("send_discord_summary", {"summary": "hi"})], "Discord isn't set up."))
    msg = _chat(uid, ws, "post hi to discord").json()["assistant_message"]
    assert msg["status"] == "done" and msg["tools"][0]["status"] == "error"
    assert "not configured" in msg["tools"][0]["error"]


def test_step_and_call_limits_stop_a_looping_model(ws_with_doc, monkeypatch):
    uid, ws, _ = ws_with_doc
    fake = FakeLlm([("list_tasks", {}), ("list_tasks", {})])  # asks for 2 tools every turn, forever
    use_llm(monkeypatch, fake)
    msg = _chat(uid, ws, "show my tasks").json()["assistant_message"]
    assert msg["status"] == "done" and "allowed number of steps" in msg["content"]
    statuses = [t["status"] for t in msg["tools"]]
    assert statuses.count("ok") == 8 and statuses.count("rejected") == 2  # 5 turns x 2, capped at 8


def test_tools_only_touch_the_active_workspace(ws_with_doc, monkeypatch):
    uid, ws, (other_uid, other_ws) = ws_with_doc
    use_llm(monkeypatch, FakeLlm([("save_task", {"title": "Secret A task"})], "ok"))
    _chat(uid, ws, "save a task")

    fake = FakeLlm([("list_tasks", {"status": "all"})], "You have no tasks.")
    use_llm(monkeypatch, fake)
    monkeypatch.setattr(retrieval, "embed_query", lambda q: ON_TOPIC)
    _chat(other_uid, other_ws, "list my tasks")
    listed = fake.calls[1][1][-1].parts[0].function_response.response
    assert listed["result"] == {"tasks": [], "count": 0}
    assert client.get(f"/api/py/workspaces/{ws}/tasks", headers=_auth(other_uid)).status_code == 404
    assert client.get(f"/api/py/workspaces/{ws}/tool-calls", headers=_auth(other_uid)).status_code == 404


def test_search_documents_results_are_citable(ws_with_doc, monkeypatch):
    uid, ws, _ = ws_with_doc
    fake = FakeLlm([("search_documents", {"query": "leave policy"})], "Staff get 25 days [S1].")
    use_llm(monkeypatch, fake)
    msg = _chat(uid, ws, "How much leave?").json()["assistant_message"]
    result = fake.calls[1][1][-1].parts[0].function_response.response["result"]
    assert result["sources"] and all(s["id"].startswith("S") for s in result["sources"])
    assert [c["label"] for c in msg["citations"]] == ["S1"]


def _fake_discord(monkeypatch, status_code=204):
    posted = []

    class Resp:
        pass

    Resp.status_code = status_code
    monkeypatch.setattr(tools.httpx, "post", lambda url, json, timeout: posted.append(json) or Resp())
    monkeypatch.setattr(config.get_settings(), "discord_webhook_url", "https://discord.com/api/webhooks/1/x")
    return posted


def test_saved_task_is_announced_on_discord_once_per_answer(ws_with_doc, monkeypatch):
    uid, ws, _ = ws_with_doc
    posted = _fake_discord(monkeypatch)
    # The answer fails after the task is saved, so the user retries it.
    use_llm(monkeypatch, FakeLlm([("save_task", {"title": "Pay @everyone", "due_date": "2026-11-01"})],
                                 llm.LlmError("The AI service is rate-limited right now.")))
    failed = _chat(uid, ws, "save a task to pay invoices").json()["assistant_message"]
    assert failed["status"] == "failed"
    assert [(t["name"], t["status"]) for t in failed["tools"]] == [("save_task", "ok"), ("notify_discord", "ok")]

    [body] = posted
    assert body["content"] == "**ws** · ✅ Task saved: Pay @\u200beveryone (due 2026-11-01)"
    assert body["allowed_mentions"] == {"parse": []}

    fake = FakeLlm([("save_task", {"title": "Pay @everyone", "due_date": "2026-11-01"})], "Saved, team notified.")
    use_llm(monkeypatch, fake)
    retried = client.post(f"/api/py/workspaces/{ws}/messages/{failed['id']}/retry", headers=_auth(uid)).json()
    assert retried["status"] == "done"
    assert len(posted) == 1 and len(_tasks(uid, ws)) == 1  # no second task, no second announcement
    notice = fake.calls[1][1][-1].parts[0].function_response.response["discord_notification"]
    assert notice == {"status": "ok", "sent": True, "already_sent": True}


def test_failed_save_is_reported_to_user_and_discord(ws_with_doc, monkeypatch):
    uid, ws, _ = ws_with_doc
    posted = _fake_discord(monkeypatch)
    fake = FakeLlm([("save_task", {"title": "Renew contract", "due_date": "someday"})], "I couldn't save it.")
    use_llm(monkeypatch, fake)

    msg = _chat(uid, ws, "add a task to renew the contract").json()["assistant_message"]
    assert [(t["name"], t["status"]) for t in msg["tools"]] == [("save_task", "rejected"), ("notify_discord", "ok")]
    assert _tasks(uid, ws) == []
    [body] = posted
    assert body["content"].startswith("**ws** · ❌ Task not saved: Renew contract\nReason: Invalid arguments: due_date")
    response = fake.calls[1][1][-1].parts[0].function_response.response
    assert response["ok"] is False and response["discord_notification"]["sent"] is True


def test_discord_outage_does_not_undo_the_saved_task(ws_with_doc, monkeypatch):
    uid, ws, _ = ws_with_doc
    _fake_discord(monkeypatch, status_code=500)
    use_llm(monkeypatch, FakeLlm([("save_task", {"title": "Call the vendor"})], "Saved; Discord failed."))

    msg = _chat(uid, ws, "remind me to call the vendor").json()["assistant_message"]
    assert msg["tools"] == [
        {"name": "save_task", "status": "ok", "error": None},
        {"name": "notify_discord", "status": "error", "error": "Discord rejected the message (HTTP 500)"},
    ]
    assert [t["title"] for t in _tasks(uid, ws)] == ["Call the vendor"]


def test_injected_save_task_is_not_announced(ws_with_doc, monkeypatch):
    """A save_task the user didn't ask for is refused and never reaches Discord."""
    uid, ws, _ = ws_with_doc
    posted = _fake_discord(monkeypatch)
    use_llm(monkeypatch, FakeLlm([("save_task", {"title": "injected"})], "The codename is BLUE HERON [S1]."))
    _chat(uid, ws, "What is the codename?")
    assert posted == [] and [e["name"] for e in _log(uid, ws)] == ["save_task"]
