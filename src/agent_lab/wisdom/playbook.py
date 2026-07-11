"""HS2 PLAYBOOK — ACE-style incremental knowledge bullets.

Flag-gated (``AGENT_LAB_PLAYBOOK``, default off). See
docs/DESIGN-HARNESS-SELF-IMPROVE.md §8.3, §9 HS2.

Storage is an **append-only** JSONL ledger (same discipline as
``outcome_harvester``/``weakness_miner``): ``add_bullet`` never rewrites a row
in place, it appends a new revision. ``load_bullets`` folds the ledger to
current state by keeping the latest row per ``pattern_id``. Curator rule
(§8.3): a pattern_id that already exists keeps its **original** description
and ``harness_rev`` — a new call only bumps ``evidence_count`` — so repeated
observations never silently rewrite what a bullet says or when it was created.

Source today (2026-07, HS2-3/4): ``correction_harvester.py``, only after a
Human Inbox ``correction_rule`` approval — see
``correction_harvester.promote_correction_rule``. HS1's weakness patterns and
HS3's harness_proposer patches are later sources (not wired yet).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from agent_lab.time_utils import utc_now_iso_seconds as _now_iso
from agent_lab.env_flags import env_bool

PLAYBOOK_SCHEMA_VERSION = 1
HARNESS_REV_UNSET = "manifest@sha:none"  # HS5 (manifest.json SSOT) not shipped yet

_store_lock = threading.Lock()


def playbook_enabled() -> bool:
    """AGENT_LAB_PLAYBOOK (default off)."""
    return env_bool("AGENT_LAB_PLAYBOOK")


@dataclass
class PlaybookBullet:
    id: str
    description: str
    pattern_id: str
    evidence_count: int
    status: str  # "active" | "quarantined" (HS5-7, not wired yet — always "active" today)
    harness_rev: str
    updated_at: str


def playbook_path(root: Path | None = None) -> Path:
    """Path to the playbook JSONL. Override via AGENT_LAB_PLAYBOOK_PATH."""
    override = (os.getenv("AGENT_LAB_PLAYBOOK_PATH") or "").strip()
    if override:
        return Path(override).expanduser()
    from agent_lab.outcome_harvester import agent_lab_project_root

    return agent_lab_project_root(root) / ".agent-lab" / "wisdom" / "playbook.jsonl"


def _bullet_id(pattern_id: str) -> str:
    """Deterministic from pattern_id so repeated appends for the same pattern
    fold to the same bullet on read (see module docstring)."""
    return "pb:" + hashlib.sha1(pattern_id.encode("utf-8")).hexdigest()[:10]


def load_bullets(*, status: str | None = None, path: Path | None = None) -> list[PlaybookBullet]:
    """Fold the append-only ledger to current state (latest row per pattern_id).

    Returns bullets sorted by ``updated_at`` descending (most recently
    reinforced first). ``status`` filters the folded view (e.g. "active").
    """
    target = path or playbook_path()
    if not target.is_file():
        return []
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return []
    latest: dict[str, PlaybookBullet] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        bullet = PlaybookBullet(
            id=str(raw.get("id") or ""),
            description=str(raw.get("description") or ""),
            pattern_id=str(raw.get("pattern_id") or ""),
            evidence_count=int(raw.get("evidence_count") or 0),
            status=str(raw.get("status") or "active"),
            harness_rev=str(raw.get("harness_rev") or HARNESS_REV_UNSET),
            updated_at=str(raw.get("updated_at") or ""),
        )
        if bullet.id:
            latest[bullet.id] = bullet  # last write wins — later lines overwrite earlier ones
    bullets = list(latest.values())
    if status is not None:
        bullets = [b for b in bullets if b.status == status]
    bullets.sort(key=lambda b: b.updated_at, reverse=True)
    return bullets


def quarantine_bullets_by_harness_rev(
    harness_rev: str, *, path: Path | None = None, root: Path | None = None
) -> list[str]:
    """HS5-7 — flip every active bullet created at ``harness_rev`` to
    ``quarantined`` (append-only revision row, not a delete — negative
    results stay auditable). ``load_bullets(status="active", ...)`` (used by
    ``playbook_bullets_for_topic``) already excludes quarantined bullets, so
    no separate RECALL filter is needed beyond this write.

    Called when a merged ``harness_patch`` is rolled back — bullets whose
    provenance is the reverted revision can no longer be trusted.
    """
    target = path or playbook_path(root)
    quarantined: list[str] = []
    for bullet in load_bullets(status="active", path=target):
        if bullet.harness_rev != harness_rev:
            continue
        revised = PlaybookBullet(
            id=bullet.id,
            description=bullet.description,
            pattern_id=bullet.pattern_id,
            evidence_count=bullet.evidence_count,
            status="quarantined",
            harness_rev=bullet.harness_rev,
            updated_at=_now_iso(),
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"v": PLAYBOOK_SCHEMA_VERSION, **asdict(revised)}, ensure_ascii=False) + "\n")
        quarantined.append(bullet.id)
    return quarantined


def add_bullet(
    description: str,
    pattern_id: str,
    *,
    harness_rev: str = HARNESS_REV_UNSET,
    path: Path | None = None,
) -> PlaybookBullet:
    """Curator write: new pattern_id creates a bullet; a recurring one only
    bumps evidence_count (description/harness_rev pinned to first write)."""
    description = description.strip()
    pattern_id = pattern_id.strip()
    if not description or not pattern_id:
        raise ValueError("playbook bullet requires description and pattern_id")

    target = path or playbook_path()
    with _store_lock:
        existing = {b.id: b for b in load_bullets(path=target)}
        bullet_id = _bullet_id(pattern_id)
        prior = existing.get(bullet_id)
        if prior is not None:
            bullet = PlaybookBullet(
                id=bullet_id,
                description=prior.description,
                pattern_id=prior.pattern_id,
                evidence_count=prior.evidence_count + 1,
                status=prior.status,
                harness_rev=prior.harness_rev,
                updated_at=_now_iso(),
            )
        else:
            bullet = PlaybookBullet(
                id=bullet_id,
                description=description,
                pattern_id=pattern_id,
                evidence_count=1,
                status="active",
                harness_rev=harness_rev,
                updated_at=_now_iso(),
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"v": PLAYBOOK_SCHEMA_VERSION, **asdict(bullet)}, ensure_ascii=False) + "\n")
    return bullet


def _score_bullet(bullet: PlaybookBullet, tokens: set[str]) -> float:
    from agent_lab.wisdom.index import _tokenize

    haystack = _tokenize(bullet.description)
    overlap = len(haystack & tokens)
    if not overlap:
        return 0.0
    return overlap + bullet.evidence_count * 0.1


def playbook_bullets_for_topic(topic: str, k: int = 3, *, path: Path | None = None) -> list[PlaybookBullet]:
    """HS2-2 — active bullets whose description keyword-overlaps ``topic``,
    ranked by overlap then evidence_count, top-k. Empty when disabled/no match."""
    if not playbook_enabled():
        return []
    from agent_lab.wisdom.index import _tokenize

    tokens = _tokenize(topic)
    if not tokens:
        return []
    bullets = load_bullets(status="active", path=path)
    scored = [(b, _score_bullet(b, tokens)) for b in bullets]
    scored = [(b, s) for b, s in scored if s > 0]
    scored.sort(key=lambda x: (-x[1], -x[0].evidence_count))
    return [b for b, _ in scored[:k]]


__all__ = [
    "PlaybookBullet",
    "playbook_enabled",
    "playbook_path",
    "load_bullets",
    "add_bullet",
    "quarantine_bullets_by_harness_rev",
    "playbook_bullets_for_topic",
]
