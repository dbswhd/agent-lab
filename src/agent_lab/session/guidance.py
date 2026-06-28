"""Book-session guidance: layout freeze, human gates, verification artifacts, golden paths."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Protocol

from agent_lab.workspace.roots import (
    is_bundled_app_runtime,
    lecture_script_root,
    resolve_execute_workspace,
    workspace_label,
)

# Desktop book golden baseline convention (RECIPE § golden)
GOLDEN_DIR = "golden"
GOLDEN_V1_SUFFIX = "v1"
GOLDEN_V2_SUFFIX = "v2"
GOLDEN_BASELINE_FILES = (
    "break-report.json",
    "공수1_기말학습자료.pdf",
)

_LAYOUT_FREEZE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"딱\s*좋", re.I),
    re.compile(r"layout\s*freeze|freeze\s*layout", re.I),
    re.compile(r"\bfreeze\b", re.I),
    re.compile(r"추가\s*수정\s*금지", re.I),
    re.compile(r"페이지\s*새\s*시작.*(더\s*하지|안\s*함|금지)", re.I),
    re.compile(r"break.*(더\s*하지|금지|freeze)", re.I),
    re.compile(r"css.*(더\s*하지|금지|freeze)", re.I),
]

_CONTENT_PHASE_HINTS = (
    "ocr",
    "빈 풀이",
    "exercise-sol",
    "내용",
    "content",
    "json",
    "md 수정",
)

_LAYOUT_PATH_HINTS = (
    "build.mjs",
    "lecture.css",
    "break-report",
    "page break",
    "레이아웃",
    "layout",
    "golden",
    "recipe",
)

SESSION_META_KEYS = (
    "layout_frozen",
    "layout_frozen_at",
    "session_phase",
    "workspace_preset",
    "workspace_binding",
    "session_template",
    "team_lead",
    "turn_leads",
    "tasks",
    "mailbox",
    "objections",
    "agent_capabilities",
    "agent_capabilities_custom",
    "artifacts",
    "research_mode",
    "last_verification_artifacts",
    "last_delegate",
    "session_goal",
    "goal_loop",
    "verified_loop",
    "plan_workflow",
    "verified_plan_sync",
    "mission_loop",
    "mission_board",
    "turn_budget",
    "hook_runs",
    "agent_hooks_manifest",
)

LAYOUT_FROZEN_GUIDANCE = """\
[LAYOUT_FROZEN — content-only mode]
- Human confirmed the current PDF layout/break/CSS baseline. **Do not** change `build.mjs`, `lecture.css`, page-break logic, or add new page-start rules.
- Allowed: md/JSON content fixes, OCR, blank-solution fills, RECIPE/plan docs, PDF spot-check rebuild only.
- If verification is needed, cite **PDF page count** + **`break-report.json`** summary/hash — never claim PASS without both.
"""

CONTENT_ROUND_GUIDANCE = """\
[Content round — separate from layout]
- Session phase is **content**: fix md/JSON/OCR/blank solutions only; layout/break/CSS are frozen.
- Rebuild PDF for spot-check after content edits; compare page count + break-report to baseline in `book/golden/`.
- Do not reopen layout debates unless Human explicitly unfreezes.
"""

SINGLE_EXECUTOR_GUIDANCE = """\
[SINGLE_EXECUTOR — discuss vs execute]
- **Discuss (this room turn):** Codex + Claude + Kimi Work = read-only review, checklists, `[PROPOSED:]` — **no file edits** and do not claim you edited files.
- **File/build edits:** Cursor only, via plan execute (thin execute) or explicit Human GO to Cursor.
- Codex: verify with read/grep/shell read-only; propose patches as text, not writes.
- Do not announce "discuss mode" in prose — constraints already state policy.
"""

VERIFICATION_ARTIFACT_GUIDANCE = """\
[Verification artifacts — mandatory before PASS]
- Do **not** write `VERIFICATION: PASS`, `PASS`, or endorse verification claims without:
  1. **PDF page count** (from `pdfinfo`, build log, or `break-report.json` `baseline.pdfPageCount`)
  2. **`break-report.json`** reference (path + `appliedBreaks` count or `generatedAt` / hash snippet)
- Example: `VERIFICATION: PASS — PDF 26p (pdfinfo), break-report.json appliedBreaks=15, generatedAt=2026-05-31T04:49Z`
- If you cannot read artifacts on disk, say FAIL or pending — do not guess page counts from chat.
"""

RECIPE_GOLDEN_GUIDANCE = """\
[RECIPE golden path convention]
- Baselines live under Desktop `book/golden/` with **v1/v2** naming:
  - v1: pre-cover golden (e.g. 26p `print-current-v1`, `break-report-v1.json`)
  - v2: post-cover baseline (e.g. 33p `print-v2`, `break-report-v2.json`)
