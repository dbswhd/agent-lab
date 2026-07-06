"""Session start: workspace preset + workflow template binding."""

from __future__ import annotations

from agent_lab.run.state import RunStateLike
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_lab.session.guidance import (
    CONTENT_ROUND_GUIDANCE,
    LAYOUT_FROZEN_GUIDANCE,
    RECIPE_GOLDEN_GUIDANCE,
    SINGLE_EXECUTOR_GUIDANCE,
    VERIFICATION_ARTIFACT_GUIDANCE,
    apply_discuss_workspace,
)
from agent_lab.agent.thread_catalog import list_agent_threads
from agent_lab.workspace.roots import (
    lecture_script_root,
    pipeline_root,
    user_agent_lab_root,
    workspace_label,
)

DEFAULT_WORKSPACE_ID = "agent-lab"
DEFAULT_TEMPLATE_ID = "general"
CUSTOM_WORKSPACE_ID = "custom"

SESSION_TEMPLATE_IDS = frozenset(
    {"general", "book-layout", "book-content", "trading-mission", "trading-thin", "trading-offline"}
)
TRADING_TEMPLATE_IDS = frozenset({"trading-mission", "trading-thin", "trading-offline"})
WORKSPACE_PRESET_IDS = frozenset({"agent-lab", "quant-pipeline", "lecture-book", CUSTOM_WORKSPACE_ID})


def _preset(
    preset_id: str,
    label: str,
    path: Path | None,
    perm_key: str,
) -> dict[str, Any]:
    available = path is not None and path.is_dir()
    return {
        "id": preset_id,
        "label": label,
        "path": str(path.resolve()) if available and path else None,
        "available": available,
        "perm_key": perm_key,
    }


def list_workspace_presets() -> list[dict[str, Any]]:
    """Workspace roots selectable at session start."""
    agent_lab = user_agent_lab_root()
    pipe = pipeline_root()
    lecture = lecture_script_root()
    presets = [
        _preset("agent-lab", "agent-lab", agent_lab, "local_agent_lab"),
        _preset("quant-pipeline", "quant-pipeline", pipe, "local_pipeline"),
        _preset("lecture-book", "교재 book", lecture, "local_lecture_script"),
    ]
    return [p for p in presets if p["available"]]


def resolve_workspace_preset(preset_id: str | None) -> dict[str, Any] | None:
    pid = (preset_id or DEFAULT_WORKSPACE_ID).strip().lower()
    if pid == CUSTOM_WORKSPACE_ID:
        return None
    presets = list_workspace_presets()
    for preset in presets:
        if preset["id"] == pid:
            return preset
    if pid != DEFAULT_WORKSPACE_ID:
        return None
    for preset in presets:
        if preset["id"] == DEFAULT_WORKSPACE_ID:
            return preset
    return presets[0] if presets else None


