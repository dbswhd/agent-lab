"""Wave B UI 재검토용: `/mission/read-model`이 HumanInboxPanel/WorkspaceCard가 legacy
`human_inbox[]`/`plan_workflow` 없이도 렌더링할 수 있을 만큼 충분한지 실측한다.

m6-precheck-retire-scope-2026-07-14.md item 2/3이 남긴 질문:
  "Inbox rows: Cannot delete row writer until Decision/inbox read-model rebuilds
   prompt/options" — 즉 legacy `human_inbox[]` row writer를 지우면 어떤 inbox item이
   placeholder("Human inbox item unavailable", options=[])로 깨지는지 아직 정량화되지
   않았다.

이 스크립트는 production HTTP route(TestClient)로 실제 lifecycle을 밟은 뒤, 매 단계에서
`/mission/read-model`의 `inbox_items[]`를 검사해:
  - `mission_gate_status`별 분포 (open_gate / missing_row / unrelated / terminal_orphan)
  - `prompt`/`options`가 채워진 실비율 (legacy row 없이 journal-only projection이면
    빈 placeholder가 몇 건인지)
를 기록한다. GO/NO-GO 판정을 내리지 않는다 — m6-precheck의 NO-GO 판정을 갱신할 근거
데이터만 남긴다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SAMPLE_PLAN = """# Demo feature

## 지금 실행

1. Add widget
   - 무엇을: implement widget
   - 어디서: `src/widget.py`
   - 검증: `pytest tests/test_widget.py`