- `RECIPE.md` at book root documents INPUT → build → verify → golden/freeze; plan.md keeps decisions + links only.
- Never overwrite v1 when promoting v2 — copy to `golden/` before full rebuild.
"""

TRADING_MISSION_GUIDANCE = """\
[Trading Mission — quant-pipeline preset]
- Read-only: `artifacts/market_snapshot.json`, PASS cards, overlay signals. No KIS orders, no LIVE arm.
- If `freshness.blocking` or `kill_switch`: agree `ingest_ready: false`, proposals=[], explain in `blocking_reason`.
- Each proposal needs `backtest_ref` or `overlay_signal_ref`; FAIL verdict refs must not become proposals.
- Scribe must include `## 합의` with: ingest_ready, blocking_reason, active_strategies, discuss_rounds_used.
- Optional draft: `artifacts/proposals_draft.json` (array of proposal objects) for export.
- Playbook: `artifacts/playbook.md` with 「오늘 장중 행동」section for thin runtime agent.
- Max proposals per mission: see topic (default 5). No infinite debate — 2 rounds cap.
"""

THIN_RUNTIME_GUIDANCE = """\
[Trading Mission — thin intraday runtime]
- **Read-only MCP**: `get_intraday_status`, `get_playbook`, `get_pending_batch`, `list_pending_proposals` (quant-trading).
- Use playbook + pending batch + control plane queue; **no new Room**, no backtest, no live execute.
- Allowed: human approve via console (`:8765` / alternate port), small thesis edits, delta ingest via quant-trading MCP.
- Forbidden: `run_backtest_refresh(dry_run=False)`, full 3-agent discuss, `AGENT_LAB_ALLOW_BACKTEST_RUN`, LIVE arm.
- Set `AGENT_LAB_SESSION_FOLDER` to today's premarket session (or rely on latest-session auto-resolve).
- Env: `QUANT_PIPELINE_ROOT`, `AGENTIC_TRADING_DB`, optional `AGENTIC_APPLY_PROPOSAL_CRITIC=1`.
"""

OFFLINE_LANE_GUIDANCE = """\
[Trading Mission — weekly offline lane]
- **No proposal ingest** — sync cards, emit `WireUpDecision`, push `data/agentic/wireup_decision.json` + playbook.
- Read PASS/FAIL cards via `list_wireup_candidates` / `get_strategy_verdict`; no full JSON, no notebooks.
- `active_refs` = overlay-eligible PASS strategies; `blocked_refs` = FAIL/ineligible (never propose).
- Scribe: `## 합의` with wireup_ready, active_strategies, ingest_ready: false.
- Artifacts: `artifacts/wireup_decision.json`, `artifacts/playbook.md` (주간 wire-up + 장중 행동).
- Optional Room: strategy review only (1–2 rounds); do not create proposal_batch.
"""


class _MsgLike(Protocol):
    role: str
    content: str


def _book_path_hints(topic: str, plan_md: str) -> list[str]:
    text = f"{topic}\n{plan_md}"
    hints: list[str] = []
    for name in (
        "build.mjs",
        "lecture.css",
        "break-report.json",
        "extract_lecturenote.py",
        "lecturenote_exercises.json",
        "RECIPE.md",
        "book/",
        "golden/",
    ):
        if name.lower() in text.lower():
            hints.append(name.rstrip("/"))
    for match in re.finditer(r"`([^`]+)`", text):
        token = match.group(1).strip()
        if any(x in token.lower() for x in ("book", "lecture", "break-report", "build.mjs")):
            hints.append(token)
    return hints


def resolve_session_workspace_binding(
    permissions: dict[str, Any] | None,
    *,
    topic: str = "",
    plan_md: str = "",
    run_meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Detect or reuse workspace binding for book sessions."""
    if run_meta:
        bound = run_meta.get("workspace_binding")
        if isinstance(bound, dict) and bound.get("path"):
            path = Path(str(bound["path"])).expanduser()
            preset_id = str(run_meta.get("workspace_preset") or "")
            if path.is_dir() and preset_id == "agent-lab" and is_bundled_app_runtime(path):
                from agent_lab.session.setup import (
                    resolve_workspace_preset,
                    workspace_binding_from_preset,
                )

                preset = resolve_workspace_preset("agent-lab")
                if preset and preset.get("path"):
                    return workspace_binding_from_preset(preset)
            if path.is_dir():
                out = {
                    "path": str(path.resolve()),
                    "label": bound.get("label") or workspace_label(path),
                }
                preset = run_meta.get("workspace_preset")
                if preset:
                    out["preset"] = preset
                return out
        preset_id = str(run_meta.get("workspace_preset") or "")
        if preset_id:
            from agent_lab.session.setup import resolve_workspace_preset, workspace_binding_from_preset

            preset = resolve_workspace_preset(str(preset_id))
            if preset and preset.get("path"):
                return workspace_binding_from_preset(preset)

    hints = _book_path_hints(topic, plan_md)
    if not hints:
        lecture = lecture_script_root()
        if lecture and any(k in topic.lower() for k in ("교재", "book", "lecture", "공수", "pdf")):
            hints = ["build.mjs", "break-report.json"]
    if not hints:
        return None

    cwd, _ = resolve_execute_workspace(permissions, hints)
    lecture = lecture_script_root()
    if lecture is None:
        return None
    try:
        cwd.relative_to(lecture)
    except ValueError:
        if cwd != lecture.resolve():
            return None
    return {"path": str(cwd.resolve()), "label": workspace_label(cwd)}


