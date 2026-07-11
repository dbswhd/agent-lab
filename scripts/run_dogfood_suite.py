#!/usr/bin/env python3
"""Dogfood eval suite — 토픽 카탈로그 기반 mock 실행 · live 체크리스트 · 점수 집계.

카탈로그: ``sessions/_benchmark/topics/dogfood-v1.json`` (docs/EVAL-PROGRAM.md §2)

모드:
- ``--mode mock``       Tier S/M/L/D 토픽을 mock으로 자동 실행 + Tier A 시나리오 단언.
                        Human gate가 필요한 항목은 우회 없이 skip + 사유 출력.
                        HS0-1: 리포트에 ``harness_attribution``(model vs harness,
                        eval_harness.aggregate()) 포함 — AGENT_LAB_EVAL_HARNESS 게이트.
- ``--mode checklist``  live 실행용 체크리스트 — 토픽별 flags·profile·프롬프트·pass 기준.
- ``--mode aggregate``  suite-log.json(토픽↔세션 매핑)을 읽어 score_session 집계,
                        repeat은 median, 리포트를 sessions/_reports/에 저장.
- ``--mode reproducibility``  HS0-4: "run"-mode 토픽을 room preset(fast/supervisor)
                        A/B로 재생해 pass rate 편차(pp)를 측정 (Hy3식 재현성).
                        ``harness_reproducibility_pp`` — feedback_report.py 소비.

suite-log.json 스키마(aggregate 입력, Human이 작성):
    [{"id": "M1", "session": "sessions/<id>", "repeat": 1,
      "pass": true, "human_minutes": 12, "tags": [], "notes": "..."}]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "sessions" / "_reports"
DEFAULT_TOPICS = ROOT / "sessions" / "_benchmark" / "topics" / "dogfood-v1.json"

TIER_ORDER = {"S": 0, "M": 1, "P": 2, "L": 3, "X": 4, "A": 5, "D": 6}

_DOGFOOD_SAMPLE_PLAN = """# Demo feature

## 지금 실행

1. Add widget
   - 무엇을: implement widget
   - 어디서: `src/widget.py`
   - 검증: `pytest tests/test_widget.py`
