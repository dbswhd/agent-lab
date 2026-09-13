"""Ideation lane state — ``run.json.ideation`` (RI-02).

Scope (see ``docs/ROOM-IDEATION-PLAN-2026-09.md`` §4.1):

- ``run.json.ideation`` is the single authority for structured idea state.
  ``concept.md`` is a human-readable derived output, never an input authority.
- No separate DB/journal, no migration: a session without an ``ideation`` key
  keeps its existing behaviour and this module never creates one implicitly.
- Selecting an option is **not** an execute approval. Nothing here starts a
  plan workflow, mission, or execution; the execute gate stays where it is.

F4 discipline: mutations here operate on an in-memory mapping. Disk writes go
through ``patch_run_meta`` / turn-end replay at the call site, as everywhere
else.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from agent_lab.run.meta import stamp_run_meta
from agent_lab.run.state import RunStateLike
from agent_lab.time_utils import utc_now_iso

SCHEMA_VERSION = 1
IDEATION_KEY = "ideation"

STAGE_EXPLORE = "explore"
STAGE_SHAPE = "shape"
STAGE_PLAN = "plan"
VALID_STAGES = frozenset({STAGE_EXPLORE, STAGE_SHAPE, STAGE_PLAN})
IDEATION_NO_EXECUTE_REASON = "ideation_lane_no_execute"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class IdeationError(Exception):
    """Invalid ideation state or operation."""


class IdeationStaleError(IdeationError):
    """Mutation carried a revision that is no longer current (→ HTTP 409)."""

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"stale ideation revision: expected {expected}, current {actual}")
        self.expected = expected
        self.actual = actual


# --------------------------------------------------------------------------
# construction / access
# --------------------------------------------------------------------------


def new_ideation(
    *,
    original_concept: str = "",
    desired_change: str = "",
    constraints: Sequence[str] | None = None,
    assumptions: Sequence[str] | None = None,
    open_questions: Sequence[str] | None = None,
) -> dict[str, Any]:
    """A fresh ideation payload at ``explore`` stage, revision 0."""
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "stage": STAGE_EXPLORE,
        "brief": {
            "original_concept": str(original_concept or ""),
            "desired_change": str(desired_change or ""),
            "constraints": _str_list(constraints),
            "assumptions": _str_list(assumptions),
            "open_questions": _str_list(open_questions),
        },
        "options": [],
        "selection": None,
        "concept": None,
        "decisions": [],
        "plan_source_revision": None,
        "plan_source_hash": None,
        "updated_at": utc_now_iso(),
    }


def read_ideation(run: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return the ideation payload, or ``None`` for a non-ideation session."""
    if not isinstance(run, Mapping):
        return None
    raw = run.get(IDEATION_KEY)
    return dict(raw) if isinstance(raw, Mapping) else None


def is_ideation_session(run: Mapping[str, Any] | None) -> bool:
    return read_ideation(run) is not None


def ensure_ideation_no_execute(run: Mapping[str, Any] | None) -> None:
    """Reject legacy execution entry points when a run belongs to the idea lane."""
    if is_ideation_session(run):
        raise IdeationError(IDEATION_NO_EXECUTE_REASON)


def option_by_id(state: Mapping[str, Any], option_id: str) -> dict[str, Any] | None:
    for option in state.get("options") or []:
        if isinstance(option, Mapping) and option.get("id") == option_id:
            return dict(option)
    return None


def selected_option(state: Mapping[str, Any]) -> dict[str, Any] | None:
    """The option the user chose, when the selection points at a stored option."""
    selection = state.get("selection")
    if not isinstance(selection, Mapping):
        return None
    return option_by_id(state, str(selection.get("option_id") or ""))