def apply_discuss_workspace(
    permissions: dict[str, Any] | None,
    binding: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach discuss cwd to permissions for agent backends."""
    out = dict(permissions or {})
    if not binding or not binding.get("path"):
        return out
    out["_discuss_cwd"] = binding["path"]
    cursor = dict(out.get("cursor") or {})
    cursor["local_lecture_script"] = True
    out["cursor"] = cursor
    claude = dict(out.get("claude") or {})
    claude["local_lecture_script"] = True
    out["claude"] = claude
    codex = dict(out.get("codex") or {})
    codex["local_lecture_script"] = True
    out["codex"] = codex
    return out


def discuss_cwd_from_permissions(permissions: dict[str, Any] | None) -> Path | None:
    raw = (permissions or {}).get("_discuss_cwd")
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    if path.is_dir():
        return path.resolve()
    return None


def detect_layout_freeze(messages: list[_MsgLike], topic: str = "") -> bool:
    for source in ([topic] if topic.strip() else []) + [m.content for m in messages if m.role == "user"]:
        for pat in _LAYOUT_FREEZE_PATTERNS:
            if pat.search(source):
                return True
    return False


def _clear_human_gate_meta(meta: dict[str, Any]) -> None:
    for key in (
        "human_gate_pending",
        "human_gate_prompt",
        "human_gate_suggested_pages",
        "last_human_gate",
    ):
        meta.pop(key, None)


def infer_session_phase(
    *,
    layout_frozen: bool,
    topic: str,
    plan_md: str,
    messages: list[_MsgLike],
) -> str:
    if layout_frozen:
        return "content"
    text = f"{topic}\n{plan_md}".lower()
    content_score = sum(1 for h in _CONTENT_PHASE_HINTS if h in text)
    layout_score = sum(1 for h in _LAYOUT_PATH_HINTS if h in text)
    for m in reversed(messages):
        if m.role != "user":
            continue
        body = (m.content or "").lower()
        content_score += sum(1 for h in _CONTENT_PHASE_HINTS if h in body)
        layout_score += sum(1 for h in _LAYOUT_PATH_HINTS if h in body)
        break
    if content_score > layout_score and layout_frozen:
        return "content"
    if layout_score > 0 and content_score == 0:
        return "layout"
    return "content"


def sync_session_meta(
    run_meta: dict[str, Any] | None,
    *,
    topic: str,
    messages: list[_MsgLike],
    plan_md: str = "",
    permissions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update session-level fields on run_meta (mutates in place)."""
    meta = run_meta if run_meta is not None else {}
    prev_frozen = bool(meta.get("layout_frozen"))
    frozen = prev_frozen or detect_layout_freeze(messages, topic)
    if frozen and not prev_frozen:
        from datetime import datetime, timezone

        meta["layout_frozen_at"] = datetime.now(timezone.utc).isoformat()
    meta["layout_frozen"] = frozen
    meta["session_phase"] = infer_session_phase(
        layout_frozen=frozen,
        topic=topic,
        plan_md=plan_md,
        messages=messages,
    )
    binding = resolve_session_workspace_binding(permissions, topic=topic, plan_md=plan_md, run_meta=meta)
    if binding:
        meta["workspace_binding"] = binding
    _clear_human_gate_meta(meta)
    return meta


def build_session_guidance_block(
    run_meta: dict[str, Any] | None,
    *,
    plan_md: str = "",
) -> str:
    """Inject into agent context based on session meta."""
    parts: list[str] = []
    from agent_lab.platform_md import read_platform_md_for_injection

    platform_md = read_platform_md_for_injection()
    if platform_md:
        parts.append(f"[PLATFORM.md — agent protocol]\n{platform_md}")
    if not run_meta:
        return "\n\n".join(parts)
    template_id = run_meta.get("session_template")
    if template_id:
        from agent_lab.session.setup import template_guidance_block

        tpl_block = template_guidance_block(str(template_id))
        if tpl_block.strip():
            parts.append(tpl_block.strip())
    binding = run_meta.get("workspace_binding")
    if isinstance(binding, dict) and binding.get("path"):
        label = binding.get("label") or "book"
        parts.append(
            f"[Session workspace — discuss + execute]\n"
            f"- Bound cwd: `{binding['path']}` ({label}). "
            "Codex `--add-dir`, Cursor bridge cwd, and plan execute must match this root."
        )
        from agent_lab.workspace.md import (
            read_shared_context_for_injection,
            resolve_agents_md_for_guidance,
        )

        shared = read_shared_context_for_injection(run_meta)
        if shared:
            parts.append(f"[SHARED_CONTEXT.md — workspace common]\n{shared}")
        project_md = _read_project_md(run_meta)
        if project_md:
            parts.append(f"[PROJECT.md — workspace memory]\n{project_md}")
        agents_header, agents_body = resolve_agents_md_for_guidance(run_meta, plan_md)
        if agents_body:
            parts.append(f"{agents_header}\n{agents_body}")
    if run_meta.get("layout_frozen"):
        parts.append(LAYOUT_FROZEN_GUIDANCE.strip())
    phase = run_meta.get("session_phase")
    if phase == "content":
        parts.append(CONTENT_ROUND_GUIDANCE.strip())
    parts.append(SINGLE_EXECUTOR_GUIDANCE.strip())
    parts.append(VERIFICATION_ARTIFACT_GUIDANCE.strip())
    if phase == "layout" or run_meta.get("layout_frozen"):
        parts.append(RECIPE_GOLDEN_GUIDANCE.strip())
    return "\n\n".join(parts)


def _read_project_md(run_meta: dict[str, Any]) -> str:
    binding = run_meta.get("workspace_binding")
    if not isinstance(binding, dict):
        return ""
    raw = binding.get("path")
    if not raw:
        return ""
    project = Path(str(raw)) / ".agent-lab" / "PROJECT.md"
    if not project.is_file():
        return ""
    try:
        text = project.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text[:1500]


def _file_sha256(path: Path, *, max_bytes: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read(max_bytes))
    return h.hexdigest()[:12]


def _pdf_page_count(pdf_path: Path) -> int | None:
    if not pdf_path.is_file():
        return None
    try:
        proc = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode != 0:
            return None
        for line in proc.stdout.splitlines():
            if line.lower().startswith("pages:"):
                return int(line.split(":", 1)[1].strip())
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        return None
    return None


def summarize_break_report(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    applied = data.get("appliedBreaks") or []
    baseline = data.get("baseline") if isinstance(data.get("baseline"), dict) else {}
    summary: dict[str, Any] = {
        "path": str(path),
        "generatedAt": data.get("generatedAt"),
        "appliedBreaksCount": len(applied),
        "dryRun": data.get("dryRun"),
        "sha256_12": _file_sha256(path),
    }
    if baseline.get("pdfPageCount") is not None:
        summary["baselinePdfPageCount"] = baseline.get("pdfPageCount")
    if baseline.get("version"):
        summary["baselineVersion"] = baseline.get("version")
    return summary


def verify_execution_artifacts(
    cwd: Path,
    verification_paths: list[str],
) -> dict[str, Any]:
    """Lightweight post-execute artifact check for PDF + break-report."""
    cwd = cwd.resolve()
    pdf_pages: int | None = None
    pdf_path: str | None = None
    break_summary: dict[str, Any] | None = None

    candidates = list(verification_paths) + [
        "break-report.json",
        "공수1_기말학습자료.pdf",
    ]
    seen: set[str] = set()
    for rel in candidates:
        rel_norm = rel.replace("\\", "/").lstrip("./")
        if rel_norm in seen:
            continue
        seen.add(rel_norm)
        path = (cwd / rel_norm).resolve()
        try:
            path.relative_to(cwd)
        except ValueError:
            continue
        if path.suffix.lower() == ".pdf" and path.is_file():
            pdf_path = str(path)
            pdf_pages = _pdf_page_count(path)
        if path.name == "break-report.json" and path.is_file():
            break_summary = summarize_break_report(path)

    ok = break_summary is not None and (pdf_pages is not None or break_summary.get("baselinePdfPageCount"))
    return {
        "ok": bool(ok),
        "pdf_path": pdf_path,
        "pdf_page_count": pdf_pages,
        "break_report": break_summary,
    }


def preserve_session_meta_from_prev(run_meta: dict[str, Any], prev_run: dict[str, Any]) -> None:
    for key in SESSION_META_KEYS:
        if key in prev_run and key not in run_meta:
            run_meta[key] = prev_run[key]
    if prev_run.get("turn_state") and "turn_state" not in run_meta:
        run_meta["turn_state"] = prev_run["turn_state"]
