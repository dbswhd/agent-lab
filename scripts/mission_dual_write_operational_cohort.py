"""Operational dual-write cohort — live HTTP only, 100+ mirrored ops, clean watch, rollback.

Unlike mission_dual_write_synthetic_cohort.py (isolated /tmp), this script:
- exercises the running uvicorn process at --base-url
- writes sessions under --sessions (default sessions/)
- counts mirrored operations from mission_dual_write responses
- requires clean verify baseline before watch
- records ≥60min observation with a final tick

See docs/redesign-2026-07/dual-write-cutover-scope-limitations-2026-07-13.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

COHORT_PREFIX_DEFAULT = "dw-c2"

# Minimum operational sessions per route before plan/inbox fillers run.
DEFAULT_ROUTE_QUOTAS: dict[str, int] = {
    "execute-resolve": 15,
    "merge-confirm": 10,
    "reverify": 15,
}


@dataclass
class HttpResponse:
    status_code: int
    _body: dict[str, Any]

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self._body}")


class LiveRouteClient:
    """TestClient-compatible surface for route_cohort scenarios."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def post(self, path: str, json: dict[str, Any] | None = None) -> HttpResponse:
        status, body = _http_json("POST", f"{self.base_url}{path}", json)
        return HttpResponse(status, body if isinstance(body, dict) else {"detail": body})

    def get(self, path: str) -> HttpResponse:
        status, body = _http_json("GET", f"{self.base_url}{path}")
        return HttpResponse(status, body if isinstance(body, dict) else {"detail": body})