"""


def _client(sessions_root: Path) -> Any:
    from fastapi.testclient import TestClient
    from agent_lab.session import paths as session_paths
    from agent_lab import session as session_module
    import app.server.deps as deps_mod
    from app.server.main import create_app

    session_paths.SESSIONS_DIR = sessions_root
    session_module.SESSIONS_DIR = sessions_root
    deps_mod.SESSIONS_DIR = sessions_root
    return TestClient(create_app(bootstrap=False))


def _read_model(client: Any, session_id: str) -> dict[str, Any]:
    response = client.get(f"/api/sessions/{session_id}/mission/read-model")
    response.raise_for_status()
    return response.json()


def _init_session(sessions_root: Path, name: str) -> Path:
    folder = sessions_root.resolve() / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "topic.txt").write_text(name, encoding="utf-8")
    (folder / "chat.jsonl").write_text("", encoding="utf-8")
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    (folder / "run.json").write_text(json.dumps({"topic": name}), encoding="utf-8")
    return folder


def _item_ui_readiness(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    ui_ready = 0
    would_degrade_without_legacy_row = 0
    for item in items:
        status = str(item.get("mission_gate_status") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        # missing_row/terminal_orphan are exactly the placeholder branches in
        # read_model._joined_inbox_items — they always carry a synthetic
        # "Human inbox item unavailable" prompt, so a naive "has prompt" check
        # would wrongly count them as UI-ready. The status tag itself is the
        # real signal: it fires only when no legacy human_inbox row backed the gate.
        degraded = status in {"missing_row", "terminal_orphan"}
        has_options = isinstance(item.get("options"), list) and bool(item.get("options"))
        if not degraded and has_options:
            ui_ready += 1
        if degraded:
            would_degrade_without_legacy_row += 1
    return {
        "total": len(items),
        "by_mission_gate_status": by_status,
        "ui_ready_count": ui_ready,
        "would_degrade_without_legacy_row_writer": would_degrade_without_legacy_row,
    }


def _scenario_plan_approve_then_inbox(client: Any, sessions_root: Path, name: str) -> dict[str, Any]:
    from agent_lab.plan.workflow_state import set_plan_workflow_phase

    folder = _init_session(sessions_root, name)
    set_plan_workflow_phase(folder, "HUMAN_PENDING")
    approve = client.post(f"/api/sessions/{name}/plan/approve", json={"goal": "ship widget"})
    after_approve = _read_model(client, name)

    from agent_lab.human_inbox import create_inbox_item
    from agent_lab.mission.application import MissionApplication
    from agent_lab.mission.kernel import BlockExecution

    MissionApplication(folder, "ship widget").repository.dispatch(BlockExecution("human decision"))
    item = create_inbox_item(
        folder,
        kind="question",
        source="ui-read-model-cohort",
        prompt="Proceed with widget rollout?",
        options=[{"id": "go", "label": "Go"}, {"id": "hold", "label": "Hold"}],
    )
    after_gate_open = _read_model(client, name)

    resolve = client.post(f"/api/sessions/{name}/inbox/{item['id']}/resolve", json={"decision": "go"})
    after_resolve = _read_model(client, name)

    return {
        "session_id": name,
        "plan_approve_status": approve.status_code,
        "after_approve_read_model_state": after_approve.get("state"),
        "after_gate_open_inbox_items": _item_ui_readiness(after_gate_open.get("inbox_items") or []),
        "inbox_resolve_status": resolve.status_code,
        "after_resolve_read_model_state": after_resolve.get("state"),
        "after_resolve_inbox_items": _item_ui_readiness(after_resolve.get("inbox_items") or []),
    }


def _scenario_gate_without_legacy_row(client: Any, sessions_root: Path, name: str) -> dict[str, Any]:
    """Mission opens a gate but no legacy `human_inbox` row exists for it — the
    exact case the m6-precheck flagged: what does the read-model hand the UI?
    """
    from agent_lab.plan.workflow_state import set_plan_workflow_phase
    from agent_lab.mission.application import MissionApplication
    from agent_lab.mission.kernel import OpenExecutionGate

    folder = _init_session(sessions_root, name)
    set_plan_workflow_phase(folder, "HUMAN_PENDING")
    client.post(f"/api/sessions/{name}/plan/approve", json={"goal": "ship widget"})
    MissionApplication(folder, "ship widget").repository.dispatch(
        OpenExecutionGate(gate_id="gate-no-row-1", kind="question", reason="human decision, no inbox row")
    )
    read_model = _read_model(client, name)
    items = read_model.get("inbox_items") or []
    return {
        "session_id": name,
        "read_model_state": read_model.get("state"),
        "inbox_items": _item_ui_readiness(items),
        "raw_items": items,
    }


def run_cohort(sessions_root: Path, *, prefix: str = "ui-read-model") -> dict[str, Any]:
    sessions_root.mkdir(parents=True, exist_ok=True)
    prefix = prefix.strip() or "ui-read-model"

    session_ids = [f"{prefix}-01-approve-inbox", f"{prefix}-02-approve-inbox", f"{prefix}-03-gate-no-row"]

    os.environ["AGENT_LAB_MISSION_UI_READ_MODEL"] = "1"
    # UI_READ_MODEL only controls what the frontend *reads*; the Mission journal
    # itself only advances through HTTP routes when the dual-write bridge is on
    # AND the session is in the cohort allowlist (production safety gate).
    os.environ["AGENT_LAB_MISSION_DUAL_WRITE"] = "1"
    os.environ["AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS"] = ",".join(session_ids)
    os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
    client = _client(sessions_root)

    rows: list[dict[str, Any]] = []
    rows.append(_scenario_plan_approve_then_inbox(client, sessions_root, session_ids[0]))
    rows.append(_scenario_plan_approve_then_inbox(client, sessions_root, session_ids[1]))

    gate_only = _scenario_gate_without_legacy_row(client, sessions_root, session_ids[2])

    legacy_row_dependent = gate_only["inbox_items"]["would_degrade_without_legacy_row_writer"] > 0

    return {
        "sessions_root": str(sessions_root),
        "scenarios": rows,
        "gate_without_legacy_row": gate_only,
        "finding_legacy_row_writer_still_required": legacy_row_dependent,
        "note": (
            "legacy human_inbox row writer가 반드시 필요하면(finding=True), "
            "m6-precheck-retire-scope-2026-07-14.md의 'Inbox rows: Cannot delete row writer' "
            "판정이 여전히 유효하다는 실측 근거."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=Path, required=True, help="scratch sessions directory")
    args = parser.parse_args()
    report = run_cohort(args.sessions)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