def resolve_custom_workspace(path: str | None) -> dict[str, Any] | None:
    raw = (path or "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        return None
    return {
        "id": CUSTOM_WORKSPACE_ID,
        "label": workspace_label(root),
        "path": str(root),
        "available": True,
        "perm_key": "local_custom",
    }


def resolve_workspace_selection(
    workspace_id: str | None,
    workspace_path: str | None = None,
) -> dict[str, Any] | None:
    """Resolve preset or user-picked folder for session start."""
    wid = (workspace_id or DEFAULT_WORKSPACE_ID).strip().lower()
    if wid == CUSTOM_WORKSPACE_ID or (workspace_path or "").strip():
        custom = resolve_custom_workspace(workspace_path)
        if custom is not None:
            return custom
    if wid == CUSTOM_WORKSPACE_ID:
        raw = (workspace_path or "").strip()
        if not raw:
            raise ValueError("custom workspace path required")
        raise ValueError(f"custom workspace path not found: {raw}")
    return resolve_workspace_preset(workspace_id)


def _all_session_template_defs() -> list[dict[str, Any]]:
    return [
        {
            "id": "general",
            "label": "일반",
            "description": "코드·기획·리서치 — 기본 room 가이던스",
            "default_phase": None,
            "routing_hints": {},
        },
        {
            "id": "book-layout",
            "label": "교재 · 레이아웃",
            "description": "PDF 빌드·페이지 break·RECIPE·golden baseline",
            "default_phase": "layout",
        },
        {
            "id": "book-content",
            "label": "교재 · 내용",
            "description": "md/JSON/OCR/풀이 — 레이아웃 변경 금지",
            "default_phase": "content",
        },
        {
            "id": "trading-mission",
            "label": "Trading Mission",
            "description": "장전/이벤트 — snapshot → discuss → proposal batch + playbook",
            "default_phase": "trading",
            "routing_hints": {"response_contract_bias": "evidence_first"},
        },
        {
            "id": "trading-thin",
            "label": "Trading · 장중 thin",
            "description": "장중 read-only — playbook/batch/console pending만 (Room 금지)",
            "default_phase": "trading_thin",
        },
        {
            "id": "trading-offline",
            "label": "Trading · 주간 offline",
            "description": "주 1회 wire-up — cards sync, WireUpDecision, runtime playbook (no ingest)",
            "default_phase": "trading_offline",
        },
    ]


def list_session_templates() -> list[dict[str, Any]]:
    """Workflow templates for session UI (trading templates require quant-pipeline extension)."""
    templates = _all_session_template_defs()
    from agent_lab.extensions.quant_trading import quant_pipeline_available

    if quant_pipeline_available():
        return templates
    return [t for t in templates if t["id"] not in TRADING_TEMPLATE_IDS]


def resolve_session_template(template_id: str | None) -> dict[str, Any]:
    tid = (template_id or DEFAULT_TEMPLATE_ID).strip().lower()
    for tpl in list_session_templates():
        if tpl["id"] == tid:
            return tpl
    return list_session_templates()[0]


def template_routing_hints(template_id: str | None) -> dict[str, Any]:
    """Optional session-template routing biases for topic_router."""
    from agent_lab.session.routing_hints import template_routing_hints as _lookup

    return _lookup(template_id)


def template_guidance_block(template_id: str | None) -> str:
    tpl = resolve_session_template(template_id)
    tid = tpl["id"]
    if tid == "book-layout":
        parts = [
            "[Session template — book layout]",
            "Focus: KaTeX/Puppeteer pipeline, page breaks, RECIPE.md, golden/ baselines.",
            "Use verification artifacts (PDF page count + break-report.json) before PASS.",
            SINGLE_EXECUTOR_GUIDANCE.strip(),
            VERIFICATION_ARTIFACT_GUIDANCE.strip(),
            RECIPE_GOLDEN_GUIDANCE.strip(),
        ]
        return "\n".join(parts)
    if tid == "book-content":
        parts = [
            "[Session template — book content]",
            "Focus: md/JSON content, OCR, blank solutions — not layout/CSS/break tuning.",
            LAYOUT_FROZEN_GUIDANCE.strip(),
            CONTENT_ROUND_GUIDANCE.strip(),
            SINGLE_EXECUTOR_GUIDANCE.strip(),
        ]
        return "\n".join(parts)
    if tid == "trading-mission":
        from agent_lab.session.guidance import TRADING_MISSION_GUIDANCE

        return TRADING_MISSION_GUIDANCE.strip()
    if tid == "trading-thin":
        from agent_lab.session.guidance import THIN_RUNTIME_GUIDANCE

        return THIN_RUNTIME_GUIDANCE.strip()
    if tid == "trading-offline":
        from agent_lab.session.guidance import OFFLINE_LANE_GUIDANCE

        return OFFLINE_LANE_GUIDANCE.strip()
    return ""


def workspace_binding_from_preset(preset: dict[str, Any]) -> dict[str, Any]:
    path = preset.get("path")
    if not path:
        raise ValueError(f"workspace preset unavailable: {preset.get('id')}")
    root = Path(str(path)).resolve()
    return {
        "path": str(root),
        "label": workspace_label(root),
        "preset": preset["id"],
    }


def merge_setup_permissions(
    permissions: dict[str, Any] | None,
    workspace_id: str | None,
    workspace_path: str | None = None,
) -> dict[str, Any]:
    """Enable the selected workspace root for all agent backends."""
    preset = resolve_workspace_selection(workspace_id, workspace_path)
    if not preset or not preset.get("path"):
        return dict(permissions or {})
    perm_key = str(preset["perm_key"])
    binding = workspace_binding_from_preset(preset)
    out: dict[str, Any] = dict(permissions or {})
    for agent in ("cursor", "claude", "codex"):
        block = dict(out.get(agent) or {})
        block[perm_key] = True
        out[agent] = block
    return apply_discuss_workspace(out, binding)


def build_setup_run_meta(
    *,
    workspace_id: str | None,
    session_template: str | None,
    workspace_path: str | None = None,
    agent_thread_bindings: dict[str, str] | None = None,
) -> dict[str, Any]:
    preset = resolve_workspace_selection(workspace_id, workspace_path)
    tpl = resolve_session_template(session_template)
    if not preset or not preset.get("path"):
        raise ValueError("no workspace preset available")
    binding = workspace_binding_from_preset(preset)
    meta: dict[str, Any] = {
        "workspace_preset": preset["id"],
        "workspace_binding": binding,
        "session_template": tpl["id"],
        "team_lead": "cursor",
        "tasks": [],
    }
    phase = tpl.get("default_phase")
    if phase:
        meta["session_phase"] = phase
    if tpl["id"] == "book-content":
        meta["layout_frozen"] = True
        meta["layout_frozen_at"] = datetime.now(timezone.utc).isoformat()
    if tpl["id"] == "trading-mission":
        meta["mission_kind"] = "trading_premarket"
        meta["response_contract"] = {"preset": "evidence_first"}
        meta["turn_profile"] = "analyze"
        from agent_lab.trading_mission.trading_goal_oracle import DEFAULT_TRADING_GOAL_TEXT

        meta["session_goal"] = {"text": DEFAULT_TRADING_GOAL_TEXT, "preset": "trading_mission"}
    if tpl["id"] == "trading-offline":
        meta["mission_kind"] = "trading_weekly"
        meta["response_contract"] = {"preset": "evidence_first"}
        meta["turn_profile"] = "analyze"
    if agent_thread_bindings:
        meta["agent_thread_bindings"] = agent_thread_bindings
    return meta


def seed_session_setup(
    folder: Path,
    *,
    workspace_id: str | None,
    session_template: str | None,
    workspace_path: str | None = None,
    topic: str = "",
    agent_thread_bindings: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Write initial run.json + meta.json fields for a new session folder."""
    setup = build_setup_run_meta(
        workspace_id=workspace_id,
        session_template=session_template,
        workspace_path=workspace_path,
        agent_thread_bindings=agent_thread_bindings,
    )
    now = datetime.now(timezone.utc).isoformat()
    run_meta: RunStateLike = {
        "workflow_id": "room.parallel",
        "run_schema_version": 1,
        "topic": topic,
        "created_at": now,
        **setup,
    }
    from agent_lab.run.meta import write_run_meta

    write_run_meta(folder, run_meta)
    meta_path = folder / "meta.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}
    meta.update(
        {
            "topic": topic or meta.get("topic", ""),
            "created_at": meta.get("created_at") or now,
            "workflow": "room.parallel",
            "workspace_preset": setup["workspace_preset"],
            "session_template": setup["session_template"],
        }
    )
    if setup.get("session_phase"):
        meta["session_phase"] = setup["session_phase"]
    if setup.get("layout_frozen"):
        meta["layout_frozen"] = True
    binding = setup.get("workspace_binding")
    if isinstance(binding, dict) and binding.get("path"):
        meta["workspace_label"] = binding.get("label") or binding["path"]
    meta_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return run_meta


def session_setup_options() -> dict[str, Any]:
    workspaces = list_workspace_presets()
    default_ws = DEFAULT_WORKSPACE_ID
    if not any(w["id"] == default_ws for w in workspaces) and workspaces:
        default_ws = str(workspaces[0]["id"])
    trading_preset: dict[str, Any] | None = None
    trading_thin_preset: dict[str, Any] | None = None
    if any(w["id"] == "quant-pipeline" for w in workspaces):
        try:
            from agent_lab.trading_mission.topic import render_premarket_topic
            from agent_lab.trading_mission.trading_goal_oracle import (
                DEFAULT_TRADING_GOAL_TEXT,
            )

            trading_preset = {
                "workspace_id": "quant-pipeline",
                "session_template": "trading-mission",
                "turn_profile": "analyze",
                "topic": render_premarket_topic(),
                "session_goal": DEFAULT_TRADING_GOAL_TEXT,
            }
            trading_thin_preset = {
                "workspace_id": "quant-pipeline",
                "session_template": "trading-thin",
                "turn_profile": "analyze",
                "topic": "[Trading · 장중 thin] playbook + pending batch + console approval only.",
                "session_goal": "Read intraday status via MCP; no Room/backtest/live execute.",
            }
        except (ImportError, FileNotFoundError, OSError):
            trading_preset = {
                "workspace_id": "quant-pipeline",
                "session_template": "trading-mission",
                "turn_profile": "analyze",
            }
            trading_thin_preset = {
                "workspace_id": "quant-pipeline",
                "session_template": "trading-thin",
                "turn_profile": "analyze",
            }
    return {
        "workspaces": workspaces,
        "agent_threads": list_agent_threads(),
        "session_templates": list_session_templates(),
        "trading_mission_preset": trading_preset,
        "trading_thin_preset": trading_thin_preset,
        "defaults": {
            "workspace_id": default_ws,
            "session_template": DEFAULT_TEMPLATE_ID,
        },
    }