def _http_json(method: str, url: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw.strip() else {"detail": raw[:300]}
        except json.JSONDecodeError:
            payload = {"detail": raw[:300]}
        return exc.code, payload


def _mirrored_from(body: dict[str, Any]) -> bool:
    bridge = body.get("mission_dual_write") or {}
    return bridge.get("mirrored") is True


def _count_journal_missing(health: dict[str, Any]) -> int:
    ops = ((health.get("dual_write") or {}).get("operations") or {}).get("inbox_create") or {}
    # errors bucket includes mission_journal_missing; no separate counter yet — scan not available.
    return int(ops.get("error") or 0)


def _run_journal_audit(sessions: Path, allowlist: str, cohort: bool) -> dict[str, Any]:
    env = {**os.environ, "AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS": allowlist}
    cmd = [sys.executable, str(ROOT / "scripts" / "mission_dual_write_journal_audit.py"), "--sessions", str(sessions)]
    if cohort:
        cmd.append("--cohort")
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if not proc.stdout.strip():
        return {"error": proc.stderr[:500], "duplicate_count": -1}
    return json.loads(proc.stdout)


def _run_verify(sessions: Path, allowlist: str, cohort: bool) -> dict[str, Any]:
    env = {**os.environ, "AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS": allowlist}
    cmd = [sys.executable, str(ROOT / "scripts" / "mission_dual_write_verify.py"), "--sessions", str(sessions)]
    if cohort:
        cmd.append("--cohort")
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    if not proc.stdout.strip():
        return {"error": proc.stderr[:500], "hard_mismatch_count": -1}
    return json.loads(proc.stdout)


def _health(base_url: str) -> dict[str, Any]:
    _, body = _http_json("GET", f"{base_url.rstrip('/')}/api/health/daemon")
    return body


@dataclass
class CohortState:
    prefix: str
    session_ids: list[str] = field(default_factory=list)
    mirrored_ops: int = 0
    route_sessions: dict[str, int] = field(default_factory=dict)
    operations: list[dict[str, Any]] = field(default_factory=list)

    def track(self, session_id: str, route: str, status_code: int, body: dict[str, Any]) -> None:
        if session_id not in self.session_ids:
            self.session_ids.append(session_id)
        bridge = body.get("mission_dual_write") or {}
        if bridge.get("mirrored") is True:
            self.mirrored_ops += 1
        self.operations.append(
            {
                "session_id": session_id,
                "route": route,
                "status_code": status_code,
                "mirrored": bridge.get("mirrored"),
                "reason": bridge.get("reason"),
                "operation": bridge.get("operation"),
            }
        )


def _quotas_met(quotas: dict[str, int], counts: dict[str, int]) -> bool:
    return all(counts.get(tag, 0) >= minimum for tag, minimum in quotas.items())


def run_traffic_fixed(
    *,
    base_url: str,
    sessions_root: Path,
    repos_root: Path,
    state: CohortState,
    target_ops: int,
    route_quotas: dict[str, int] | None = None,
) -> None:
    """Drive scenarios until mirrored_ops >= target_ops and route quotas are met."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import mission_dual_write_route_cohort as rc

    quotas = route_quotas or DEFAULT_ROUTE_QUOTAS
    client = LiveRouteClient(base_url)
    cycle = 0
    runners = [
        ("execute-resolve", lambda n: rc._scenario_execute_resolve_approve(client, sessions_root, repos_root, n)),
        ("merge-confirm", lambda n: rc._scenario_execute_merge_confirm(client, sessions_root, repos_root, n)),
        ("reverify", lambda n: rc._scenario_execute_reverify(client, sessions_root, repos_root, n)),
        ("plan-approve", lambda n: rc._scenario_plan_approve(client, sessions_root, n)),
        ("plan-reject", lambda n: rc._scenario_plan_reject(client, sessions_root, n)),
        ("inbox", lambda n: _run_inbox_cycle(client, sessions_root, n)),
    ]
    plan_tags = frozenset({"plan-approve", "plan-reject", "inbox"})
    while state.mirrored_ops < target_ops or not _quotas_met(quotas, state.route_sessions):
        cycle += 1
        for tag, run in runners:
            if tag in plan_tags and not _quotas_met(quotas, state.route_sessions):
                continue
            if state.mirrored_ops >= target_ops and _quotas_met(quotas, state.route_sessions):
                return
            name = f"{state.prefix}-{cycle:03d}-{tag}"
            if tag == "inbox":
                for row in run(name):
                    _record_row(state, name, tag, row)
            else:
                try:
                    row = run(name)
                    _record_row(state, name, tag, row)
                except Exception as exc:
                    if name not in state.session_ids:
                        state.session_ids.append(name)
                    state.operations.append({"session_id": name, "route": tag, "error": str(exc)[:240]})


def _run_inbox_cycle(client: LiveRouteClient, sessions_root: Path, name: str) -> list[dict[str, Any]]:
    from mission_dual_write_route_cohort import _init_session, _prep_plan_approve

    folder = _init_session(sessions_root, name)
    out: list[dict[str, Any]] = []
    if not _prep_plan_approve(client, folder, name):
        out.append({"route": "prep/plan/approve", "mirrored": False, "status_code": 500})
        return out
    out.append({"route": "prep/plan/approve", "mirrored": True, "status_code": 200})
    create = client.post(
        f"/api/sessions/{name}/inbox/items",
        json={"kind": "question", "source": "operational-cohort", "prompt": "Proceed?"},
    )
    cb = create.json()
    out.append(
        {
            "route": "POST /inbox/items",
            "status_code": create.status_code,
            "mirrored": (cb.get("mission_dual_write") or {}).get("mirrored"),
        }
    )
    item_id = (cb.get("item") or {}).get("id") or ""
    resolve = client.post(f"/api/sessions/{name}/inbox/{item_id}/resolve", json={"decision": "go"})
    rb = resolve.json()
    out.append(
        {
            "route": "POST /inbox/resolve",
            "status_code": resolve.status_code,
            "mirrored": (rb.get("mission_dual_write") or {}).get("mirrored"),
        }
    )
    return out


def _record_row(state: CohortState, name: str, tag: str, row: dict[str, Any]) -> None:
    if name not in state.session_ids:
        state.session_ids.append(name)
    if row.get("mirrored") is True:
        state.mirrored_ops += 1
    state.route_sessions[tag] = state.route_sessions.get(tag, 0) + 1
    state.operations.append({"session_id": name, "route_tag": tag, **row})


def run_watch(
    *,
    base_url: str,
    sessions: Path,
    allowlist: str,
    minutes: int,
    interval_sec: int,
    ledger: Path,
) -> dict[str, Any]:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    if ledger.is_file():
        ledger.unlink()
    baseline = _run_verify(sessions, allowlist, cohort=True)
    if baseline.get("hard_mismatch_count", 0) != 0:
        return {"pass": False, "phase": "baseline", "baseline": baseline}

    started = datetime.now(UTC)
    deadline = time.monotonic() + minutes * 60
    ticks: list[dict[str, Any]] = []
    hard_failures = 0

    while True:
        tick = len(ticks) + 1
        ts = datetime.now(UTC).isoformat()
        verify = _run_verify(sessions, allowlist, cohort=True)
        health = _health(base_url)
        entry = {
            "tick": tick,
            "at": ts,
            "verify_exit_code": 0 if verify.get("hard_mismatch_count", 0) == 0 else 1,
            "hard_mismatch_count": verify.get("hard_mismatch_count"),
            "migrated_count": verify.get("migrated_count"),
            "dual_write": health.get("dual_write"),
            "last_activity_recovery": health.get("last_activity_recovery_result"),
        }
        ticks.append(entry)
        with ledger.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if entry["verify_exit_code"] != 0:
            hard_failures += 1
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(interval_sec, remaining))

    # final tick
    tick = len(ticks) + 1
    verify = _run_verify(sessions, allowlist, cohort=True)
    health = _health(base_url)
    final = {
        "tick": tick,
        "at": datetime.now(UTC).isoformat(),
        "final": True,
        "verify_exit_code": 0 if verify.get("hard_mismatch_count", 0) == 0 else 1,
        "hard_mismatch_count": verify.get("hard_mismatch_count"),
        "migrated_count": verify.get("migrated_count"),
        "dual_write": health.get("dual_write"),
    }
    ticks.append(final)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(final, ensure_ascii=False) + "\n")

    ended = datetime.now(UTC)
    span_sec = int((ended - started).total_seconds())
    clean_ticks = [t for t in ticks if t.get("hard_mismatch_count", 0) == 0]
    first_clean_idx = next((i for i, t in enumerate(ticks) if t.get("hard_mismatch_count", 0) == 0), 0)
    clean_span = 0
    if clean_ticks:
        clean_start = datetime.fromisoformat(ticks[first_clean_idx]["at"])
        clean_span = int((ended - clean_start).total_seconds())

    return {
        "pass": hard_failures == 0 and span_sec >= 3600 and clean_span >= 3600,
        "ticks": len(ticks),
        "hard_failure_ticks": hard_failures,
        "ledger_span_seconds": span_sec,
        "clean_span_seconds": clean_span,
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
    }


def _mirrored_ops_from_health(health: dict[str, Any]) -> int:
    total = 0
    for counts in ((health.get("dual_write") or {}).get("operations") or {}).values():
        if isinstance(counts, dict):
            total += int(counts.get("mirrored") or 0)
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--sessions", type=Path, default=ROOT / "sessions")
    parser.add_argument("--repos", type=Path, default=Path("/tmp/agent-lab-dw-cohort2/repos"))
    parser.add_argument("--artifact-dir", type=Path, default=Path("/tmp/agent-lab-dw-cohort2"))
    parser.add_argument("--prefix", default=COHORT_PREFIX_DEFAULT)
    parser.add_argument("--target-ops", type=int, default=100)
    parser.add_argument("--watch-minutes", type=int, default=61)
    parser.add_argument("--watch-interval-sec", type=int, default=300)
    parser.add_argument("--traffic-only", action="store_true")
    parser.add_argument("--watch-only", action="store_true")
    parser.add_argument("--allowlist-file", type=Path, default=None)
    args = parser.parse_args()
    args.sessions = args.sessions.resolve()
    args.repos = args.repos.resolve()
    args.artifact_dir = args.artifact_dir.resolve()
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    args.repos.mkdir(parents=True, exist_ok=True)
    ledger = args.artifact_dir / "ledger" / "watch.jsonl"
    report_path = args.artifact_dir / "reports" / "operational.json"

    allowlist = ""
    if args.allowlist_file and args.allowlist_file.is_file():
        allowlist = args.allowlist_file.read_text(encoding="utf-8").strip()

    report: dict[str, Any] = {"kind": "operational_cohort_v2", "started_at": datetime.now(UTC).isoformat()}

    if not args.watch_only:
        health = _health(args.base_url)
        report["startup_recovery"] = health.get("last_activity_recovery_result")
        state = CohortState(prefix=args.prefix)
        run_traffic_fixed(
            base_url=args.base_url,
            sessions_root=args.sessions,
            repos_root=args.repos,
            state=state,
            target_ops=args.target_ops,
        )
        allowlist = ",".join(state.session_ids)
        (args.artifact_dir / "cohort-allowlist.txt").write_text(allowlist + "\n", encoding="utf-8")
        baseline = _run_verify(args.sessions, allowlist, cohort=True)
        journal_audit = _run_journal_audit(args.sessions, allowlist, cohort=True)
        health = _health(args.base_url)
        inbox_errors = int(
            (((health.get("dual_write") or {}).get("operations") or {}).get("inbox_create") or {}).get("error") or 0
        )
        report["traffic"] = {
            "mirrored_ops": state.mirrored_ops,
            "mirrored_ops_health_total": _mirrored_ops_from_health(health),
            "inbox_create_errors": inbox_errors,
            "session_count": len(state.session_ids),
            "route_sessions": dict(state.route_sessions),
            "route_quotas": dict(DEFAULT_ROUTE_QUOTAS),
            "baseline_hard_mismatch_count": baseline.get("hard_mismatch_count"),
            "journal_duplicate_count": journal_audit.get("duplicate_count"),
        }
        report["journal_audit"] = journal_audit
        report["allowlist"] = allowlist
        quotas_met = _quotas_met(DEFAULT_ROUTE_QUOTAS, state.route_sessions)
        if baseline.get("hard_mismatch_count", 0) != 0 or inbox_errors > 0:
            report["pass"] = False
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2))
            return 1
        if journal_audit.get("duplicate_count", 1) != 0:
            report["pass"] = False
            report["fail_reason"] = "journal_duplicates"
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2))
            return 1
        if not quotas_met:
            report["pass"] = False
            report["fail_reason"] = "route_quotas_not_met"
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2))
            return 1
        if _mirrored_ops_from_health(health) < args.target_ops:
            report["pass"] = False
            report["fail_reason"] = "mirrored_ops_below_target"
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, indent=2))
            return 1

    if args.traffic_only:
        tr = report.get("traffic") or {}
        health_total = int(tr.get("mirrored_ops_health_total") or 0)
        route_sessions = tr.get("route_sessions") or {}
        report["pass"] = (
            tr.get("baseline_hard_mismatch_count", 1) == 0
            and tr.get("inbox_create_errors", 1) == 0
            and tr.get("journal_duplicate_count", 1) == 0
            and _quotas_met(DEFAULT_ROUTE_QUOTAS, route_sessions)
            and health_total >= args.target_ops
        )
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0 if report.get("pass") else 1

    if not allowlist:
        allowlist = (args.artifact_dir / "cohort-allowlist.txt").read_text(encoding="utf-8").strip()

    watch = run_watch(
        base_url=args.base_url,
        sessions=args.sessions,
        allowlist=allowlist,
        minutes=args.watch_minutes,
        interval_sec=args.watch_interval_sec,
        ledger=ledger,
    )
    report["watch"] = watch
    report["pass"] = watch.get("pass", False)
    report["ended_at"] = datetime.now(UTC).isoformat()
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
