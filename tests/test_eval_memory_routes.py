"""Wiring: /api/eval/score + /api/memory/eval routes (P4/P5 consumers).

Stateless pure-compute endpoints, flag-gated (404 when off). Plus a focused check
of the room.py event-validation flag path (drop-invalid when on; byte-identical when off).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_LAB_MOCK_AGENTS", "1")
    from app.server.main import app

    return TestClient(app)


# --- eval route (P4) -------------------------------------------------------


def test_eval_score_404_when_disabled(client, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_EVAL_HARNESS", "0")
    res = client.post("/api/eval/score", json={"instances": []})
    assert res.status_code == 404


def test_eval_score_200_by_default(client, monkeypatch):
    monkeypatch.delenv("AGENT_LAB_EVAL_HARNESS", raising=False)
    res = client.post("/api/eval/score", json={"instances": []})
    assert res.status_code == 200


def test_eval_score_computes_when_on(client, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_EVAL_HARNESS", "1")
    body = {
        "instances": [
            {"result_map": {"t1": "pass"}, "f2p_ids": ["t1"], "p2p_ids": [], "status": "ok"},
            {"result_map": {"t1": "fail"}, "f2p_ids": ["t1"], "p2p_ids": [], "status": "ok"},
            {"result_map": {"t1": "pass"}, "f2p_ids": ["t1"], "p2p_ids": [], "status": "timeout"},
        ]
    }
    res = client.post("/api/eval/score", json=body)
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 3
    agg = data["aggregate"]
    assert agg["total"] == 3
    assert agg["resolved"] == 1
    assert agg["harness_failure_count"] == 1
    # harness excluded from denominator: 1 resolved / (3 - 1) = 0.5
    assert abs(agg["model_resolved_rate"] - 0.5) < 1e-9


# --- memory route (P5) -----------------------------------------------------


def test_memory_eval_404_when_disabled(client, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_EVENT_MEMORY", "0")
    res = client.post("/api/memory/eval", json={"ops": []})
    assert res.status_code == 404


def test_memory_eval_200_by_default(client, monkeypatch):
    monkeypatch.delenv("AGENT_LAB_EVENT_MEMORY", raising=False)
    res = client.post("/api/memory/eval", json={"ops": []})
    assert res.status_code == 200


def test_memory_eval_stateless_compute_when_on(client, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_EVENT_MEMORY", "1")
    body = {
        "ops": [
            {"op": "put", "namespace": "b", "key": "y", "value": {"v": 2}},
            {"op": "put", "namespace": "a", "key": "x", "value": 1},
            {"op": "put", "namespace": "a", "key": "z", "value": 3},
            {"op": "delete", "namespace": "a", "key": "z"},
        ]
    }
    res = client.post("/api/memory/eval", json=body)
    assert res.status_code == 200
    data = res.json()
    assert data["namespaces"] == ["a", "b"]  # sorted
    assert data["keys_by_namespace"] == {"a": ["x"], "b": ["y"]}  # z deleted, sorted


def test_memory_eval_no_cross_request_state(client, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_EVENT_MEMORY", "1")
    client.post("/api/memory/eval", json={"ops": [{"op": "put", "namespace": "n", "key": "k", "value": 1}]})
    # second request with empty ops => fresh store, nothing leaks from the first
    res = client.post("/api/memory/eval", json={"ops": []})
    assert res.json()["namespaces"] == []


def test_memory_eval_unknown_op_400(client, monkeypatch):
    monkeypatch.setenv("AGENT_LAB_EVENT_MEMORY", "1")
    res = client.post("/api/memory/eval", json={"ops": [{"op": "frobnicate", "namespace": "n", "key": "k"}]})
    assert res.status_code == 400


# --- room.py event-validation flag path (P5 seam B) ------------------------


def test_room_event_validation_flag_path(monkeypatch):
    """Mirror room.py on_event gate: AGENT_LAB_EVENT_VALIDATE off (default) => always append; on => drop invalid."""
    from agent_lab.event_schema import event_validation_enabled, validate_event

    appended: list[tuple[str, dict]] = []

    def fake_append(_folder, typ, payload):
        appended.append((typ, payload))

    def on_event(folder, typ, payload):
        # replicates room.py on_event live-log branch logic
        if folder is not None:
            if event_validation_enabled():
                ok, _ = validate_event({"ts": "x", "type": typ, **payload})
                if not ok:
                    return
            fake_append(folder, typ, payload)

    # DEFAULT (EVENT_VALIDATE unset): no drop — even an unknown type is appended
    # (byte-identical legacy behavior; the writer itself drops unknowns later).
    monkeypatch.delenv("AGENT_LAB_EVENT_VALIDATE", raising=False)
    on_event("f", "totally_unknown", {"a": 1})
    assert appended == [("totally_unknown", {"a": 1})]

    appended.clear()
    # EVENT_VALIDATE=1: valid LIVE type passes; unknown type dropped before append.
    monkeypatch.setenv("AGENT_LAB_EVENT_VALIDATE", "1")
    on_event("f", "agent_start", {"agent": "x"})
    on_event("f", "totally_unknown", {"a": 1})
    assert appended == [("agent_start", {"agent": "x"})]
