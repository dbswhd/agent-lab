from __future__ import annotations

import pytest


@pytest.mark.integration
def test_room_modes_catalog() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.server.main import app

    client = TestClient(app)
    res = client.get("/api/room/modes")
    assert res.status_code == 200
    body = res.json()
    mode_ids = {row["id"] for row in body.get("modes") or []}
    assert mode_ids == {"quick", "team", "loop", "divergence"}
    divergence_mode = next(row for row in body["modes"] if row["id"] == "divergence")
    assert divergence_mode["execute_loop_on_approve"] is False
    assert divergence_mode["divergence"] is True
    loop_mode = next(row for row in body["modes"] if row["id"] == "loop")
    assert loop_mode["execute_loop_on_approve"] is True
    team_mode = next(row for row in body["modes"] if row["id"] == "team")
    assert team_mode["execute_loop_on_approve"] is False
    assert body["legacy_migration"]["verified"] == "loop"
    assert body["verified_routing"]["legacy_verified_api"]["in_turn_verified_loop"] is True
    loop_mode = next(row for row in body["modes"] if row["id"] == "loop")
    assert loop_mode.get("budget", {}).get("max_cost_tier") == "high"
