"""Actual HTTP commands and Room Scribe persistence, with only provider calls stubbed."""

from __future__ import annotations

import pytest

from test_ideation_api import client as client_fixture, _make_session
from agent_lab.run.meta import read_run_meta

client = client_fixture


def test_http_selection_conditions_concept_plan_and_refresh(client, tmp_path, monkeypatch):
    folder = _make_session(tmp_path)
    url = f"/api/sessions/{folder.name}/ideation"

    def command(verb, **fields):
        revision = client.get(url).json()["revision"]
        res = client.patch(url, json={"command": verb, "expected_revision": revision, **fields})
        assert res.status_code == 200, res.text
        return res.json()

    command("select", option_id="opt-0-cursor")
    command("condition", constraints=["iOS 전용", "2주 안에"], reason="범위 축소")
    command("concept", concept={"summary": "마감 알림과 한 줄 복습", "mvp": "한 과목"})
    state = client.get(url).json()["ideation"]
    assert state["brief"]["constraints"] == ["iOS 전용", "2주 안에"]
    assert state["concept"]["mvp"] == "한 과목"
    assert state["decisions"][-1]["kind"] == "condition"


@pytest.mark.parametrize(
    "verb,fields",
    [
        ("condition", {"constraints": []}),
        ("concept", {"concept": {"summary": "수정"}}),
        ("plan", {}),
    ],
)
def test_new_commands_reject_stale_revision(client, tmp_path, verb, fields):
    folder = _make_session(tmp_path)
    res = client.patch(
        f"/api/sessions/{folder.name}/ideation",
        json={
            "command": verb,
            "expected_revision": 999,
            **fields,
        },
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "stale_revision"
    assert read_run_meta(folder)["ideation"]["revision"] == 0
