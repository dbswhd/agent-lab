"""Layer B: MCP elicitation attempt for ``ask_human``, capability-gated with a
safe fallback to the existing ``create_mcp_question_and_wait`` poll flow.

All tests exercise ``src/agent_lab/inbox/mcp_server.py`` functions directly —
no real Codex/Claude/Cursor process, no real MCP transport — matching the
existing config-building-function-direct style already used for
``build_codex_inbox_mcp_config_args`` / ``build_claude_inbox_mcp_overlay``.

``ask_human``/``_try_elicit_ask_human`` are ``async def`` (required to
``await ctx.elicit(...)``); this repo has no pytest-asyncio, so — matching
``tests/test_room_resume_stream.py``'s ``_drain`` helper — coroutines are
driven with a small ``asyncio.run`` wrapper instead of ``async def test_``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Coroutine

import pytest

from agent_lab.human_inbox import find_inbox_item, has_pending_question
from agent_lab.inbox import mcp_server
from agent_lab.run.meta import read_run_meta


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


class _StubSession:
    def __init__(self, *, supports: bool) -> None:
        self._supports = supports

    def check_client_capability(self, _capability: object) -> bool:
        return self._supports


class _StubContext:
    def __init__(
        self,
        *,
        supports: bool = True,
        elicit_result: object | None = None,
        elicit_error: Exception | None = None,
    ) -> None:
        self.session = _StubSession(supports=supports)
        self._elicit_result = elicit_result
        self._elicit_error = elicit_error

    async def elicit(self, _message: str, _schema: object) -> object:
        if self._elicit_error is not None:
            raise self._elicit_error
        return self._elicit_result


def _accepted(choice: str, note: str | None = None):
    from mcp.server.elicitation import AcceptedElicitation

    return AcceptedElicitation(data=mcp_server._AskHumanChoice(choice=choice, note=note))


def _options() -> list[dict[str, str]]:
    return [{"id": "a", "label": "Option A"}, {"id": "b", "label": "Option B"}]


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    d = tmp_path / "sess"
    d.mkdir()
    (d / "chat.jsonl").write_text("", encoding="utf-8")
    return d


def test_elicit_returns_none_when_client_lacks_capability(folder: Path):
    ctx = _StubContext(supports=False)
    result = _run(mcp_server._try_elicit_ask_human(ctx, folder, "Scope?", _options(), None))
    assert result is None
    assert has_pending_question(read_run_meta(folder)) is False


def test_elicit_returns_none_on_mcp_error(folder: Path):
    from mcp.shared.exceptions import McpError
    from mcp import types as mcp_types

    err = McpError(mcp_types.ErrorData(code=1, message="timed out"))
    ctx = _StubContext(supports=True, elicit_error=err)
    result = _run(mcp_server._try_elicit_ask_human(ctx, folder, "Scope?", _options(), None))
    assert result is None


def test_elicit_returns_none_on_decline(folder: Path):
    ctx = _StubContext(supports=True, elicit_result=SimpleNamespace(action="decline"))
    result = _run(mcp_server._try_elicit_ask_human(ctx, folder, "Scope?", _options(), None))
    assert result is None


def test_elicit_returns_none_on_cancel(folder: Path):
    ctx = _StubContext(supports=True, elicit_result=SimpleNamespace(action="cancel"))
    result = _run(mcp_server._try_elicit_ask_human(ctx, folder, "Scope?", _options(), None))
    assert result is None


def test_elicit_returns_none_on_invalid_choice(folder: Path):
    ctx = _StubContext(supports=True, elicit_result=_accepted("not-an-option"))
    result = _run(mcp_server._try_elicit_ask_human(ctx, folder, "Scope?", _options(), None))
    assert result is None
    # No half-created item left behind for an invalid choice.
    assert read_run_meta(folder).get("human_inbox", []) == []


def test_elicit_accept_resolves_item_and_skips_poll_wait(folder: Path):
    ctx = _StubContext(supports=True, elicit_result=_accepted("a", note="go with a"))
    result = _run(mcp_server._try_elicit_ask_human(ctx, folder, "Scope?", _options(), None))

    assert result is not None
    assert result["selected"] == ["a"]
    assert result["freeform"] == "go with a"

    run = read_run_meta(folder)
    item = find_inbox_item(run, result["inbox_item_id"])
    assert item is not None
    assert item["status"] == "resolved"
    assert item["resolved_by"] == "human"
    assert item["source"] == "mcp_ask_human"


def test_ask_human_falls_back_when_elicit_unavailable(folder: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_SESSION_FOLDER", str(folder))
    called: dict[str, object] = {}

    def fake_create_mcp_question_and_wait(_folder, **kwargs):
        called.update(kwargs)
        return {"selected": ["a"], "freeform": None, "inbox_item_id": "stub", "resolved_at": "x"}

    monkeypatch.setattr(
        "agent_lab.human_inbox.create_mcp_question_and_wait",
        fake_create_mcp_question_and_wait,
    )

    ctx = _StubContext(supports=False)
    result = _run(mcp_server.ask_human(question="Scope?", options=_options(), multiSelect=False, ctx=ctx))

    assert result["selected"] == ["a"]
    assert called["question"] == "Scope?"


def test_ask_human_uses_elicit_and_skips_fallback_when_accepted(folder: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_SESSION_FOLDER", str(folder))

    def fail_if_called(_folder, **_kwargs):
        raise AssertionError("create_mcp_question_and_wait must not be called on elicit accept")

    monkeypatch.setattr(
        "agent_lab.human_inbox.create_mcp_question_and_wait",
        fail_if_called,
    )

    ctx = _StubContext(supports=True, elicit_result=_accepted("b"))
    result = _run(mcp_server.ask_human(question="Scope?", options=_options(), multiSelect=False, ctx=ctx))

    assert result["selected"] == ["b"]


def test_ask_human_policy_check_runs_regardless_of_elicit_path(folder: Path, monkeypatch: pytest.MonkeyPatch):
    """Regression guard: a pending question must still block a second
    ask_human call even when an elicitation-capable client is attached —
    the policy check must never be bypassed by the elicit shortcut."""
    monkeypatch.setenv("AGENT_LAB_SESSION_FOLDER", str(folder))
    monkeypatch.setenv("AGENT_LAB_INBOX_CALLER_AGENT", "claude")
    monkeypatch.setenv("AGENT_LAB_INBOX_POLICY_LANE", "discuss")

    from agent_lab.human_inbox import create_inbox_item

    create_inbox_item(
        folder,
        kind="question",
        source="mcp_ask_human",
        prompt="already pending",
        options=_options(),
    )

    ctx = _StubContext(supports=True, elicit_result=_accepted("a"))
    with pytest.raises(ValueError, match="pending Human Inbox question"):
        _run(mcp_server.ask_human(question="Another?", options=_options(), multiSelect=False, ctx=ctx))


def test_ask_human_multiselect_skips_elicit_by_design(folder: Path, monkeypatch: pytest.MonkeyPatch):
    """The elicit schema is a single flat ``choice: str`` field — it cannot
    represent a multi-select answer, so multiSelect calls always go straight
    to the poll fallback, even with a capable client attached."""
    monkeypatch.setenv("AGENT_LAB_SESSION_FOLDER", str(folder))
    called = {"hit": False}

    def fake_create_mcp_question_and_wait(_folder, **kwargs):
        called["hit"] = True
        called.update(kwargs)
        return {"selected": ["a", "b"], "freeform": None, "inbox_item_id": "stub", "resolved_at": "x"}

    monkeypatch.setattr(
        "agent_lab.human_inbox.create_mcp_question_and_wait",
        fake_create_mcp_question_and_wait,
    )

    ctx = _StubContext(supports=True, elicit_result=_accepted("a"))
    result = _run(mcp_server.ask_human(question="Scope?", options=_options(), multiSelect=True, ctx=ctx))

    assert called["hit"] is True
    assert result["selected"] == ["a", "b"]
