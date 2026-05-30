"""Human-gated bandit for composer turn profile recommendation (E1)."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

TurnProfileId = Literal["quick", "discuss", "review", "free"]

TURN_PROFILES: tuple[str, ...] = ("quick", "discuss", "review", "free")
DEFAULT_TURN_PROFILE = "discuss"
BANDIT_SCHEMA_VERSION = 1
UCB_C = 1.2
MAX_EVENTS = 200


def _root() -> Path:
    return Path(os.getenv("AGENT_LAB_ROOT", Path(__file__).resolve().parents[2]))


def bandit_store_path() -> Path:
    raw = os.getenv("AGENT_LAB_BANDIT_STORE", "").strip()
    if raw:
        return Path(raw).expanduser()
    return _root() / "data" / "turn_profile_bandit.json"


def _empty_store() -> dict[str, Any]:
    return {
        "schema_version": BANDIT_SCHEMA_VERSION,
        "profiles": {p: {"up": 0, "down": 0, "total": 0} for p in TURN_PROFILES},
        "events": [],
    }


def load_bandit_store(path: Path | None = None) -> dict[str, Any]:
    p = path or bandit_store_path()
    if not p.is_file():
        return _empty_store()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    profiles = data.setdefault("profiles", {})
    for pid in TURN_PROFILES:
        profiles.setdefault(pid, {"up": 0, "down": 0, "total": 0})
    data.setdefault("events", [])
    data["schema_version"] = BANDIT_SCHEMA_VERSION
    return data


def save_bandit_store(data: dict[str, Any], path: Path | None = None) -> Path:
    p = path or bandit_store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def infer_turn_profile(turn: dict[str, Any]) -> str:
    explicit = str(turn.get("turn_profile") or "").strip()
    if explicit in TURN_PROFILES:
        return explicit
    if turn.get("consensus_mode"):
        return "free"
    if turn.get("review_mode"):
        return "review"
    rounds = int(turn.get("agent_parallel_rounds") or 1)
    agents = turn.get("agents") or []
    if rounds <= 1 and len(agents) <= 1:
        return "quick"
    return "discuss"


def recommend_profile(
    store: dict[str, Any] | None = None,
    *,
    ucb_c: float = UCB_C,
) -> dict[str, Any]:
    """UCB1 over 👍 rate; unexplored profiles get exploration priority."""
    data = store or load_bandit_store()
    profiles: dict[str, dict[str, int]] = data.get("profiles") or {}
    total_all = sum(int(p.get("total", 0)) for p in profiles.values())
    scores: dict[str, float] = {}
    for pid in TURN_PROFILES:
        row = profiles.get(pid) or {"up": 0, "down": 0, "total": 0}
        n = int(row.get("total", 0))
        if n == 0:
            scores[pid] = 0.5 + ucb_c
            continue
        rate = int(row.get("up", 0)) / n
        explore = ucb_c * math.sqrt(math.log(max(total_all, 1)) / n)
        scores[pid] = rate + explore
    recommended = max(TURN_PROFILES, key=lambda p: scores.get(p, 0.0))
    return {
        "recommended": recommended,
        "default": DEFAULT_TURN_PROFILE,
        "scores": scores,
        "stats": profiles,
        "total_feedback": total_all,
    }


def record_turn_feedback(
    *,
    profile: str,
    vote: str,
    session_id: str = "",
    turn_index: int | None = None,
    meta: dict[str, Any] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    if profile not in TURN_PROFILES:
        raise ValueError(f"invalid turn profile: {profile}")
    vote_norm = vote.strip().lower()
    if vote_norm not in ("up", "down"):
        raise ValueError("vote must be up or down")

    data = load_bandit_store(path)
    row = data["profiles"].setdefault(profile, {"up": 0, "down": 0, "total": 0})
    if vote_norm == "up":
        row["up"] = int(row.get("up", 0)) + 1
    else:
        row["down"] = int(row.get("down", 0)) + 1
    row["total"] = int(row.get("total", 0)) + 1

    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "profile": profile,
        "vote": vote_norm,
        "session_id": session_id,
        "turn_index": turn_index,
    }
    if meta:
        event.update(meta)
    events: list[dict[str, Any]] = list(data.get("events") or [])
    events.append(event)
    data["events"] = events[-MAX_EVENTS:]
    save_bandit_store(data, path)
    rec = recommend_profile(data)
    return {"ok": True, "recorded": event, "recommendation": rec}


def patch_session_turn_feedback(
    folder: Path,
    *,
    turn_index: int = -1,
    vote: str,
    profile: str | None = None,
) -> dict[str, Any]:
    run_path = folder / "run.json"
    if not run_path.is_file():
        raise FileNotFoundError("run.json missing")
    data = json.loads(run_path.read_text(encoding="utf-8"))
    turns: list[dict[str, Any]] = list(data.get("turns") or [])
    if not turns:
        raise ValueError("no turns in run.json")
    idx = turn_index if turn_index >= 0 else len(turns) - 1
    if idx < 0 or idx >= len(turns):
        raise ValueError("turn_index out of range")
    turn = turns[idx]
    prof = profile or infer_turn_profile(turn)
    vote_norm = vote.strip().lower()
    if vote_norm not in ("up", "down"):
        raise ValueError("vote must be up or down")
    turn["feedback"] = {
        "vote": vote_norm,
        "profile": prof,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    turns[idx] = turn
    data["turns"] = turns
    run_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return turn["feedback"]