def rejected_option_ids(state: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    for decision in state.get("decisions") or []:
        if isinstance(decision, Mapping) and decision.get("kind") == "reject":
            target = str(decision.get("option_id") or "")
            if target and target not in out:
                out.append(target)
    return out


def plan_is_stale(state: Mapping[str, Any]) -> bool:
    """True when a plan was recorded against an older ideation revision."""
    source = state.get("plan_source_revision")
    if not isinstance(source, int):
        return False
    return int(state.get("revision") or 0) > source


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


def validate_ideation(raw: Any) -> dict[str, Any]:
    """Validate one ideation payload, returning a normalized copy."""
    if not isinstance(raw, Mapping):
        raise IdeationError("ideation must be a mapping")
    state = dict(raw)

    version = state.get("schema_version")
    if version != SCHEMA_VERSION:
        raise IdeationError(f"unsupported ideation schema_version: {version!r}")

    revision = state.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise IdeationError("ideation.revision must be a non-negative int")

    stage = state.get("stage")
    if stage not in VALID_STAGES:
        raise IdeationError(f"invalid ideation.stage: {stage!r}")

    brief = state.get("brief")
    if not isinstance(brief, Mapping):
        raise IdeationError("ideation.brief must be a mapping")

    options = state.get("options")
    if not isinstance(options, list):
        raise IdeationError("ideation.options must be a list")
    seen: set[str] = set()
    for index, option in enumerate(options):
        if not isinstance(option, Mapping):
            raise IdeationError(f"ideation.options[{index}] is not a mapping")
        option_id = str(option.get("id") or "")
        if not _ID_RE.match(option_id):
            raise IdeationError(f"invalid option id at index {index}: {option.get('id')!r}")
        if option_id in seen:
            raise IdeationError(f"duplicate option id: {option_id!r}")
        seen.add(option_id)

    selection = state.get("selection")
    if selection is not None:
        if not isinstance(selection, Mapping):
            raise IdeationError("ideation.selection must be a mapping or null")
        selected_id = str(selection.get("option_id") or "")
        if not _ID_RE.match(selected_id):
            raise IdeationError(f"invalid selection.option_id: {selection.get('option_id')!r}")
        parents = selection.get("parent_ids")
        if parents is not None and not isinstance(parents, list):
            raise IdeationError("selection.parent_ids must be a list or null")
        if selected_id not in seen and not (parents or []):
            raise IdeationError(f"selection.option_id {selected_id!r} is not a known option and has no parents")
        source_revision = selection.get("source_revision")
        if not isinstance(source_revision, int) or isinstance(source_revision, bool):
            raise IdeationError("selection.source_revision must be an int")

    decisions = state.get("decisions")
    if not isinstance(decisions, list) or not all(isinstance(d, Mapping) for d in decisions):
        raise IdeationError("ideation.decisions must be a list of mappings")

    for key in ("plan_source_revision",):
        value = state.get(key)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
            raise IdeationError(f"ideation.{key} must be an int or null")

    return state


def validate_run_ideation(run: Mapping[str, Any] | None) -> None:
    """No-op for sessions without an ``ideation`` key (no implicit migration)."""
    if not isinstance(run, Mapping) or IDEATION_KEY not in run:
        return
    validate_ideation(run.get(IDEATION_KEY))


# --------------------------------------------------------------------------
# mutation
# --------------------------------------------------------------------------

Mutator = Callable[[dict[str, Any]], dict[str, Any] | None]


def mutate_ideation(
    run_meta: RunStateLike,
    mutator: Mutator,
    *,
    expected_revision: int | None = None,
) -> dict[str, Any]:
    """Apply ``mutator`` to the ideation payload and bump ``revision``.

    ``expected_revision`` implements optimistic locking: a stale value raises
    ``IdeationStaleError`` and leaves ``run_meta`` untouched. Writes stay
    in-memory (F4) — the caller persists via ``patch_run_meta`` or turn-end
    replay.
    """
    state = read_ideation(run_meta)
    if state is None:
        raise IdeationError("session has no ideation state")
    state = validate_ideation(state)

    current = int(state["revision"])
    if expected_revision is not None and int(expected_revision) != current:
        raise IdeationStaleError(int(expected_revision), current)

    working = _deep_copy(state)
    result = mutator(working)
    updated = validate_ideation(result if isinstance(result, Mapping) else working)
    updated["revision"] = current + 1
    updated["updated_at"] = utc_now_iso()
    stamp_run_meta(run_meta, **{IDEATION_KEY: updated})
    return updated


def start_ideation(run_meta: RunStateLike, state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Attach ideation state to a session that opted in. Never called implicitly."""
    payload = validate_ideation(dict(state) if state is not None else new_ideation())
    stamp_run_meta(run_meta, **{IDEATION_KEY: payload})
    return payload


# --------------------------------------------------------------------------
# operations (mutators)
# --------------------------------------------------------------------------


def set_brief(**fields: Any) -> Mutator:
    def _apply(state: dict[str, Any]) -> dict[str, Any]:
        brief = dict(state.get("brief") or {})
        for key, value in fields.items():
            if key in ("constraints", "assumptions", "open_questions"):
                brief[key] = _str_list(value)
            else:
                brief[key] = "" if value is None else str(value)
        state["brief"] = brief
        return state

    return _apply


def set_options(options: Sequence[Mapping[str, Any]]) -> Mutator:
    """Replace the candidate set. Option ids are stable identifiers, not indices."""

    def _apply(state: dict[str, Any]) -> dict[str, Any]:
        state["options"] = [_normalize_option(option, index) for index, option in enumerate(options)]
        return state

    return _apply


def select_option(option_id: str, *, reason: str = "") -> Mutator:
    """Record the user's choice and move to ``shape``. Not an execute approval."""

    def _apply(state: dict[str, Any]) -> dict[str, Any]:
        if option_by_id(state, option_id) is None:
            raise IdeationError(f"unknown option id: {option_id!r}")
        state["selection"] = {
            "option_id": option_id,
            "parent_ids": [],
            "reason": str(reason or ""),
            "source_revision": int(state["revision"]),
        }
        state["stage"] = STAGE_SHAPE
        state["decisions"] = _append_decision(
            state,
            {"kind": "select", "option_id": option_id, "reason": str(reason or ""), "source": "user"},
        )
        return state

    return _apply


def combine_options(
    parent_ids: Sequence[str],
    *,
    new_id: str,
    title: str = "",
    reason: str = "",
) -> Mutator:
    """Select a new option combined from existing ones, keeping parent links."""

    def _apply(state: dict[str, Any]) -> dict[str, Any]:
        parents = [str(p) for p in parent_ids]
        if not parents:
            raise IdeationError("combine_options requires at least one parent id")
        for parent in parents:
            if option_by_id(state, parent) is None:
                raise IdeationError(f"unknown option id: {parent!r}")
        if not _ID_RE.match(new_id):
            raise IdeationError(f"invalid combined option id: {new_id!r}")
        if option_by_id(state, new_id) is not None:
            raise IdeationError(f"option id already exists: {new_id!r}")
        state["selection"] = {
            "option_id": new_id,
            "parent_ids": parents,
            "title": str(title or ""),
            "reason": str(reason or ""),
            "source_revision": int(state["revision"]),
        }
        state["stage"] = STAGE_SHAPE
        state["decisions"] = _append_decision(
            state,
            {
                "kind": "combine",
                "option_id": new_id,
                "parent_ids": parents,
                "reason": str(reason or ""),
                "source": "user",
            },
        )
        return state

    return _apply


def reject_option(option_id: str, *, reason: str = "") -> Mutator:
    """Record a rejection with its reason so the candidate does not silently return."""

    def _apply(state: dict[str, Any]) -> dict[str, Any]:
        if option_by_id(state, option_id) is None:
            raise IdeationError(f"unknown option id: {option_id!r}")
        state["decisions"] = _append_decision(
            state,
            {"kind": "reject", "option_id": option_id, "reason": str(reason or ""), "source": "user"},
        )
        return state

    return _apply


def back_to_explore(*, reason: str = "") -> Mutator:
    """Return to exploration without discarding earlier decisions."""

    def _apply(state: dict[str, Any]) -> dict[str, Any]:
        state["stage"] = STAGE_EXPLORE
        state["selection"] = None
        state["decisions"] = _append_decision(state, {"kind": "reopen", "reason": str(reason or ""), "source": "user"})
        return state

    return _apply


def set_concept(concept: Mapping[str, Any]) -> Mutator:
    def _apply(state: dict[str, Any]) -> dict[str, Any]:
        state["concept"] = dict(concept)
        return state

    return _apply


def enter_plan_stage() -> Mutator:
    """Move to ``plan``. This is a stage marker, not a plan approval."""

    def _apply(state: dict[str, Any]) -> dict[str, Any]:
        state["stage"] = STAGE_PLAN
        return state

    return _apply


def record_plan_source(*, source_hash: str | None = None) -> Mutator:
    """Link the written plan to the ideation revision it reflected."""

    def _apply(state: dict[str, Any]) -> dict[str, Any]:
        state["plan_source_revision"] = int(state["revision"]) + 1
        state["plan_source_hash"] = None if source_hash is None else str(source_hash)
        return state

    return _apply


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

_OPTION_TEXT_FIELDS = ("title", "principle", "usage", "difference", "tradeoff", "first_experiment")


def _normalize_option(option: Mapping[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(option, Mapping):
        raise IdeationError(f"option[{index}] is not a mapping")
    raw_id = str(option.get("id") or "").strip().lower()
    if not raw_id:
        raise IdeationError(f"option[{index}] has no id — ids must be stable, not positional")
    if not _ID_RE.match(raw_id):
        raise IdeationError(f"invalid option id: {option.get('id')!r}")
    normalized: dict[str, Any] = {"id": raw_id}
    if option.get("agent"):
        # Provenance only — which seat produced it, never a quality signal.
        normalized["agent"] = str(option.get("agent"))
    for field in _OPTION_TEXT_FIELDS:
        normalized[field] = str(option.get(field) or "")
    normalized["refs"] = _str_list(option.get("refs"))
    # Keep the raw model text when structured parsing failed — never hide it.
    if option.get("raw"):
        normalized["raw"] = str(option.get("raw"))
    if option.get("parse_error"):
        normalized["parse_error"] = str(option.get("parse_error"))
    return normalized


def _append_decision(state: Mapping[str, Any], decision: Mapping[str, Any]) -> list[dict[str, Any]]:
    decisions = [dict(d) for d in (state.get("decisions") or []) if isinstance(d, Mapping)]
    entry = dict(decision)
    entry.setdefault("ts", utc_now_iso())
    entry["revision"] = int(state.get("revision") or 0)
    decisions.append(entry)
    return decisions


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    raise IdeationError(f"expected a list of strings, got {type(value).__name__}")


def _deep_copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy(v) for v in value]
    return value


# --------------------------------------------------------------------------
# turn policy (RI-03)
# --------------------------------------------------------------------------
#
# The idea lane reuses the existing Room turn machinery; it does not add a
# second workflow engine. These predicates are the only thing the turn policy
# needs to know, and they all answer ``False``/``None`` for a session without
# ``run.json.ideation`` — existing sessions keep their behaviour exactly.


def ideation_stage(run: Mapping[str, Any] | None) -> str | None:
    """``explore`` / ``shape`` / ``plan``, or ``None`` for a non-ideation session."""
    state = read_ideation(run)
    if state is None:
        return None
    stage = str(state.get("stage") or "")
    return stage if stage in VALID_STAGES else None


def suppresses_plan_side_effects(run: Mapping[str, Any] | None) -> bool:
    """True while exploring or shaping.

    Exploration must not be interrupted by the plan FSM bootstrap, CLARIFY
    waits, task claims, or the every-turn auto Scribe. None of this changes an
    approval boundary — it only stops side effects from firing on a lane whose
    turns produce candidate ideas.
    """
    stage = ideation_stage(run)
    return stage in (STAGE_EXPLORE, STAGE_SHAPE)


def allows_scribe(run: Mapping[str, Any] | None) -> bool:
    """Scribe runs on the idea lane only after an explicit "make a plan" request.

    Reaching ``plan`` stage is that request (§4.2) — a consensus verdict, a
    skill intent, or a refresh is not.
    """
    stage = ideation_stage(run)
    if stage is None:
        return True
    return stage == STAGE_PLAN


def uses_execute_history_routing(run: Mapping[str, Any] | None) -> bool:
    """Execution success is not an idea-quality signal (§3.1)."""
    return ideation_stage(run) is None
