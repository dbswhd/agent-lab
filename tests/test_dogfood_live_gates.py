"""Live mid-gate driver — option picking + pause policy (no live API)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "dogfood_live_gates.py"


def _load():
    scripts = str(_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location("dogfood_live_gates", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pick_question_prefers_default() -> None:
    mod = _load()
    item = {
        "options": [
            {"id": "a", "label": "A"},
            {"id": "b", "label": "B", "default": True},
        ]
    }
    assert mod._pick_question_selected(item) == ["b"]


def test_pick_question_falls_back_to_first() -> None:
    mod = _load()
    item = {"options": [{"id": "x"}, {"id": "y"}]}
    assert mod._pick_question_selected(item) == ["x"]


def test_pick_question_empty_returns_none() -> None:
    mod = _load()
    assert mod._pick_question_selected({"options": []}) is None
    assert mod._pick_question_selected({}) is None


def test_resolve_inbox_pauses_harness_patch() -> None:
    mod = _load()
    out = mod._resolve_inbox(
        "sess",
        {"id": "i1", "kind": "harness_patch", "status": "pending"},
        freeform_note=None,
    )
    assert out["paused"] is True
    assert "harness_patch" in str(out.get("reason"))


def test_resolve_inbox_auto_build(monkeypatch) -> None:
    mod = _load()
    calls: list[tuple] = []

    def fake_json(method, path, body=None, **kwargs):
        calls.append((method, path, body))
        return {"ok": True}

    monkeypatch.setattr(mod, "_json_request", fake_json)
    out = mod._resolve_inbox(
        "sess",
        {"id": "b1", "kind": "build", "source": "mcp_propose_build", "status": "pending"},
        freeform_note=None,
    )
    assert out["ok"] is True
    assert out["action"] == "inbox_resolve"
    assert calls[0][2]["decision"] == "go"


def test_resolve_inbox_auto_question(monkeypatch) -> None:
    mod = _load()

    def fake_json(method, path, body=None, **kwargs):
        return {"ok": True}

    monkeypatch.setattr(mod, "_json_request", fake_json)
    out = mod._resolve_inbox(
        "sess",
        {
            "id": "q1",
            "kind": "question",
            "status": "pending",
            "options": [{"id": "opt-a"}, {"id": "opt-b"}],
        },
        freeform_note=None,
    )
    assert out["ok"] is True


def test_normalize_session_id() -> None:
    mod = _load()
    assert mod._normalize_session_id("sessions/abc") == "abc"
    assert mod._normalize_session_id("abc") == "abc"
