"""S1 Phase A — outcome harvester: cross-session outcome ledger.

At turn end this module (a) patches ``turn_metrics`` into the just-written
``run.json`` turn and (b) appends one outcome line to ``.agent-lab/outcomes.jsonl``
under the project root. Both writes are independently flag-gated and fail-open:
any error is swallowed so the feedback machinery never blocks a room turn.

See docs/archive/rfcs/DESIGN-S1-FEEDBACK-LOOP.md (Phase A).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any
from weakref import WeakValueDictionary

from agent_lab.env_flags import env_bool
from agent_lab.run.meta import patch_run_meta, read_run_meta
from agent_lab.run.state import RunStateLike
from agent_lab.s1_flags import s1_flag_enabled
from agent_lab.time_utils import utc_now_iso as _now_iso
from agent_lab.turn_metrics import build_turn_metrics
from agent_lab.wisdom.index import _tokenize

log = logging.getLogger(__name__)

OUTCOME_LEDGER_SCHEMA_VERSION = 1
_OUTCOMES_RELPATH = Path(".agent-lab") / "outcomes.jsonl"

_LOCK_GUARD = threading.Lock()
_PATH_LOCKS: WeakValueDictionary[str, threading.Lock] = WeakValueDictionary()


def _path_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _LOCK_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[key] = lock
        return lock


def _default_outcomes_root() -> Path:
    """Repo root for the outcomes ledger (not ``src/`` package root).

    ``project_root()`` resolves to ``…/src`` for the in-tree package layout.
    Outcomes are written under the git/repo root ``.agent-lab/outcomes.jsonl``.
    """
    env_root = (os.getenv("AGENT_LAB_OUTCOMES_ROOT") or "").strip()
    if env_root:
        return Path(env_root)
    from agent_lab.workspace.roots import project_root

    root = project_root()
    # In-tree layout: src/agent_lab/… → project_root is …/src; ledger lives on parent.
    if root.name == "src" and (root.parent / ".agent-lab").is_dir():
        return root.parent
    if root.name == "src" and (root.parent / "pyproject.toml").is_file():
        return root.parent
    return root


def outcomes_path(root: Path | None = None) -> Path:
    """Resolve ``.agent-lab/outcomes.jsonl`` under the project root.

    Resolution order: explicit ``root`` arg → ``AGENT_LAB_OUTCOMES_ROOT`` env
    (S1.5 dogfood isolation) → repo root (not ``src/``).
    """
    if root is None:
        root = _default_outcomes_root()
    return Path(root) / _OUTCOMES_RELPATH


def agent_lab_project_root(root: Path | None = None) -> Path:
    """Resolve the repo root for ALL ``.agent-lab/`` runtime writes (ledger,
    traces, memory — HS1). ``AGENT_LAB_OUTCOMES_ROOT`` isolates the whole
    ``.agent-lab/`` tree, not just the outcomes ledger; the env var name
    predates HS1's traces/memory consumers.
    """
    return Path(root) if root is not None else _default_outcomes_root()


def load_outcome_rows(root: Path | None = None) -> list[dict[str, Any]]:
    """Read + parse every JSON line in the outcome ledger (malformed lines skipped).

    Shared reader for feedback_report and weakness_miner (HS1) — both bucket
    the same ledger, just by different keys.
    """
    path = outcomes_path(root)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def challenge_precision_enabled() -> bool:
    """S1 D1 (default off) — docs/S1-CHALLENGE-PRECISION.md. Record-only: never
    consumed by feedback_advisor yet, independent of the TURN_METRICS/
    OUTCOME_LEDGER supervisor-implicit trio (s1_flags._SUPERVISOR_S1_FLAGS)."""
    return env_bool("AGENT_LAB_CHALLENGE_PRECISION")


def _turn_acts_for_human_turn(folder: Path) -> list[dict[str, str]]:
    """Flat {"agent","act"} list for the just-completed human turn (S1 D1).

    Acts beyond CHALLENGE/BLOCK (e.g. NOTE, ENDORSE) never land in
    ``objections`` (core.objections.HARVEST_ACTS is BLOCK/CHALLENGE only), so
    challenge_precision reads chat.jsonl directly for the full act tally.
    """
    from agent_lab.agent.envelope import envelope_act
    from agent_lab.room.session_persist import load_session_messages
    from agent_lab.room.turn_state import current_turn_slice

    messages = load_session_messages(folder)
    if not messages:
        return []
    turn_msgs, _ = current_turn_slice(messages)
    acts: list[dict[str, str]] = []
    for m in turn_msgs:
        if m.role != "agent" or not m.agent:
            continue
        act = envelope_act(m.envelope)
        if not act:
            continue
        acts.append({"agent": str(m.agent), "act": str(act)})
    return acts


def _topic_text(folder: Path, run: RunStateLike) -> str:
    topic = str(run.get("topic") or "").strip()
    if topic:
        return topic
    topic_file = folder / "topic.txt"
    if topic_file.is_file():
        try:
            return topic_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return ""


def _topic_hash(topic: str) -> str:
    return "sha1:" + hashlib.sha1(topic.encode("utf-8")).hexdigest()[:16]


def build_outcome_record(
    folder: Path, topic: str, metrics: dict[str, Any], *, run_meta: RunStateLike | None = None
) -> dict[str, Any]:
    """Flatten turn_metrics into one cross-session ledger row."""
    from agent_lab.autonomy_ladder import infer_effective_autonomy_level
    from agent_lab.human_inbox import pending_inbox_items

    rollup_raw = metrics.get("oracle_rollup")
    rollup = rollup_raw if isinstance(rollup_raw, dict) else {}
    run = run_meta or {}
    contract_raw = run.get("turn_contract")
    contract = contract_raw if isinstance(contract_raw, dict) else {}
    level = infer_effective_autonomy_level(run)
    inbox_hit = bool(metrics.get("escalated")) or bool(pending_inbox_items(run))
    verdict = rollup.get("final_verdict")
    from agent_lab.room.turn_contract import derive_route_regrets

    contract_id = str(contract.get("contract_id") or "")
    regrets = derive_route_regrets(
        contract_id,
        escalated=bool(metrics.get("escalated")),
        final_verdict=str(verdict) if verdict else None,
        repair_attempts=int(rollup.get("repair_attempts") or 0),
        rounds_used=int(metrics.get("rounds_used") or 0),
        execution_present=bool(run.get("executions")),
        clarify_no_delta=bool(metrics.get("clarify_no_delta") or run.get("clarify_no_delta")),
        fsm_no_action=bool(metrics.get("fsm_no_action") or run.get("fsm_no_action")),
        subset_escalated=bool(metrics.get("subset_escalated") or run.get("subset_escalated")),
    )
    return {
        "v": OUTCOME_LEDGER_SCHEMA_VERSION,
        "ts": _now_iso(),
        # "turn" (Room turn close) vs "execute" (see record_execute_outcome).
        # Absent on rows written before this field existed — readers treat
        # missing phase as "turn" for backward compatibility.
        "phase": "turn",
        "session_id": folder.name,
        "topic_hash": _topic_hash(topic),
        "topic_terms": sorted(_tokenize(topic))[:24],
        "category": metrics.get("category") or "",
        "roles": metrics.get("roles") or {},
        "agents": metrics.get("agents") or [],
        "rounds_used": metrics.get("rounds_used") or 0,
        "escalated": bool(metrics.get("escalated")),
        "final_verdict": rollup.get("final_verdict"),
        "repair_attempts": rollup.get("repair_attempts") or 0,
        "objection_summary": metrics.get("objection_summary") or {},
        "objection_resolution": metrics.get("objection_resolution") or {},
        "consensus_reached": bool(metrics.get("consensus_reached")),
        "latency_ms": metrics.get("latency_ms") or 0,
        # S1.5 — advisor attribution (absent/"default" = baseline bucket in reports)
        "advisor_source": metrics.get("advisor_source") or "default",
        "combo_id": metrics.get("advisor_combo_id") or "",
        "autonomy_level": level,
        "human_inbox_escalation": inbox_hit,
        # S3a-0 — tool cards suggested at RECALL time (installed-but-unused capabilities)
        "tool_card_suggestions": list(metrics.get("tool_card_suggestions") or []),
        # HS1-1 — failure taxonomy tags (see turn_metrics._derive_failure_tags)
        "failure_tags": list(metrics.get("failure_tags") or []),
        "primary_tag": metrics.get("primary_tag"),
        # S1 D1 — record-only, not yet consumed (docs/S1-CHALLENGE-PRECISION.md)
        "challenge_precision": metrics.get("challenge_precision") or {},
        "contract_id": contract_id,
        "contract_source": str(contract.get("source") or ""),
        "safety_floor": str(contract.get("safety_floor") or ""),
        "task_kind": str(contract.get("task_kind") or ""),
        "risk": str(contract.get("risk") or ""),
        "execute_intent": bool(contract.get("execute_intent")),
        "route_regret_signals": list(regrets),
    }


def append_outcome(record: dict[str, Any], *, root: Path | None = None) -> None:
    """Atomically append one JSON line to the outcomes ledger."""
    path = outcomes_path(root)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _path_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)


def record_turn_outcome(folder: Path | None, human_turn: int) -> None:
    """Persist turn_metrics + append to the outcome ledger (flag-gated, fail-open).

    Called from ``_finalize_durable_turn`` after run.json has been written for a
    completed turn. ``AGENT_LAB_TURN_METRICS`` gates the run.json patch;
    ``AGENT_LAB_OUTCOME_LEDGER`` gates the ledger append.
    """
    if folder is None:
        return
    try:
        run = read_run_meta(folder)
        want_metrics = s1_flag_enabled("AGENT_LAB_TURN_METRICS", run_meta=run)
        want_ledger = s1_flag_enabled("AGENT_LAB_OUTCOME_LEDGER", run_meta=run)
        if not (want_metrics or want_ledger):
            return
        turns = run.get("turns") or []
        if not turns:
            return
        turn_acts = _turn_acts_for_human_turn(folder) if challenge_precision_enabled() else []
        metrics = build_turn_metrics(
            turns[-1],
            objections=run.get("objections") or [],
            executions=run.get("executions") or [],
            human_turn=human_turn,
            turn_acts=turn_acts,
        )
        if want_metrics:

            def _patch(current: RunStateLike) -> RunStateLike:
                rows = current.get("turns")
                if isinstance(rows, list) and rows and isinstance(rows[-1], dict):
                    rows[-1]["turn_metrics"] = metrics
                return current

            patch_run_meta(folder, _patch)
        if want_ledger:
            append_outcome(build_outcome_record(folder, _topic_text(folder, run), metrics, run_meta=run))
    except Exception:  # fail-open: feedback must never block a turn
        log.warning("record_turn_outcome failed for %s", folder, exc_info=True)


def _advisor_fields_for_execute(run: RunStateLike, last_turn: dict[str, Any]) -> dict[str, Any]:
    """Resolve advisor attribution for execute rows (P0-5 lift).

    Turn snapshot ``category`` is primary; fall back to ``turn_metrics`` and
    in-flight ``_turn_category`` when execute runs after turn close.
    """
    layers: list[dict[str, Any]] = []
    cat = last_turn.get("category")
    if isinstance(cat, dict):
        layers.append(cat)
    metrics = last_turn.get("turn_metrics")
    if isinstance(metrics, dict):
        layers.append(metrics)
    turn_cat = run.get("_turn_category")
    if isinstance(turn_cat, dict):
        layers.append(turn_cat)

    advisor_source = "default"
    combo_id = ""
    tool_cards: list[Any] = []
    for layer in layers:
        src = str(layer.get("advisor_source") or "").strip().lower()
        if src in ("default", "history", "explore"):
            advisor_source = src
        if layer.get("advisor_combo_id"):
            combo_id = str(layer.get("advisor_combo_id") or "")
        if layer.get("tool_card_suggestions"):
            tool_cards = list(layer.get("tool_card_suggestions") or [])
    return {
        "advisor_source": advisor_source,
        "combo_id": combo_id,
        "tool_card_suggestions": tool_cards,
    }


def _execution_verdict(execution: dict[str, Any]) -> str:
    oracle = execution.get("oracle") if isinstance(execution.get("oracle"), dict) else {}
    verdict = str(oracle.get("verdict") or "").strip().lower()
    if verdict:
        return verdict
    status = str((execution.get("verify_after_merge") or {}).get("status") or "").strip().lower()
    return {"passed": "pass", "failed": "fail", "skipped": "skipped"}.get(status, "")


def _build_execute_outcome_record(
    folder: Path,
    run: RunStateLike,
    last_turn: dict[str, Any],
    execution: dict[str, Any],
    *,
    advisor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    category = last_turn.get("category") if isinstance(last_turn.get("category"), dict) else {}
    roles = last_turn.get("roles") if isinstance(last_turn.get("roles"), dict) else {}
    consensus = last_turn.get("consensus") if isinstance(last_turn.get("consensus"), dict) else {}
    advisor = advisor or _advisor_fields_for_execute(run, last_turn)
    topic = _topic_text(folder, run)
    verdict = _execution_verdict(execution)
    evaluation = None
    if verdict:
        from agent_lab.eval_harness_ingest import score_execute_outcome

        evaluation = score_execute_outcome(verdict)
    contract_raw = run.get("turn_contract")
    contract = contract_raw if isinstance(contract_raw, dict) else {}
    from agent_lab.room.turn_contract import derive_route_regrets

    contract_id = str(contract.get("contract_id") or "")
    regrets = derive_route_regrets(
        contract_id,
        escalated=bool(category.get("escalated_from")),
        final_verdict=verdict or None,
        repair_attempts=len(execution.get("repair_history") or []),
        rounds_used=int(last_turn.get("agent_parallel_rounds") or 0),
        execution_present=True,
        clarify_no_delta=bool(run.get("clarify_no_delta")),
        fsm_no_action=bool(run.get("fsm_no_action")),
        subset_escalated=bool(run.get("subset_escalated")),
    )
    # HS1-1 — execute rows are where Oracle-derived tags actually land:
    # verdicts arrive after the plan turn closed, so the turn row rarely sees
    # them (2026-07 ledger audit: 195/197 turn rows had final_verdict null).
    from agent_lab.turn_metrics import derive_execution_failure_tags

    failure_tags = derive_execution_failure_tags(execution)
    record: dict[str, Any] = {
        "v": OUTCOME_LEDGER_SCHEMA_VERSION,
        "ts": _now_iso(),
        "phase": "execute",
        "session_id": folder.name,
        "topic_hash": _topic_hash(topic),
        "topic_terms": sorted(_tokenize(topic))[:24],
        "category": str(category.get("value") or ""),
        "roles": {str(k): str(v) for k, v in roles.items()},
        "agents": list(last_turn.get("agents") or []),
        "rounds_used": int(last_turn.get("agent_parallel_rounds") or 0),
        "escalated": bool(category.get("escalated_from")),
        "execution_id": str(execution.get("id") or ""),
        "final_verdict": verdict or None,
        "harness_resolved": evaluation["resolved"] if evaluation else None,
        "harness_attribution": evaluation["attribution"] if evaluation else None,
        "harness_reason": evaluation["reason"] if evaluation else None,
        "repair_attempts": len(execution.get("repair_history") or []),
        "objection_summary": {},
        "objection_resolution": {},
        "consensus_reached": str(consensus.get("status") or "") == "reached",
        "latency_ms": 0,
        "advisor_source": advisor.get("advisor_source") or "default",
        "combo_id": advisor.get("combo_id") or "",
        "tool_card_suggestions": list(advisor.get("tool_card_suggestions") or []),
        "failure_tags": failure_tags,
        "primary_tag": failure_tags[0] if failure_tags else None,
        "contract_id": contract_id,
        "contract_source": str(contract.get("source") or ""),
        "safety_floor": str(contract.get("safety_floor") or ""),
        "task_kind": str(contract.get("task_kind") or ""),
        "risk": str(contract.get("risk") or ""),
        "execute_intent": bool(contract.get("execute_intent")),
        "route_regret_signals": list(regrets),
    }
    from agent_lab.autonomy_ladder import infer_effective_autonomy_level
    from agent_lab.human_inbox import pending_inbox_items

    record["autonomy_level"] = infer_effective_autonomy_level(run)
    record["human_inbox_escalation"] = bool(pending_inbox_items(run))
    from agent_lab.self_patch import classify_self_patch

    touched = list(execution.get("source_touched_paths") or execution.get("touched_paths") or [])
    record["self_patch"] = classify_self_patch(touched)
    return record


def dogfood_execute_outcomes_enabled() -> bool:
    """When set, mock dogfood emits synthetic execute-phase rows for S1 lift."""
    return env_bool("AGENT_LAB_DOGFOOD_EXECUTE_OUTCOMES")


def _mock_verdict_for_advisor_source(source: str) -> str:
    """Mock-only structural lift signal — not live Oracle evidence."""
    if source in ("history", "explore"):
        return "pass"
    return "fail"


def record_mock_execute_outcome(folder: Path | None) -> None:
    """Emit execute-phase row after mock Room session (P0-5 dogfood lift).

    Live missions must use ``record_execute_outcome`` from Oracle verify instead.
    """
    if folder is None or not dogfood_execute_outcomes_enabled():
        return
    try:
        run = read_run_meta(folder)
        if not s1_flag_enabled("AGENT_LAB_OUTCOME_LEDGER", run_meta=run):
            return
        turns = run.get("turns") or []
        if not turns or not isinstance(turns[-1], dict):
            return
        last_turn = turns[-1]
        advisor = _advisor_fields_for_execute(run, last_turn)
        # Self-describing evidence: this row is a synthetic lift signal, not a
        # real Oracle response — without it, HS1-1 would mis-tag every mock
        # pass as false_success (pass with no cited evidence).
        execution = {
            "id": f"mock-exec-{folder.name}",
            "oracle": {
                "verdict": _mock_verdict_for_advisor_source(str(advisor.get("advisor_source") or "default")),
                "evidence": ["synthetic dogfood execute row (AGENT_LAB_DOGFOOD_EXECUTE_OUTCOMES)"],
            },
            "repair_history": [],
        }
        append_outcome(_build_execute_outcome_record(folder, run, last_turn, execution, advisor=advisor))
    except Exception:
        log.warning("record_mock_execute_outcome failed for %s", folder, exc_info=True)


def record_execute_outcome(folder: Path | None, execution: dict[str, Any]) -> None:
    """Persist one execute-completion outcome row (flag-gated, fail-open).

    ``record_turn_outcome`` only fires when a Room turn closes, and rolls up
    whatever ``executions`` exist in run.json *at that moment*. Oracle
    verdicts are decided by execute/verify, which normally happens *after*
    the turn that produced the plan has already closed its ledger row — so a
    session with no follow-up chat turn after execute never emits a row
    carrying the verdict, and the S1 lift signal (§1.4 KPI) stays permanently
    empty (2026-07 diagnosis: 40/40 ledger rows had ``final_verdict: null``).

    Called from ``_record_verify_after_merge`` right after one execution's
    Oracle verdict is known, so it also fires once per repair-retry attempt.
    Reuses the last Room turn's category/roles/agents for the S2 episode key
    (mission x agent-subset x result, §1 S2) since execute itself has no
    role-combo concept of its own.
    """
    if folder is None:
        return
    try:
        run = read_run_meta(folder)
        if not s1_flag_enabled("AGENT_LAB_OUTCOME_LEDGER", run_meta=run):
            return
        turns = run.get("turns") or []
        last_turn = turns[-1] if turns and isinstance(turns[-1], dict) else {}
        advisor = _advisor_fields_for_execute(run, last_turn)
        record = _build_execute_outcome_record(folder, run, last_turn, execution, advisor=advisor)
        append_outcome(record)
    except Exception:  # fail-open: feedback must never block execute
        log.warning("record_execute_outcome failed for %s", folder, exc_info=True)