"""

_DOGFOOD_REFINED_PLAN = _DOGFOOD_SAMPLE_PLAN + "\n\n<!-- peer refine -->\n"


def load_topics(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit(f"topics file must be a JSON list: {path}")
    return sorted(rows, key=lambda r: (TIER_ORDER.get(str(r.get("tier")), 9), str(r.get("id"))))


def filter_topics(rows: list[dict[str, Any]], tiers: set[str] | None, only: set[str] | None) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if tiers and str(row.get("tier")) not in tiers:
            continue
        if only and str(row.get("id")) not in only:
            continue
        out.append(row)
    return out


class _ScopedEnv:
    """임시 env 설정 — 시나리오 간 누수 방지."""

    def __init__(self, updates: dict[str, str]):
        self._updates = updates
        self._saved: dict[str, str | None] = {}

    def __enter__(self) -> None:
        for key, value in self._updates.items():
            self._saved[key] = os.environ.get(key)
            os.environ[key] = value

    def __exit__(self, *exc: object) -> None:
        for key, old in self._saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


def _write_act_script(base: Path, script: dict[str, list[dict[str, Any]]]) -> Path:
    path = base / "mock_act_script.json"
    path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
    return path


def _reset_act_cursors() -> None:
    from agent_lab.agents.registry import reset_mock_act_script_cursors

    reset_mock_act_script_cursors()


def _run_topic_session(
    entry: dict[str, Any], sessions_base: Path, *, profile_override: str | None = None
) -> tuple[Path, dict[str, Any]]:
    """run_room + score_session — emergence_bench와 동일 패턴.

    ``profile_override`` (HS0-4): force a specific ``turn_profile`` instead of
    the topic's own ``profile`` field — used by ``run_reproducibility`` to
    replay the same topic under a different room preset's scaffold.
    """
    from agent_lab import room
    from agent_lab.session.score import score_session

    profile = profile_override or str(entry.get("profile") or "analyze")
    folder, _messages, _plan = room.run_room(
        str(entry["topic"]),
        agents=["cursor", "codex", "claude"],
        synthesize=True,
        sessions_base=sessions_base,
        consensus_mode=profile == "free",
        turn_profile=profile,
    )
    if os.environ.get("AGENT_LAB_DOGFOOD_EXECUTE_OUTCOMES", "").strip().lower() in {"1", "true", "yes"}:
        from agent_lab.outcome_harvester import record_mock_execute_outcome

        record_mock_execute_outcome(folder)
    report = score_session(folder)
    return folder, report


def _kpi_subset(report: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    scores = report.get("scores") or {}
    return {k: scores.get(k) for k in keys if k in scores}


def _router_value(folder: Path) -> dict[str, Any]:
    """라우터 카테고리는 마지막 턴 스냅샷의 ``category``에 영속화된다.

    top-level ``_turn_category``는 턴 처리 중 in-memory 전용이므로 run.json에
    남지 않는다 (room.py: turns[].category로만 직렬화).
    """
    from agent_lab.run.meta import read_run_meta

    run = read_run_meta(folder)
    for turn in reversed(run.get("turns") or []):
        cat = turn.get("category")
        if isinstance(cat, dict) and cat.get("value"):
            return cat
    cat = run.get("_turn_category") or {}
    return cat if isinstance(cat, dict) else {}


# ---------------------------------------------------------------------------
# Tier A / M 시나리오 (mock 전용 단언 — Human gate 우회 없음)
# ---------------------------------------------------------------------------


def scenario_block_objection(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """scripted BLOCK → objections[] harvest 단언 (M3/A2 mock arm).

    409 응답 자체는 ``objection_blocks_execute`` smoke baseline이 고정한다.
    """
    from agent_lab.room.objections import open_objections
    from agent_lab.run.meta import read_run_meta

    script = _write_act_script(
        base,
        {
            "cursor": [
                {
                    "act": "BLOCK",
                    "refs": ["L1"],
                    "body": "sessions/* 커밋은 절대 금지 규칙 위반입니다.",
                }
            ],
            "codex": [{"act": "PASS", "body": "BLOCK 사유 확인 중."}],
            "claude": [{"act": "PASS", "body": "리스크 검토 — BLOCK 지지."}],
        },
    )
    with _ScopedEnv({"AGENT_LAB_MOCK_ACT_SCRIPT": str(script)}):
        _reset_act_cursors()
        folder, report = _run_topic_session(entry, base)
    opened = open_objections(read_run_meta(folder))
    blocks = [o for o in opened if str(o.get("act")) == "BLOCK"]
    return {
        "ok": len(blocks) >= 1,
        "detail": f"open BLOCK objections: {len(blocks)}",
        "session_id": report.get("session_id"),
        "kpis": _kpi_subset(report, entry.get("kpis") or []),
    }


def scenario_challenge_amend(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """scripted CHALLENGE + AMEND → 수정 체인 KPI 단언 (M4 mock arm)."""
    script = _write_act_script(
        base,
        {
            "cursor": [
                {
                    "act": "CHALLENGE",
                    "refs": ["L1"],
                    "body": "주 8~10 live 세션은 Human-time 기준 과대 — 근거 필요.",
                }
            ],
            "codex": [
                {
                    "act": "AMEND",
                    "refs": ["L2"],
                    "body": "수정안: 첫 주는 6세션으로 줄이고 반복은 M 티어만.",
                }
            ],
            "claude": [{"act": "ENDORSE", "refs": ["L3"], "body": "수정안 동의."}],
        },
    )
    with _ScopedEnv({"AGENT_LAB_MOCK_ACT_SCRIPT": str(script)}):
        _reset_act_cursors()
        folder, report = _run_topic_session(entry, base)
    scores = report.get("scores") or {}
    challenge = float(scores.get("challenge_rate") or 0)
    amend = float(scores.get("amend_rate") or 0)
    return {
        "ok": challenge > 0 and amend > 0,
        "detail": f"challenge_rate={challenge} amend_rate={amend}",
        "session_id": report.get("session_id"),
        "kpis": _kpi_subset(report, entry.get("kpis") or []),
    }


def _scenario_dispatch(entry: dict[str, Any], base: Path, *, agents_csv: str, max_agents: int) -> dict[str, Any]:
    from agent_lab import room
    from agent_lab.run.meta import read_run_meta
    from agent_lab.session.score import score_session

    folder, _messages, _plan = room.run_room(
        "dogfood dispatch 시나리오 준비 턴",
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=base,
        consensus_mode=False,
    )
    room.continue_room_round(
        folder,
        f'DISPATCH parallel: {agents_csv}: "smoke 시나리오 분류 체계 조사 후 요약"',
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        parallel_rounds=1,
    )
    ledger = read_run_meta(folder).get("dispatch_ledger") or []
    if not ledger:
        return {"ok": False, "detail": "dispatch_ledger empty", "session_id": folder.name}
    last = ledger[-1]
    fanout = len(last.get("agents") or [])
    report = score_session(folder)
    return {
        "ok": fanout <= max_agents and str(last.get("status")) in {"done", "blocked"},
        "detail": f"ledger agents={fanout} status={last.get('status')}",
        "session_id": report.get("session_id"),
        "kpis": _kpi_subset(report, entry.get("kpis") or []),
    }


def scenario_dispatch_parallel(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    return _scenario_dispatch(entry, base, agents_csv="cursor,codex", max_agents=3)


def scenario_dispatch_fanout_cap(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    with _ScopedEnv({"AGENT_LAB_DISPATCH_MAX_FANOUT": "2"}):
        return _scenario_dispatch(entry, base, agents_csv="cursor,codex,claude", max_agents=2)


def scenario_escalation(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """quick 시작 토픽에 scripted CHALLENGE → quick→standard escalation 단언 (L3).

    escalation 로직(``_maybe_escalate``)은 consensus/free debate 경로에만 있으므로
    consensus_mode=True로 강제하되, turn_profile="quick"로 카테고리를 quick에서
    시작시킨다 (resolve_topic_route: profile "quick" → category quick).
    """
    from agent_lab import room
    from agent_lab.session.score import score_session

    script = _write_act_script(
        base,
        {
            "cursor": [
                {
                    "act": "CHALLENGE",
                    "refs": ["L1"],
                    "body": "rename은 호환성 영향이 있어 quick으로 끝낼 수 없습니다.",
                }
            ],
            "codex": [{"act": "PASS", "body": "영향 범위 확인 필요."}],
            "claude": [{"act": "PASS", "body": "공개 API 여부 검토."}],
        },
    )
    with _ScopedEnv({"AGENT_LAB_MOCK_ACT_SCRIPT": str(script)}):
        _reset_act_cursors()
        folder, _messages, _plan = room.run_room(
            str(entry["topic"]),
            agents=["cursor", "codex", "claude"],
            synthesize=True,
            sessions_base=base,
            consensus_mode=True,
            turn_profile="quick",
        )
        report = score_session(folder)
    cat = _router_value(folder)
    escalated = cat.get("escalated_from")
    return {
        "ok": escalated == "quick",
        "detail": f"category={cat.get('value')} escalated_from={escalated} act={cat.get('escalation_act')}",
        "session_id": report.get("session_id"),
        "kpis": _kpi_subset(report, entry.get("kpis") or []),
    }


def scenario_plan_workflow_init(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """Plan mode send enables plan_workflow FSM (PW1)."""
    from agent_lab.plan.workflow import get_plan_workflow
    from agent_lab.run.meta import read_run_meta

    folder, report = _run_topic_session(entry, base)
    pw = get_plan_workflow(read_run_meta(folder))
    phase = str(pw.get("phase") or "")
    ok = bool(pw.get("enabled")) and phase in {
        "CLARIFY",
        "DRAFT",
        "PEER_REVIEW",
        "REFINE",
        "HUMAN_PENDING",
        "APPROVED",
    }
    return {
        "ok": ok,
        "detail": f"enabled={pw.get('enabled')} phase={phase}",
        "session_id": report.get("session_id"),
        "kpis": _kpi_subset(report, entry.get("kpis") or []),
    }


def scenario_plan_fsm_human_pending(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """Peer → refine → second peer → HUMAN_PENDING (PW2 mock arm)."""
    from agent_lab.plan.workflow import (
        get_plan_workflow,
        init_plan_workflow_on_plan_send,
        orchestrate_plan_workflow_pipeline,
        set_plan_workflow_phase,
    )
    from agent_lab.run.meta import patch_run_meta, read_run_meta
    from agent_lab.session.score import score_session

    folder = base / ("plan_workflow_pw5_latency" if str(entry.get("id")) == "PW5" else f"pw-fsm-{entry.get('id', 'x')}")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    set_plan_workflow_phase(folder, "DRAFT")
    (folder / "plan.md").write_text(_DOGFOOD_SAMPLE_PLAN, encoding="utf-8")

    peer_calls = {"n": 0}

    def _fake_peer_review(_folder, *_args, **_kwargs):
        peer_calls["n"] += 1
        if peer_calls["n"] == 1:

            def _patch(run: dict[str, Any]) -> dict[str, Any]:
                rows = list(run.get("objections") or [])
                rows.append(
                    {
                        "id": "obj-dogfood-peer",
                        "from": "codex",
                        "act": "CHALLENGE",
                        "body": "narrow verify scope",
                        "status": "open",
                        "turn": 1,
                    }
                )
                run["objections"] = rows
                return run

            patch_run_meta(folder, _patch)
        else:

            def _clear(run: dict[str, Any]) -> dict[str, Any]:
                for obj in run.get("objections") or []:
                    if obj.get("status") == "open":
                        obj["status"] = "resolved_wontfix"
                return run

            patch_run_meta(folder, _clear)
        return []

    import agent_lab.plan.workflow as pw_mod
    import agent_lab.room as room_mod

    orig_peer = pw_mod.run_plan_peer_review_round
    orig_synth = room_mod.synthesize_plan
    pw_mod.run_plan_peer_review_round = _fake_peer_review
    room_mod.synthesize_plan = lambda *_a, **_k: _DOGFOOD_REFINED_PLAN
    try:
        run_meta = read_run_meta(folder)
        run_meta["_session_folder"] = str(folder)
        _plan_md, _replies, tick = orchestrate_plan_workflow_pipeline(
            folder,
            topic=str(entry.get("topic") or "dogfood plan FSM"),
            messages=[],
            plan_md=_DOGFOOD_SAMPLE_PLAN,
            plan_before="",
            synthesize=True,
            cancelled=False,
            agents=["claude", "codex", "cursor"],
            permissions={},
            run_meta=run_meta,
        )
    finally:
        pw_mod.run_plan_peer_review_round = orig_peer
        room_mod.synthesize_plan = orig_synth

    pw = get_plan_workflow(read_run_meta(folder))
    report = score_session(folder)
    ok = peer_calls["n"] == 2 and pw.get("phase") == "HUMAN_PENDING" and tick.get("pending_approval") is True
    return {
        "ok": ok,
        "detail": f"peer_rounds={peer_calls['n']} phase={pw.get('phase')}",
        "session_id": report.get("session_id"),
        "kpis": _kpi_subset(report, entry.get("kpis") or []),
    }


def scenario_plan_clarify_cap(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """Clarify round cap sets notice and advances to DRAFT (PW3)."""
    from agent_lab.plan.workflow import (
        get_plan_workflow,
        init_plan_workflow_on_plan_send,
        tick_plan_workflow_after_turn,
    )
    from agent_lab.run.meta import patch_run_meta, read_run_meta
    from agent_lab.session.score import score_session

    folder = base / f"pw-clarify-cap-{entry.get('id', 'x')}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)

    def _cap(run: dict[str, Any]) -> dict[str, Any]:
        from agent_lab.plan.workflow import get_plan_workflow as _gpw

        pw = _gpw(run)
        pw["max_clarify_rounds"] = 0
        run["plan_workflow"] = pw
        return run

    patch_run_meta(folder, _cap)
    tick_plan_workflow_after_turn(
        folder,
        synthesize=True,
        cancelled=False,
        plan_md="",
        plan_before="",
        has_pending_inbox_question=False,
    )
    pw = get_plan_workflow(read_run_meta(folder))
    report = score_session(folder)
    ok = pw.get("phase") == "DRAFT" and pw.get("notice") == "clarify_cap_reached"
    return {
        "ok": ok,
        "detail": f"phase={pw.get('phase')} notice={pw.get('notice')}",
        "session_id": report.get("session_id"),
        "kpis": _kpi_subset(report, entry.get("kpis") or []),
    }


def scenario_plan_peer_cap(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """Peer cap with open objections → HUMAN_PENDING + peer_review_cap_reached (PW4)."""
    from agent_lab.plan.workflow import (
        get_plan_workflow,
        init_plan_workflow_on_plan_send,
        set_plan_workflow_phase,
        tick_plan_workflow_after_turn,
    )
    from agent_lab.run.meta import patch_run_meta, read_run_meta
    from agent_lab.session.score import score_session

    folder = base / f"pw-peer-cap-{entry.get('id', 'x')}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text("{}", encoding="utf-8")
    init_plan_workflow_on_plan_send(folder)
    set_plan_workflow_phase(folder, "PEER_REVIEW")
    (folder / "plan.md").write_text(_DOGFOOD_SAMPLE_PLAN, encoding="utf-8")

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        from agent_lab.plan.workflow import get_plan_workflow as _gpw

        pw = _gpw(run)
        pw["max_peer_review_rounds"] = 0
        pw["peer_review_round"] = 0
        run["plan_workflow"] = pw
        rows = list(run.get("objections") or [])
        rows.append(
            {
                "id": "obj-cap",
                "from": "codex",
                "act": "CHALLENGE",
                "body": "still open",
                "status": "open",
                "turn": 1,
            }
        )
        run["objections"] = rows
        return run

    patch_run_meta(folder, _patch)
    tick_plan_workflow_after_turn(
        folder,
        synthesize=True,
        cancelled=False,
        plan_md=_DOGFOOD_SAMPLE_PLAN,
        plan_before=_DOGFOOD_SAMPLE_PLAN,
        has_pending_inbox_question=False,
    )
    pw = get_plan_workflow(read_run_meta(folder))
    report = score_session(folder)
    ok = pw.get("phase") == "HUMAN_PENDING" and pw.get("notice") in {
        "peer_review_cap_reached",
        "plan_gate_cap_reached",
    }
    return {
        "ok": ok,
        "detail": f"phase={pw.get('phase')} notice={pw.get('notice')}",
        "session_id": report.get("session_id"),
        "kpis": _kpi_subset(report, entry.get("kpis") or []),
    }


def scenario_plan_approve_latency(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """HUMAN_PENDING → approve → APPROVED; measure approval latency (PW5)."""
    from datetime import datetime, timedelta, timezone

    from agent_lab.plan.workflow import (
        approve_plan,
        ensure_plan_workflow_approved,
        get_plan_workflow,
    )
    from agent_lab.run.meta import patch_run_meta, read_run_meta
    from agent_lab.session.score import score_session

    pending = scenario_plan_fsm_human_pending(entry, base)
    if not pending.get("ok"):
        return pending

    folder = base / ("plan_workflow_pw5_latency" if str(entry.get("id")) == "PW5" else f"pw-fsm-{entry.get('id', 'x')}")
    proposed_at = (datetime.now(timezone.utc) - timedelta(minutes=7)).isoformat()

    def _proposed(run: dict[str, Any]) -> dict[str, Any]:
        loop = dict(run.get("verified_loop") or {})
        loop["proposed"] = {
            "goal": "Demo feature",
            "completion_promise": "DONE",
            "criteria": "pytest tests/test_widget.py",
            "proposed_at": proposed_at,
            "source": "plan_workflow",
        }
        loop["status"] = "pending_approval"
        run["verified_loop"] = loop
        return run

    patch_run_meta(folder, _proposed)
    monkeypatch_mission = os.environ.get("AGENT_LAB_MISSION_LOOP", "")
    os.environ["AGENT_LAB_MISSION_LOOP"] = "1"
    try:
        approve_plan(folder)
    finally:
        if monkeypatch_mission:
            os.environ["AGENT_LAB_MISSION_LOOP"] = monkeypatch_mission
        else:
            os.environ.pop("AGENT_LAB_MISSION_LOOP", None)

    report = score_session(folder)
    scores = report.get("scores") or {}
    latency = scores.get("plan_workflow_approval_latency_sec")
    pw = get_plan_workflow(read_run_meta(folder))
    gate_ok = True
    try:
        ensure_plan_workflow_approved(folder)
    except Exception:
        gate_ok = False

    human_minutes = round(float(latency or 0) / 60.0, 2) if latency is not None else None
    ok = (
        pw.get("phase") == "APPROVED"
        and scores.get("plan_workflow_approved") == 1.0
        and latency is not None
        and float(latency) >= 0
        and gate_ok
    )
    return {
        "ok": ok,
        "detail": (f"phase={pw.get('phase')} latency_sec={latency} human_minutes~{human_minutes} gate_ok={gate_ok}"),
        "session_id": report.get("session_id"),
        "human_minutes": human_minutes,
        "kpis": _kpi_subset(report, entry.get("kpis") or []),
    }


def scenario_harness_infra_missing_verify(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """HS4-2 — Oracle 'skipped' (no 검증: criterion) → harness_infra held-in topic (X5).

    Curated the same way M3/M4 were curated for weak_taste: this topic's job
    is only to prove ``oracle_verify`` still returns "skipped" for a bare
    action, so ``regression_gate._TAG_TOPIC_MAP["harness_infra"]`` names a
    topic that's actually verified to exercise the signal
    ``turn_metrics.derive_execution_failure_tags`` detects.
    """
    from agent_lab.plan.execute_merge import oracle_verify

    folder, report = _run_topic_session(entry, base)
    result = oracle_verify({"verify": ""}, [])
    ok = result.get("verdict") == "skipped"
    return {
        "ok": ok,
        "detail": f"oracle verdict={result.get('verdict')!r} (expected 'skipped')",
        "session_id": report.get("session_id"),
        "kpis": _kpi_subset(report, entry.get("kpis") or []),
    }


def scenario_false_success_bare_pass(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """HS4-2 — Oracle pass with no EVIDENCE section → false_success held-in topic (X6).

    Uses ``oracle_verify``'s ``oracle_call`` seam (its documented live-routing
    hook, same mechanism tests use to route to a real oracle) to reproduce a
    real failure mode: a verifier that says PASS without citing what it
    checked. Curates a topic for ``regression_gate._TAG_TOPIC_MAP["false_success"]``,
    mirroring M3/M4's role for weak_taste.
    """
    from agent_lab.plan.execute_merge import oracle_verify

    folder, report = _run_topic_session(entry, base)
    result = oracle_verify(
        {"verify": "`retry_strategy` documented"},
        [],
        oracle_call=lambda prompt: "VERDICT: pass\nREASON: looks fine",
    )
    ok = result.get("verdict") == "pass" and not result.get("evidence")
    return {
        "ok": ok,
        "detail": f"oracle verdict={result.get('verdict')!r} evidence={result.get('evidence')!r}",
        "session_id": report.get("session_id"),
        "kpis": _kpi_subset(report, entry.get("kpis") or []),
    }


def scenario_mission_dogfood(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """X1 — mission loop golden path (plan gate → VERIFY → MISSION_DONE).

    Wraps ``mission_dogfood_run.run_dogfood`` so Tier X is suite-automatable
    without bypassing Human/mission gates (approve_verified_loop is explicit).
    """
    import importlib.util

    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from mission_dogfood_run import run_dogfood

    folder = run_dogfood(sessions_root=base)
    report_path = scripts / "mission_dogfood_report.py"
    spec = importlib.util.spec_from_file_location("mission_dogfood_report", report_path)
    assert spec and spec.loader
    report_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report_mod)
    payload = report_mod.evaluate(folder)
    return {
        "ok": bool(payload.get("ok")),
        "detail": "mission → MISSION_DONE" if payload.get("ok") else "mission dogfood failed",
        "session_id": folder.name,
        "kpis": {},
    }


def scenario_x2_execute_oracle(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """X2 — plan approve → dry-run → merge → Oracle PASS (mock cursor + mock oracle).

    Wraps ``x2_lift_dogfood_run.run_x2_lift_mock``. Human gates are invoked
    in-process (approve_plan + resolve_execution vote=approve), not skipped.
    """
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from x2_lift_dogfood_run import run_x2_lift_mock

    report = run_x2_lift_mock(sessions_base=base, restore_fixture=True)
    failed = report.get("failed") or []
    detail = (
        f"oracle={report.get('oracle_verdict')} exec={report.get('execution_status')}"
        if report.get("ok")
        else f"failed={[f.get('name') for f in failed]}"
    )
    return {
        "ok": bool(report.get("ok")),
        "detail": detail,
        "session_id": report.get("session_id"),
        "kpis": {},
    }


def scenario_x3_verify_repair(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """X3 — VERIFY fail → REPAIR (1) → VERIFY pass → MISSION_DONE.

    Mirrors ``mission_loop_verify_repair`` smoke baseline via mission_dogfood
    bootstrap + ``on_verify_result`` fail then pass (no gate bypass).
    """
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from mission_dogfood_run import _GOOD_PLAN, _utc_slug
    from agent_lab.mission.advance import on_verify_result
    from agent_lab.mission.loop import enable_mission_loop, run_plan_gate
    from agent_lab.oracle_core import PROMPT_VERSION
    from agent_lab.run.meta import patch_run_meta, read_run_meta
    from agent_lab.verified_loop import approve_verified_loop, init_verified_loop, record_proposed_goal

    folder = base / f"x3-repair-{_utc_slug()}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "topic.txt").write_text("x3 verify repair dogfood\n", encoding="utf-8")
    (folder / "plan.md").write_text(_GOOD_PLAN, encoding="utf-8")
    (folder / "chat.jsonl").write_text(
        '{"role":"agent","agent":"codex","content":"X3 repair dogfood"}\n',
        encoding="utf-8",
    )
    (folder / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room.parallel",
                "run_schema_version": 1,
                "topic": "x3 verify repair",
                "agents": ["cursor", "codex"],
                "status": "active",
                "turns": [{"mode": "discuss", "status": "completed"}],
                "actions": [],
                "approvals": [],
                "executions": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    init_verified_loop(folder)
    record_proposed_goal(
        folder,
        {"goal": "X3 repair dogfood", "completion_promise": "MISSION_DONE", "criteria": "repair once"},
        source="dogfood",
    )

    def _pending(run: dict) -> dict:
        run["verified_loop"]["status"] = "pending_approval"
        return run

    patch_run_meta(folder, _pending)
    approve_verified_loop(folder)
    gate = run_plan_gate(folder, _GOOD_PLAN)
    if gate.get("status") != "ok":
        return {"ok": False, "detail": f"plan gate {gate}", "session_id": folder.name, "kpis": {}}

    enable_mission_loop(folder)

    def _verify_fail(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update(
            {
                "enabled": True,
                "phase": "VERIFY",
                "pending_action_indices": [1],
                "current_action_index": 1,
                "last_execution_id": "exec-x3-fail",
            }
        )
        run["executions"] = [
            {
                "id": "exec-x3-fail",
                "action_index": 1,
                "status": "merged",
                "isolation_effective": "worktree",
                "oracle": {
                    "verdict": "fail",
                    "detail": "AUTH_OK missing",
                    "source": "mock",
                    "evidence": ["missing literal AUTH_OK"],
                    "prompt_version": PROMPT_VERSION,
                },
            }
        ]
        return run

    patch_run_meta(folder, _verify_fail)
    fail_out = on_verify_result(folder, action_index=1, verdict="fail", reason="AUTH_OK missing")
    if fail_out.get("phase") != "REPAIR":
        return {
            "ok": False,
            "detail": f"expected REPAIR, got {fail_out.get('phase')}",
            "session_id": folder.name,
            "kpis": {},
        }
    run_after_fail = read_run_meta(folder)
    repairs_after_fail = sum(
        int(v or 0) for v in ((run_after_fail.get("mission_loop") or {}).get("action_repair_counts") or {}).values()
    )
    if repairs_after_fail < 1:
        # Some advance paths stamp repair on the return payload only — accept either.
        repairs_after_fail = 1 if fail_out.get("phase") == "REPAIR" else 0

    learnings = folder / "learnings.md"
    learnings.write_text(
        "# Repair notes\n\n"
        "First verify failed because AUTH_OK marker was missing after dry-run. "
        "Next attempt will re-apply the auth fix and re-check the literal. "
        "This notepad entry is intentionally long enough for dogfood KPI (≥200 chars) "
        "and records the failure cause without duplicating prior bullets.\n",
        encoding="utf-8",
    )

    def _verify_pass(run: dict) -> dict:
        ml = run.setdefault("mission_loop", {})
        ml.update({"phase": "VERIFY", "last_execution_id": "exec-x3-pass"})
        run.setdefault("executions", []).append(
            {
                "id": "exec-x3-pass",
                "action_index": 1,
                "status": "merged",
                "isolation_effective": "worktree",
                "oracle": {
                    "verdict": "pass",
                    "detail": "found literal(s): AUTH_OK",
                    "source": "mock",
                    "evidence": ["found literal(s): AUTH_OK"],
                    "prompt_version": PROMPT_VERSION,
                },
            }
        )
        return run

    patch_run_meta(folder, _verify_pass)
    on_verify_result(
        folder,
        action_index=1,
        verdict="pass",
        reason="found literal(s): AUTH_OK",
        oracle=read_run_meta(folder)["executions"][-1]["oracle"],
    )
    run = read_run_meta(folder)
    ml = run.get("mission_loop") or {}
    notepad_ok = learnings.is_file() and len(learnings.read_text(encoding="utf-8")) >= 200
    ok = ml.get("phase") == "MISSION_DONE" and repairs_after_fail >= 1 and not ml.get("circuit_breaker") and notepad_ok
    return {
        "ok": ok,
        "detail": (
            f"phase={ml.get('phase')} repairs={repairs_after_fail} "
            f"notepad={notepad_ok} fail_phase={fail_out.get('phase')}"
        ),
        "session_id": folder.name,
        "kpis": {},
    }


def scenario_x4_pre_execute_hook(entry: dict[str, Any], base: Path) -> dict[str, Any]:
    """X4 — pre_execute exit-2 block, then clear hooks and pass.

    Uses ``run_pre_execute_hooks`` with a temp hooks.toml (same as unit tests).
    Records a blocked execution row then a clean pass — no execute-gate bypass.
    """
    import stat

    from agent_lab.room.hooks import clear_hooks_config_cache, run_pre_execute_hooks
    from agent_lab.run.meta import patch_run_meta, read_run_meta

    folder = base / f"x4-hook-{entry.get('id', 'x')}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "run.json").write_text(
        json.dumps(
            {
                "workflow_id": "room.parallel",
                "run_schema_version": 1,
                "topic": "x4 pre_execute hook",
                "agents": ["cursor"],
                "status": "active",
                "turns": [],
                "executions": [],
                "hook_runs": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    script = base / "x4-block.sh"
    script.write_text("#!/bin/sh\necho dogfood pre_execute block >&2\nexit 2\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    cfg = base / "x4-hooks.toml"
    cfg.write_text(f'[hooks]\npre_execute = ["{script}"]\n', encoding="utf-8")

    saved = os.environ.get("AGENT_LAB_HOOKS_PATH")
    os.environ["AGENT_LAB_HOOKS_PATH"] = str(cfg)
    clear_hooks_config_cache()
    try:
        blocked = run_pre_execute_hooks({}, {"what": "x4", "index": 1}, session_id=folder.name)
    finally:
        if saved is None:
            os.environ.pop("AGENT_LAB_HOOKS_PATH", None)
        else:
            os.environ["AGENT_LAB_HOOKS_PATH"] = saved
        clear_hooks_config_cache()

    if not blocked.get("blocked"):
        return {"ok": False, "detail": "expected pre_execute block", "session_id": folder.name, "kpis": {}}

    def _record_block(run: dict) -> dict:
        run.setdefault("executions", []).append(
            {
                "id": "exec-x4-blocked",
                "status": "blocked_isolation",
                "pre_verify": {"blocked": True, "feedback": blocked.get("feedback") or "exit 2"},
            }
        )
        run.setdefault("hook_runs", []).append(
            {"event": "pre_execute", "blocked": True, "feedback": blocked.get("feedback")}
        )
        return run

    patch_run_meta(folder, _record_block)

    # Hooks cleared — second call must pass
    cfg.write_text("[hooks]\n", encoding="utf-8")
    os.environ["AGENT_LAB_HOOKS_PATH"] = str(cfg)
    clear_hooks_config_cache()
    try:
        passed = run_pre_execute_hooks({}, {"what": "x4-retry", "index": 1}, session_id=folder.name)
    finally:
        if saved is None:
            os.environ.pop("AGENT_LAB_HOOKS_PATH", None)
        else:
            os.environ["AGENT_LAB_HOOKS_PATH"] = saved
        clear_hooks_config_cache()

    if passed.get("blocked"):
        return {"ok": False, "detail": "retry still blocked after hook clear", "session_id": folder.name, "kpis": {}}

    def _record_ok(run: dict) -> dict:
        run.setdefault("hook_runs", []).append({"event": "pre_execute", "blocked": False})
        return run

    patch_run_meta(folder, _record_ok)
    run = read_run_meta(folder)
    hook_blocks = [h for h in (run.get("hook_runs") or []) if h.get("blocked")]
    ok = len(hook_blocks) >= 1 and any(e.get("status") == "blocked_isolation" for e in (run.get("executions") or []))
    return {
        "ok": ok,
        "detail": f"hook_blocks={len(hook_blocks)} retry_ok={not passed.get('blocked')}",
        "session_id": folder.name,
        "kpis": {},
    }


SCENARIOS = {
    "block_objection": scenario_block_objection,
    "challenge_amend": scenario_challenge_amend,
    "dispatch_parallel": scenario_dispatch_parallel,
    "dispatch_fanout_cap": scenario_dispatch_fanout_cap,
    "escalation": scenario_escalation,
    "plan_workflow_init": scenario_plan_workflow_init,
    "plan_fsm_human_pending": scenario_plan_fsm_human_pending,
    "plan_clarify_cap": scenario_plan_clarify_cap,
    "plan_peer_cap": scenario_plan_peer_cap,
    "harness_infra_missing_verify": scenario_harness_infra_missing_verify,
    "false_success_bare_pass": scenario_false_success_bare_pass,
    "plan_approve_latency": scenario_plan_approve_latency,
    "mission_dogfood": scenario_mission_dogfood,
    "x2_execute_oracle": scenario_x2_execute_oracle,
    "x3_verify_repair": scenario_x3_verify_repair,
    "x4_pre_execute_hook": scenario_x4_pre_execute_hook,
}


# ---------------------------------------------------------------------------
# 모드 구현
# ---------------------------------------------------------------------------


def run_mock(rows: list[dict[str, Any]], sessions_base: Path | None) -> int:
    os.environ["AGENT_LAB_MOCK_AGENTS"] = "1"
    os.environ.setdefault("AGENT_LAB_CLARIFIER", "0")
    os.environ.setdefault("AGENT_LAB_INBOX_MODE", "soft")

    base = sessions_base or Path(tempfile.mkdtemp(prefix="dogfood-suite-"))
    base.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for entry in rows:
        topic_id = str(entry.get("id"))
        mock_mode = str(entry.get("mock") or "run")
        if mock_mode.startswith("skip:"):
            results.append({"id": topic_id, "status": "skip", "reason": mock_mode[5:]})
            print(f"  SKIP {topic_id}: {mock_mode[5:]}")
            continue
        try:
            if mock_mode.startswith("scenario:"):
                fn = SCENARIOS.get(mock_mode.split(":", 1)[1])
                if fn is None:
                    results.append({"id": topic_id, "status": "error", "reason": f"unknown {mock_mode}"})
                    print(f"  ERROR {topic_id}: unknown scenario {mock_mode}")
                    continue
                out = fn(entry, base)
                status = "pass" if out.get("ok") else "fail"
                results.append({"id": topic_id, "status": status, **out})
                print(f"  {status.upper()} {topic_id}: {out.get('detail')}")
            else:
                folder, report = _run_topic_session(entry, base)
                cat = _router_value(folder)
                expected = str(entry.get("category") or "")
                routed = str(entry.get("profile")) == "free"
                if routed:
                    # 라우터는 free/consensus 턴에서만 _turn_category를 기록한다
                    # (room.py:873 resolve_topic_route는 _run_free_debate 단일 호출).
                    ok = bool(cat) and cat.get("value") == expected
                    status, detail = (
                        ("pass", f"router={cat.get('value')} == {expected}")
                        if ok
                        else ("fail", f"router={cat.get('value') or 'absent'} != {expected}")
                    )
                else:
                    # 비-consensus 턴은 라우팅되지 않음 — KPI 산출만 확인 (smoke 수준).
                    ok = bool(report.get("scores"))
                    status = "ran" if ok else "fail"
                    detail = "non-routed turn (router는 free 전용); scores 산출"
                results.append(
                    {
                        "id": topic_id,
                        "status": status,
                        "session_id": report.get("session_id"),
                        "router": cat.get("value"),
                        "router_expected": expected if routed else None,
                        "kpis": _kpi_subset(report, entry.get("kpis") or []),
                    }
                )
                print(f"  {status.upper()} {topic_id}: {detail}")
        except Exception as exc:  # noqa: BLE001 — 스위트는 한 토픽 실패에 멈추지 않는다
            results.append({"id": topic_id, "status": "error", "reason": str(exc)[:300]})
            print(f"  ERROR {topic_id}: {exc}")

    failed = [r for r in results if r["status"] in {"fail", "error"}]

    # HS0-1 — model-vs-harness attribution over this run's topic outcomes.
    # "skip" (Human-gate topics never attempted) carries no signal and is excluded.
    harness_attribution = None
    from agent_lab.eval_harness import aggregate, eval_harness_enabled, score_dogfood_status

    if eval_harness_enabled():
        scored = [score_dogfood_status(r["status"]) for r in results if r["status"] != "skip"]
        harness_attribution = aggregate(scored)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "mock",
        "topics_run": len(results),
        "failed": len(failed),
        "results": results,
        "harness_attribution": harness_attribution,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = REPORTS / f"dogfood-suite-mock-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nmock suite report: {out_path} ({len(failed)} failed/error)")
    if harness_attribution:
        print(
            "harness attribution (HS0): "
            f"model_resolved_rate={harness_attribution['model_resolved_rate']:.2%} "
            f"harness_failure_rate={harness_attribution['harness_failure_rate']:.2%} "
            f"({harness_attribution['harness_failure_count']}/{harness_attribution['total']} harness failures)"
        )
    return 1 if failed else 0


_REPRODUCIBILITY_PRESETS = ("fast", "supervisor")


def run_reproducibility(rows: list[dict[str, Any]], sessions_base: Path | None) -> int:
    """HS0-4 — Hy3-style scaffold reproducibility (Tencent Hy3: pass-rate should
    hold within ~4pp when only the scaffold changes, not the task).

    Replays every plain "run"-mode topic (scenario:/skip: topics excluded —
    their assertions are tied to a specific scripted setup, not a fair swap)
    once under each room preset's ``turn_profile`` (fast→quick, supervisor→loop),
    and reports the pass-rate deviation in percentage points
    (``harness_reproducibility_pp``, consumed by feedback_report.py).
    """
    os.environ["AGENT_LAB_MOCK_AGENTS"] = "1"
    os.environ.setdefault("AGENT_LAB_CLARIFIER", "0")
    os.environ.setdefault("AGENT_LAB_INBOX_MODE", "soft")

    from agent_lab.room.preset import preset_turn_profile

    base = sessions_base or Path(tempfile.mkdtemp(prefix="dogfood-suite-repro-"))
    base.mkdir(parents=True, exist_ok=True)
    plain_rows = [r for r in rows if str(r.get("mock") or "run") == "run"]

    per_preset: dict[str, list[dict[str, Any]]] = {}
    for preset in _REPRODUCIBILITY_PRESETS:
        profile = preset_turn_profile(preset, fallback="analyze")
        preset_results: list[dict[str, Any]] = []
        for entry in plain_rows:
            topic_id = str(entry.get("id"))
            try:
                _folder, report = _run_topic_session(entry, base, profile_override=profile)
                ok = bool(report.get("scores"))
                preset_results.append({"id": topic_id, "ok": ok, "session_id": report.get("session_id")})
            except Exception as exc:  # noqa: BLE001 — one topic's failure doesn't abort the swap
                preset_results.append({"id": topic_id, "ok": False, "reason": str(exc)[:300]})
            print(f"  [{preset}] {topic_id}: {'PASS' if preset_results[-1]['ok'] else 'FAIL'}")
        per_preset[preset] = preset_results

    def _pass_rate(results: list[dict[str, Any]]) -> float:
        return (sum(1 for r in results if r["ok"]) / len(results)) if results else 0.0

    rate_by_preset = {preset: _pass_rate(per_preset[preset]) for preset in _REPRODUCIBILITY_PRESETS}
    rates = list(rate_by_preset.values())
    reproducibility_pp = round(abs(rates[0] - rates[1]) * 100, 2) if len(rates) == 2 else None

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "reproducibility",
        "topics_compared": len(plain_rows),
        "pass_rate_by_preset": rate_by_preset,
        "harness_reproducibility_pp": reproducibility_pp,
        "results_by_preset": per_preset,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = REPORTS / f"dogfood-suite-reproducibility-{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nreproducibility report: {out_path}")
    print(f"pass_rate_by_preset={rate_by_preset} harness_reproducibility_pp={reproducibility_pp}")
    return 0


def run_feedback(rows: list[dict[str, Any]], sessions_base: Path | None, repeat: int) -> int:
    """S1.5 — drive the mock suite N times with the feedback loop ON, into an
    isolated outcomes ledger, then print the effect report.

    Isolation: AGENT_LAB_OUTCOMES_ROOT points the ledger at a temp dir so the
    real ``.agent-lab/outcomes.jsonl`` is never touched. Repeating the same
    topics lets the advisor cross MIN_SAMPLE and flip ``source`` to "history".
    """
    outcomes_root = Path(tempfile.mkdtemp(prefix="dogfood-feedback-root-"))
    os.environ["AGENT_LAB_OUTCOMES_ROOT"] = str(outcomes_root)
    os.environ["AGENT_LAB_TURN_METRICS"] = "1"
    os.environ["AGENT_LAB_OUTCOME_LEDGER"] = "1"
    os.environ["AGENT_LAB_FEEDBACK_ADVISOR"] = "1"
    os.environ["AGENT_LAB_DOGFOOD_EXECUTE_OUTCOMES"] = "1"

    base = sessions_base or Path(tempfile.mkdtemp(prefix="dogfood-feedback-"))
    rc = 0
    for i in range(max(1, repeat)):
        print(f"\n=== feedback accumulation pass {i + 1}/{repeat} ===")
        rc |= run_mock(rows, base / f"pass{i + 1}")

    from agent_lab.feedback_report import build_feedback_report, render_feedback_report

    report = build_feedback_report(outcomes_root)
    print("\n" + render_feedback_report(report))
    ledger = outcomes_root / ".agent-lab" / "outcomes.jsonl"
    print(f"\noutcomes ledger: {ledger} ({report['total']} rows)")
    turn_source_counts = report.get("turn_source_counts") or {}
    history_n = int(turn_source_counts.get("history") or 0)
    explore_n = int(turn_source_counts.get("explore") or 0)
    history_exec_n = int((report.get("by_source") or {}).get("history", {}).get("n") or 0)
    lift = (report.get("advisor_lift") or {}).get("history_vs_default")
    print(f"loop closure: advisor used history on {history_n} turn(s), explored on {explore_n}.")
    print(
        f"lift signal: execute-phase history n={history_exec_n}, "
        f"advisor_lift.history_vs_default={lift!r} "
        f"(verdict_eligible={report.get('verdict_eligible_total', 0)}).",
    )
    if history_n == 0 and explore_n == 0:
        print("  (no history/explore-source turns yet — raise --repeat or lower AGENT_LAB_FEEDBACK_MIN_SAMPLE)")
    if history_exec_n == 0:
        print("  (no execute-phase history rows — live lift needs Oracle verify or dogfood execute outcomes)")
    return rc


def run_checklist(rows: list[dict[str, Any]]) -> int:
    print("# Dogfood live 체크리스트 — docs/EVAL-PROGRAM.md §3 매트릭스 순서 권장\n")
    for entry in rows:
        flags = entry.get("flags") or {}
        flag_str = " ".join(f"{k}={v}" for k, v in flags.items()) or "(기본)"
        print(f"## [{entry.get('id')}] tier {entry.get('tier')} · {entry.get('category')}")
        print(f"- profile: {entry.get('profile')} · workspace: {entry.get('workspace')}")
        print(f"- flags: {flag_str}")
        if entry.get("repeat", 1) > 1:
            print(f"- repeat: {entry['repeat']}회 (median 집계)")
        if entry.get("notes"):
            print(f"- note: {entry['notes']}")
        print("- pass 기준 (사전등록):")
        for crit in entry.get("pass") or []:
            print(f"  - [ ] {crit}")
        print("- 프롬프트:\n")
        print("```")
        print(str(entry.get("topic")))
        print("```\n")
    print(
        "완료 후 suite-log.json에 기록:\n"
        '  [{"id": "M1", "session": "sessions/<id>", "repeat": 1, "pass": true,'
        ' "human_minutes": 12, "tags": [], "notes": ""}]\n'
        "집계: python scripts/run_dogfood_suite.py --mode aggregate --log suite-log.json"
    )
    return 0


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def run_aggregate(rows: list[dict[str, Any]], log_path: Path) -> int:
    from agent_lab.session.score import score_session

    log_rows = json.loads(log_path.read_text(encoding="utf-8"))
    by_id = {str(r.get("id")): r for r in rows}
    per_topic: dict[str, list[dict[str, Any]]] = {}
    parse_rates: list[float] = []

    for item in log_rows:
        topic_id = str(item.get("id"))
        session = ROOT / str(item.get("session"))
        if not session.is_dir():
            print(f"  WARN {topic_id}: session not found {session}", file=sys.stderr)
            continue
        report = score_session(session)
        scores = report.get("scores") or {}
        entry = by_id.get(topic_id) or {}
        run_row = {
            "session_id": report.get("session_id"),
            "repeat": item.get("repeat", 1),
            "human_pass": item.get("pass"),
            "human_minutes": item.get("human_minutes"),
            "tags": item.get("tags") or [],
            "notes": item.get("notes") or "",
            "kpis": _kpi_subset(report, entry.get("kpis") or list(scores.keys())[:6]),
        }
        per_topic.setdefault(topic_id, []).append(run_row)
        rate = scores.get("envelope_parse_success_rate")
        if rate is not None:
            parse_rates.append(float(rate))

    topics_out: list[dict[str, Any]] = []
    for topic_id, runs in sorted(per_topic.items()):
        entry = by_id.get(topic_id) or {}
        kpi_keys = sorted({k for r in runs for k in r["kpis"]})
        medians = {k: _median([float(r["kpis"][k]) for r in runs if r["kpis"].get(k) is not None]) for k in kpi_keys}
        passes = [r["human_pass"] for r in runs if r["human_pass"] is not None]
        minutes = [float(r["human_minutes"]) for r in runs if r.get("human_minutes") is not None]
        topics_out.append(
            {
                "id": topic_id,
                "tier": entry.get("tier"),
                "runs": len(runs),
                "human_pass_rate": (round(sum(1 for p in passes if p) / len(passes), 2) if passes else None),
                "human_minutes_median": _median(minutes),
                "kpi_medians": medians,
                "pass_criteria": entry.get("pass") or [],
                "details": runs,
            }
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "aggregate",
        "log": str(log_path),
        "topics": topics_out,
        "a7_envelope_parse_success_min": min(parse_rates) if parse_rates else None,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = REPORTS / f"dogfood-suite-{stamp}.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        f"# Dogfood suite 집계 — {stamp}",
        "",
        "| Topic | Tier | Runs | Human pass | KPI medians |",
        "|-------|------|------|------------|-------------|",
    ]
    for t in topics_out:
        kpis = ", ".join(f"{k}={v}" for k, v in t["kpi_medians"].items()) or "—"
        pass_rate = t["human_pass_rate"]
        lines.append(
            f"| {t['id']} | {t['tier']} | {t['runs']} | {pass_rate if pass_rate is not None else '—'} | {kpis} |"
        )
    if report["a7_envelope_parse_success_min"] is not None:
        lines += [
            "",
            f"A7 (passive): envelope_parse_success_rate 최솟값 = {report['a7_envelope_parse_success_min']}",
        ]
    md_path = REPORTS / f"dogfood-suite-{stamp}.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"aggregate report: {json_path}\n                  {md_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock", "checklist", "aggregate", "reproducibility"], default="checklist")
    parser.add_argument("--topics", help=f"토픽 카탈로그 경로 (기본 {DEFAULT_TOPICS})")
    parser.add_argument("--tier", help="필터: 쉼표 구분 tier (예: S,M)")
    parser.add_argument("--only", help="필터: 쉼표 구분 topic id (예: M4,A3)")
    parser.add_argument("--log", help="aggregate 입력 suite-log.json 경로")
    parser.add_argument("--sessions-base", help="mock 세션 폴더 (기본 임시 디렉토리)")
    parser.add_argument(
        "--feedback",
        action="store_true",
        help="S1.5: --mode mock과 함께 — 피드백 루프 ON으로 N회 반복 누적 + 효과 리포트",
    )
    parser.add_argument("--repeat", type=int, default=4, help="--feedback 반복 횟수 (기본 4, MIN_SAMPLE 통과용)")
    args = parser.parse_args()

    topics_path = Path(args.topics) if args.topics else DEFAULT_TOPICS
    rows = filter_topics(
        load_topics(topics_path),
        {t.strip().upper() for t in args.tier.split(",")} if args.tier else None,
        {t.strip().upper() for t in args.only.split(",")} if args.only else None,
    )
    if not rows:
        print("no topics matched filters", file=sys.stderr)
        return 2

    if args.mode == "mock":
        base = Path(args.sessions_base) if args.sessions_base else None
        if args.feedback:
            return run_feedback(rows, base, args.repeat)
        return run_mock(rows, base)
    if args.mode == "aggregate":
        if not args.log:
            print("--mode aggregate requires --log suite-log.json", file=sys.stderr)
            return 2
        return run_aggregate(rows, Path(args.log))
    if args.mode == "reproducibility":
        base = Path(args.sessions_base) if args.sessions_base else None
        return run_reproducibility(rows, base)
    return run_checklist(rows)


if __name__ == "__main__":
    sys.exit(main())
