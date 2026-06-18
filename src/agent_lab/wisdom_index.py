"""Evidence + mission notepad FTS-lite index (MB-10, Hermes-inspired)."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.evidence_ledger import evidence_path, read_evidence_tail
from agent_lab.mission_notepad import MISSION_NOTEPAD_FILES, mission_notepad_dir

_TOKEN_RE = re.compile(r"[\w가-힣]+", re.UNICODE)
_INDEX_FILENAME = "wisdom_index.json"
_DEFAULT_LIMIT = 20


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def wisdom_index_enabled(run: dict[str, Any] | None = None) -> bool:
    raw = (os.getenv("AGENT_LAB_WISDOM_INDEX") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    if run:
        from agent_lab.mission_loop import get_mission_loop

        return bool(get_mission_loop(run).get("enabled"))
    return False


def wisdom_cross_session_enabled() -> bool:
    raw = (os.getenv("AGENT_LAB_WISDOM_CROSS_SESSION") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return raw in ("1", "true", "yes", "on")


def index_path(folder: Path) -> Path:
    return mission_notepad_dir(folder) / _INDEX_FILENAME


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text) if len(token) >= 2}


def _snippet(text: str, *, query_terms: set[str], max_chars: int = 220) -> str:
    compact = " ".join(text.split())
    if not compact:
        return ""
    lower = compact.lower()
    best_at = -1
    for term in sorted(query_terms, key=len, reverse=True):
        pos = lower.find(term)
        if pos >= 0 and (best_at < 0 or pos < best_at):
            best_at = pos
    if best_at < 0:
        return compact[:max_chars] + ("…" if len(compact) > max_chars else "")
    start = max(0, best_at - 60)
    chunk = compact[start : start + max_chars]
    if start > 0:
        chunk = "…" + chunk
    if start + max_chars < len(compact):
        chunk += "…"
    return chunk


def _evidence_document(entry: dict[str, Any], *, index: int) -> dict[str, Any]:
    event = str(entry.get("event") or entry.get("kind") or "evidence")
    parts = [
        event,
        str(entry.get("execution_id") or ""),
        str(entry.get("detail") or ""),
        str(entry.get("message") or ""),
        str(entry.get("summary") or ""),
        json.dumps(entry.get("meta") or {}, ensure_ascii=False),
    ]
    text = "\n".join(p for p in parts if p.strip())
    return {
        "id": f"evidence:{index}",
        "source": "evidence",
        "title": event,
        "text": text,
        "at": entry.get("at"),
    }


def _notepad_document(folder: Path, name: str) -> dict[str, Any] | None:
    path = mission_notepad_dir(folder) / name
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if not text.strip():
        return None
    return {
        "id": f"notepad:{name}",
        "source": "notepad",
        "title": name,
        "text": text,
        "path": str(path),
        "mtime": mtime,
    }


def _source_fingerprint(folder: Path) -> dict[str, Any]:
    evidence = evidence_path(folder)
    sources: dict[str, Any] = {}
    if evidence.is_file():
        try:
            stat = evidence.stat()
            sources["evidence"] = {"mtime": stat.st_mtime, "size": stat.st_size}
        except OSError:
            sources["evidence"] = None
    for name in MISSION_NOTEPAD_FILES:
        path = mission_notepad_dir(folder) / name
        if path.is_file():
            try:
                stat = path.stat()
                sources[f"notepad:{name}"] = {"mtime": stat.st_mtime, "size": stat.st_size}
            except OSError:
                sources[f"notepad:{name}"] = None
    return sources


def _index_stale(folder: Path, stored: dict[str, Any] | None) -> bool:
    if not stored:
        return True
    return stored.get("fingerprint") != _source_fingerprint(folder)


def collect_documents(folder: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for i, entry in enumerate(read_evidence_tail(folder, limit=500)):
        if isinstance(entry, dict):
            docs.append(_evidence_document(entry, index=i))
    for name in MISSION_NOTEPAD_FILES:
        row = _notepad_document(folder, name)
        if row:
            docs.append(row)
    docs.extend(_trading_artifact_documents(folder))
    return docs


def _trading_wisdom_tags(folder: Path) -> list[str]:
    from agent_lab.run_meta import read_run_meta
    from agent_lab.trading_mission.trading_goal_oracle import is_trading_mission_run

    run = read_run_meta(folder)
    if not is_trading_mission_run(run):
        return []
    tags = [f"trading:session:{folder.name}"]
    mission_kind = str(run.get("mission_kind") or "").strip()
    if mission_kind:
        tags.append(f"trading:kind:{mission_kind}")
    batch_path = folder / "artifacts" / "proposal_batch.json"
    if batch_path.is_file():
        try:
            batch = json.loads(batch_path.read_text(encoding="utf-8"))
            if isinstance(batch, dict):
                mid = str(batch.get("mission_id") or "").strip()
                if mid:
                    tags.append(f"trading:mission:{mid}")
                if batch.get("ingest_ready") is False:
                    tags.append("trading:blocked")
        except (OSError, json.JSONDecodeError):
            pass
    return tags


def _trading_artifact_documents(folder: Path) -> list[dict[str, Any]]:
    tags = _trading_wisdom_tags(folder)
    if not tags:
        return []
    docs: list[dict[str, Any]] = []
    for rel in (
        "artifacts/mission_summary.md",
        "artifacts/playbook.md",
        "plan.md",
    ):
        path = folder / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        docs.append(
            {
                "id": f"trading:{rel.replace('/', ':')}",
                "source": "trading_mission",
                "title": rel,
                "text": text[:4000],
                "path": rel,
                "at": _now_iso(),
                "tags": tags,
            }
        )
    return docs


def build_wisdom_index(folder: Path, *, force: bool = False) -> dict[str, Any]:
    path = index_path(folder)
    if path.is_file() and not force:
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = None
        if isinstance(stored, dict) and not _index_stale(folder, stored):
            return stored

    documents = collect_documents(folder)
    rows: list[dict[str, Any]] = []
    for doc in documents:
        text = str(doc.get("text") or "")
        rows.append(
            {
                **doc,
                "tokens": sorted(_tokenize(text)),
            }
        )
    payload = {
        "version": 1,
        "built_at": _now_iso(),
        "session_id": folder.name,
        "document_count": len(rows),
        "fingerprint": _source_fingerprint(folder),
        "documents": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _load_index(folder: Path, *, rebuild_if_stale: bool = True) -> dict[str, Any]:
    path = index_path(folder)
    stored: dict[str, Any] | None = None
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                stored = raw
        except (OSError, json.JSONDecodeError):
            stored = None
    if rebuild_if_stale and _index_stale(folder, stored):
        return build_wisdom_index(folder, force=True)
    return stored or build_wisdom_index(folder, force=True)


def search_wisdom_index(
    folder: Path,
    query: str,
    *,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    terms = _tokenize(query)
    if not terms:
        return []
    index = _load_index(folder)
    scored: list[tuple[float, dict[str, Any]]] = []
    for doc in index.get("documents") or []:
        if not isinstance(doc, dict):
            continue
        text = str(doc.get("text") or "")
        lower = text.lower()
        score = 0.0
        for term in terms:
            if term in lower:
                score += lower.count(term)
        doc_tokens = set(doc.get("tokens") or [])
        score += len(terms & doc_tokens) * 0.5
        if score <= 0:
            continue
        hit = {
            "id": doc.get("id"),
            "source": doc.get("source"),
            "title": doc.get("title"),
            "score": round(score, 2),
            "snippet": _snippet(text, query_terms=terms),
            "at": doc.get("at"),
            "path": doc.get("path"),
            "tags": list(doc.get("tags") or []),
        }
        scored.append((score, hit))
    scored.sort(key=lambda row: row[0], reverse=True)
    return [row[1] for row in scored[: max(1, limit)]]


def _recent_session_folders(
    *,
    exclude_session: str | None = None,
    limit: int = 8,
) -> list[Path]:
    from agent_lab.session import SESSIONS_DIR

    if not SESSIONS_DIR.is_dir():
        return []
    rows: list[tuple[float, Path]] = []
    for child in SESSIONS_DIR.iterdir():
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if exclude_session and child.name == exclude_session:
            continue
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        rows.append((mtime, child))
    rows.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in rows[: max(1, limit)]]


def search_wisdom_cross_sessions(
    query: str,
    *,
    exclude_session: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    if not wisdom_cross_session_enabled():
        return []
    terms = _tokenize(query)
    if not terms:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for folder in _recent_session_folders(exclude_session=exclude_session):
        for hit in search_wisdom_index(folder, query, limit=limit):
            row = dict(hit)
            row["session_id"] = folder.name
            score = float(row.get("score") or 0)
            scored.append((score, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in scored[: max(1, limit)]]


def public_wisdom_index_status(folder: Path, *, run: dict[str, Any] | None = None) -> dict[str, Any]:
    run_meta = run
    if run_meta is None:
        from agent_lab.run_meta import read_run_meta

        run_meta = read_run_meta(folder)
    if not wisdom_index_enabled(run_meta):
        return {
            "enabled": False,
            "document_count": 0,
            "built_at": None,
            "cross_session": wisdom_cross_session_enabled(),
        }
    index = _load_index(folder, rebuild_if_stale=True)
    return {
        "enabled": True,
        "document_count": int(index.get("document_count") or 0),
        "built_at": index.get("built_at"),
        "path": str(index_path(folder)),
        "cross_session": wisdom_cross_session_enabled(),
        "auto_enabled": (os.getenv("AGENT_LAB_WISDOM_INDEX") or "").strip().lower() not in ("1", "true", "yes", "on"),
    }


def agent_learnings_enabled() -> bool:
    """``AGENT_LAB_AGENT_LEARNINGS`` — ``[LEARNED:]`` 마커 수확 (기본 on)."""
    raw = (os.getenv("AGENT_LAB_AGENT_LEARNINGS") or "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def harvest_agent_learnings(folder: Path, messages: list[Any]) -> int:
    """P5 stigmergy 쓰기 경로 — 이번 턴 ``[LEARNED:]`` 마커를 learnings.md에 dedupe 추가.

    루프 폐쇄: 에이전트 기록 → notepad → wisdom index → R1 주입이 미래 토론에 공급.
    room.py가 mission_loop를 직접 import하지 않도록 여기서 배선한다 (레이어링).
    """
    if not agent_learnings_enabled():
        return 0
    from agent_lab.agent_envelope import extract_learned_notes

    last_user = -1
    for i, m in enumerate(messages):
        if getattr(m, "role", None) == "user":
            last_user = i
    turn = messages[last_user + 1 :] if last_user >= 0 else list(messages)
    entries: list[str] = []
    for m in turn:
        if getattr(m, "role", None) != "agent" or not getattr(m, "agent", None):
            continue
        for note in extract_learned_notes(getattr(m, "content", "") or ""):
            entry = f"[{m.agent}] {note[:300]}"
            if entry not in entries:
                entries.append(entry)
    if not entries:
        return 0
    from agent_lab.mission_loop import append_wisdom_note

    existing = ""
    notepad = mission_notepad_dir(folder) / "learnings.md"
    if notepad.is_file():
        existing = notepad.read_text(encoding="utf-8")
    added = 0
    for entry in entries:
        if entry in existing:
            continue
        append_wisdom_note(
            folder,
            line=entry,
            filename="learnings.md",
            provenance="agent-learned",
            auto_provenance=False,
        )
        added += 1
    return added


def public_wisdom_search_payload(
    folder: Path,
    *,
    query: str,
    limit: int = _DEFAULT_LIMIT,
    cross_session: bool = False,
) -> dict[str, Any]:
    from agent_lab.run_meta import read_run_meta

    run = read_run_meta(folder)
    if not wisdom_index_enabled(run):
        return {
            "enabled": False,
            "query": query,
            "hits": [],
            "hit_count": 0,
            "cross_session_hits": [],
        }
    hits = search_wisdom_index(folder, query, limit=limit)
    cross_hits: list[dict[str, Any]] = []
    if cross_session and wisdom_cross_session_enabled():
        cross_hits = search_wisdom_cross_sessions(
            query,
            exclude_session=folder.name,
            limit=limit,
        )
    status = public_wisdom_index_status(folder, run=run)
    return {
        "enabled": True,
        "query": query,
        "hits": hits,
        "hit_count": len(hits),
        "cross_session_hits": cross_hits,
        "cross_session_hit_count": len(cross_hits),
        "index": status,
    }
