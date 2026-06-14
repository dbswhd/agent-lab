"""Mission templates — sessions/_templates/ registry and fast-path plan approve."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.plan_pending import plan_content_hash
from agent_lab.plan_workflow import (
    approve_plan_bypass,
    get_plan_workflow,
    init_plan_workflow_on_plan_send,
)
from agent_lab.run_meta import read_run_meta
from agent_lab.session import SESSIONS_DIR

TEMPLATES_DIR_NAME = "_templates"


def templates_root(sessions_dir: Path | None = None) -> Path:
    root = sessions_dir or SESSIONS_DIR
    return root / TEMPLATES_DIR_NAME


def list_mission_templates(sessions_dir: Path | None = None) -> list[dict[str, Any]]:
    root = templates_root(sessions_dir)
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        meta = read_template_meta(child)
        plan_path = child / "plan.md"
        plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
        live_hash = plan_content_hash(plan_md) if plan_md.strip() else ""
        meta_hash = str(meta.get("hash") or "")
        rows.append(
            {
                "id": child.name,
                "path": str(child),
                "meta": meta,
                "plan_hash": live_hash,
                "hash_match": bool(meta_hash and meta_hash == live_hash),
                "topic": (child / "topic.txt").read_text(encoding="utf-8").strip()
                if (child / "topic.txt").is_file()
                else "",
            }
        )
    return rows


def read_template_meta(template_dir: Path) -> dict[str, Any]:
    path = template_dir / "template_meta.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def template_dir_for(template_id: str, sessions_dir: Path | None = None) -> Path:
    safe = template_id.strip().replace("/", "").replace("\\", "")
    if not safe:
        raise ValueError("template_id required")
    path = templates_root(sessions_dir) / safe
    if not path.is_dir():
        raise FileNotFoundError(f"template not found: {safe}")
    return path


def get_template_detail(template_id: str, sessions_dir: Path | None = None) -> dict[str, Any]:
    tdir = template_dir_for(template_id, sessions_dir)
    meta = read_template_meta(tdir)
    plan_path = tdir / "plan.md"
    plan_md = plan_path.read_text(encoding="utf-8") if plan_path.is_file() else ""
    live_hash = plan_content_hash(plan_md) if plan_md.strip() else ""
    meta_hash = str(meta.get("hash") or "")
    return {
        "id": tdir.name,
        "meta": meta,
        "plan_md": plan_md,
        "plan_hash": live_hash,
        "hash_match": bool(meta_hash and meta_hash == live_hash),
        "topic": (tdir / "topic.txt").read_text(encoding="utf-8").strip() if (tdir / "topic.txt").is_file() else "",
    }


def copy_template_into_session(
    session_folder: Path,
    template_id: str,
    *,
    sessions_dir: Path | None = None,
) -> dict[str, Any]:
    tdir = template_dir_for(template_id, sessions_dir)
    meta = read_template_meta(tdir)
    plan_src = tdir / "plan.md"
    topic_src = tdir / "topic.txt"
    if not plan_src.is_file():
        raise ValueError("template plan.md missing")
    session_folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(plan_src, session_folder / "plan.md")
    if topic_src.is_file():
        shutil.copy2(topic_src, session_folder / "topic.txt")
    plan_md = (session_folder / "plan.md").read_text(encoding="utf-8")
    live_hash = plan_content_hash(plan_md)
    return {
        "template_id": template_id,
        "meta": meta,
        "plan_hash": live_hash,
        "hash_match": str(meta.get("hash") or "") == live_hash,
    }


def init_plan_workflow_from_template(
    session_folder: Path,
    template_id: str,
    *,
    sessions_dir: Path | None = None,
) -> dict[str, Any]:
    """Gate 2-B: copy template; hash match → APPROVED fast-path, else full FSM."""
    copied = copy_template_into_session(session_folder, template_id, sessions_dir=sessions_dir)
    plan_md = (session_folder / "plan.md").read_text(encoding="utf-8")
    if copied["hash_match"]:
        return approve_plan_bypass(
            session_folder,
            plan_md=plan_md,
            approved_by=f"template:{template_id}",
        )
    init_plan_workflow_on_plan_send(session_folder)
    return {
        "fast_path": False,
        "reason": "hash_mismatch",
        "template_id": template_id,
        "plan_hash": copied["plan_hash"],
        "expected_hash": copied["meta"].get("hash"),
        "plan_workflow": get_plan_workflow(read_run_meta(session_folder)),
    }


def sign_template_pre_approval(
    template_dir: Path,
    *,
    approved_by: str = "human",
) -> dict[str, Any]:
    """Human one-time sign-off when registering a template (Gate 5-A for templates)."""
    meta = read_template_meta(template_dir)
    plan_path = template_dir / "plan.md"
    if not plan_path.is_file():
        raise ValueError("plan.md missing")
    plan_md = plan_path.read_text(encoding="utf-8")
    meta["hash"] = plan_content_hash(plan_md)
    meta["pre_approved_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    meta["pre_approved_by"] = approved_by
    path = template_dir / "template_meta.json"
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return meta
