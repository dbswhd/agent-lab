"""Live uvicorn에 HTTP로 dual-write route를 exercise (operational ledger)."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SAMPLE_PLAN = """# Cohort op

## 지금 실행

1. Add marker
   - 무엇을: implement marker
   - 어디서: `src/marker.py`
   - 검증: `pytest tests/test_marker.py`
"""


def _http_json(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw.strip() else {"detail": raw[:300]}
        except json.JSONDecodeError:
            payload = {"detail": raw[:300]}
        return exc.code, payload


def _init_session(sessions_root: Path, session_id: str) -> Path:
    folder = sessions_root / session_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "topic.txt").write_text(session_id, encoding="utf-8")
    (folder / "chat.jsonl").write_text("", encoding="utf-8")
    (folder / "plan.md").write_text(SAMPLE_PLAN, encoding="utf-8")
    (folder / "run.json").write_text(json.dumps({"topic": session_id}), encoding="utf-8")
    return folder


def run_live_routes(base_url: str, sessions_root: Path, session_ids: list[str]) -> dict[str, Any]:
    from agent_lab.plan.workflow_state import set_plan_workflow_phase

    base = base_url.rstrip("/")
    rows: list[dict[str, Any]] = []
    for session_id in session_ids:
        folder = _init_session(sessions_root, session_id)
        set_plan_workflow_phase(folder, "HUMAN_PENDING")
        status, body = _http_json("POST", f"{base}/api/sessions/{session_id}/plan/approve", {"goal": "cohort ship"})
        read_status, read_model = _http_json("GET", f"{base}/api/sessions/{session_id}/mission/read-model")
        rows.append(
            {
                "session_id": session_id,
                "plan_approve_status": status,
                "mirrored": (body.get("mission_dual_write") or {}).get("mirrored"),
                "dual_write_reason": (body.get("mission_dual_write") or {}).get("reason"),
                "read_model_status": read_status,
                "read_model_migrated": read_model.get("migrated"),
                "read_model_state": read_model.get("state"),
            }
        )
    health_status, health = _http_json("GET", f"{base}/api/health/daemon")
    pass_all = all(r["plan_approve_status"] == 200 and r["mirrored"] is True and r["read_model_migrated"] is True for r in rows)
    return {
        "kind": "live_route_cohort",
        "base_url": base,
        "session_count": len(session_ids),
        "pass": pass_all,
        "health_status": health_status,
        "dual_write_counters": health.get("dual_write"),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--prefix", default="dw-cohort-op")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()
    session_ids = [f"{args.prefix}-{index:02d}" for index in range(1, args.count + 1)]
    report = run_live_routes(args.base_url, args.sessions, session_ids)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        args.report.write_text(text + "\n", encoding="utf-8")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
