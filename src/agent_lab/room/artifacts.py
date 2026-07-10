"""Session artifacts[] — agent outputs as first-class run.json citizens (Phase G1)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Literal

from agent_lab.time_utils import utc_now_iso as _now
from agent_lab.run.state import RunStateLike

RUN_ARTIFACTS_KEY = "artifacts"
ArtifactKind = Literal["log", "diff", "table", "file_ref", "delegate"]
_AGENT_IDS = frozenset({"cursor", "codex", "claude"})
_ARTIFACT_BODY_RE = re.compile(
    r"```(?:artifact|output)\s*\n([\s\S]*?)```",
    re.I,
)



def _new_artifact_id() -> str:
    return f"art-{uuid.uuid4().hex[:10]}"


def normalize_artifact(raw: dict[str, Any]) -> dict[str, Any]:
    aid = str(raw.get("id") or _new_artifact_id()).strip() or _new_artifact_id()
    kind = str(raw.get("kind") or "log").strip().lower()
    if kind not in ("log", "diff", "table", "file_ref", "delegate"):
        kind = "log"
    out: dict[str, Any] = {
        "id": aid,
        "producer": str(raw.get("producer") or "").strip().lower()[:40],
        "kind": kind,
        "summary": str(raw.get("summary") or "").strip()[:500],
        "ts": str(raw.get("ts") or _now()),
    }
    if raw.get("path"):
        out["path"] = str(raw["path"]).strip()[:500]
    if raw.get("turn") is not None:
        try:
            out["turn"] = int(raw["turn"])
        except (TypeError, ValueError):
            pass
    refs = raw.get("refs") or []
    if isinstance(refs, list) and refs:
        out["refs"] = [str(r).strip()[:80] for r in refs if str(r).strip()][:12]
    if raw.get("parallel_round") is not None:
        try:
            out["parallel_round"] = int(raw["parallel_round"])
        except (TypeError, ValueError):
            pass
    return out


def list_artifacts(run_meta: RunStateLike | None) -> list[dict[str, Any]]:
    if not run_meta:
        return []
    raw = run_meta.get(RUN_ARTIFACTS_KEY)
    if not isinstance(raw, list):
        return []
    return [normalize_artifact(a) for a in raw if isinstance(a, dict)]


def write_artifacts(run_meta: RunStateLike, rows: list[dict[str, Any]]) -> None:
    from agent_lab.run.meta import stamp_run_meta

    stamp_run_meta(
        run_meta,
        **{RUN_ARTIFACTS_KEY: [normalize_artifact(a) for a in rows]},
    )


def _artifact_dir(session_folder: Path | None) -> Path | None:
    if session_folder and session_folder.is_dir():
        d = session_folder / "artifacts"
        d.mkdir(exist_ok=True)
        return d
    return None


def append_artifact(
    run_meta: RunStateLike,
    *,
    producer: str,
    kind: ArtifactKind,
    summary: str,
    body: str = "",
    session_folder: Path | None = None,
    human_turn: int | None = None,
    parallel_round: int | None = None,
    refs: list[str] | None = None,
) -> dict[str, Any]:
    producer_l = str(producer or "").strip().lower()
    text = (body or summary or "").strip()
    if producer_l not in _AGENT_IDS or not text:
        raise ValueError("invalid artifact producer or empty body")
    rows = list_artifacts(run_meta)
    fp: str | None = None
    art_dir = _artifact_dir(session_folder)
    if art_dir is not None and session_folder is not None and len(text) > 80:
        fname = f"{_new_artifact_id()}.txt"
        path = art_dir / fname
        path.write_text(text[:120_000], encoding="utf-8")
        session_root = session_folder.resolve()
        fp = str(path.resolve().relative_to(session_root))
    row = normalize_artifact(
        {
            "producer": producer_l,
            "kind": kind,
            "summary": (summary or text)[:500],
            "path": fp,
            "turn": human_turn,
            "parallel_round": parallel_round,
            "refs": refs or [],
        }
    )
    rows.append(row)
    write_artifacts(run_meta, rows)
    return row


def _extract_body(content: str) -> tuple[str, str | None]:
    m = _ARTIFACT_BODY_RE.search(content or "")
    if m:
        return content, m.group(1).strip()[:8000]
    body = (content or "").strip()
    if len(body) < 120:
        return body, None
    first = body.splitlines()[0].strip()[:200]
    return first, body[:8000]


def harvest_artifacts_from_turn(
    run_meta: RunStateLike,
    messages: list[Any],
    *,
    human_turn: int,
    session_folder: Path | None = None,
    turn_profile: str = "",
    mode: str = "discuss",
) -> list[dict[str, Any]]:
    """Harvest agent outputs as artifacts (plan / specialist / research turns)."""
    profile = (turn_profile or str(run_meta.get("turn_profile") or "")).strip().lower()
    research = profile == "specialist" or bool(run_meta.get("research_mode"))
    if not research and mode != "plan":
        return []

    last_user = -1
    for i, m in enumerate(messages):
        if getattr(m, "role", None) == "user":
            last_user = i
    turn = messages[last_user + 1 :] if last_user >= 0 else messages
    created: list[dict[str, Any]] = []
    for m in turn:
        if getattr(m, "role", None) != "agent":
            continue
        agent = str(getattr(m, "agent", "") or "").strip().lower()
        if agent not in _AGENT_IDS:
            continue
        pr = getattr(m, "parallel_round", None) or 1
        if research and profile == "specialist" and pr == 1 and agent == "cursor":
            continue
        content = getattr(m, "content", "") or ""
        summary, body = _extract_body(content)
        if not body and len(summary) < 120:
            continue
        try:
            row = append_artifact(
                run_meta,
                producer=agent,
                kind="log",
                summary=summary,
                body=body or summary,
                session_folder=session_folder,
                human_turn=human_turn,
                parallel_round=pr,
            )
            created.append(row)
        except ValueError:
            continue
    return created


def recent_artifacts_for_agent(
    run_meta: RunStateLike | None,
    agent: str,
    *,
    turn_profile: str = "",
    parallel_round: int = 1,
) -> list[dict[str, Any]]:
    profile = (turn_profile or str((run_meta or {}).get("turn_profile") or "")).lower()
    rows = list_artifacts(run_meta)
    research = profile == "specialist" or bool((run_meta or {}).get("research_mode"))
    if research and agent == "cursor" and parallel_round >= 2:
        return [a for a in rows if a.get("producer") in ("codex", "claude")][-6:]
    return rows[-8:]


def _session_folder(run_meta: RunStateLike | None) -> Path | None:
    raw = (run_meta or {}).get("_session_folder")
    if not raw:
        return None
    try:
        folder = Path(str(raw)).expanduser().resolve()
    except OSError:
        return None
    return folder if folder.is_dir() else None


def _read_artifact_body(
    run_meta: RunStateLike | None,
    path_raw: Any,
    *,
    cap_chars: int,
) -> str:
    if not path_raw:
        return ""
    try:
        path = Path(str(path_raw)).expanduser()
    except (TypeError, ValueError):
        return ""
    if not path.is_absolute():
        folder = _session_folder(run_meta)
        if folder is None:
            return ""
        path = folder / path
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    text = text.strip()
    if len(text) > cap_chars:
        return text[: cap_chars - 1] + "…"
    return text


def build_artifacts_block(
    run_meta: RunStateLike | None,
    agent: str,
    *,
    parallel_round: int = 1,
    artifact_only: bool = False,
    body_cap_chars: int = 2000,
) -> str:
    rows = recent_artifacts_for_agent(run_meta, agent, parallel_round=parallel_round)
    if not rows:
        return ""
    if artifact_only:
        lines = [
            "[artifact-only R2 — 아래 artifacts만 근거로 패치 제안]",
            "",
        ]
    else:
        lines = ["[최근 artifacts — 동료 산출물]", ""]
    for a in rows:
        prod = a.get("producer") or "?"
        lines.append(f"- {prod} ({a.get('kind')}): {(a.get('summary') or '')[:160]}")
        if a.get("path"):
            lines.append(f"  path: {a['path']}")
            body = (
                _read_artifact_body(
                    run_meta,
                    a.get("path"),
                    cap_chars=body_cap_chars,
                )
                if artifact_only
                else ""
            )
            if body:
                lines.append("  body:")
                for line in body.splitlines():
                    lines.append(f"    {line}")
    lines.append("")
    if artifact_only:
        lines.append("Cursor R2: full chat 없음. artifacts와 이번 Human 질문만 근거로 패치 제안.")
    else:
        lines.append("Cursor R2: artifacts만 근거로 패치 제안 가능.")
    return "\n".join(lines)


def artifacts_public_payload(run_meta: RunStateLike | None) -> dict[str, Any]:
    rows = list_artifacts(run_meta)
    return {
        "artifacts": rows[-30:],
        "artifact_count": len(rows),
    }
