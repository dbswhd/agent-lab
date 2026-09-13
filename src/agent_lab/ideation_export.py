"""Idea-lane export — the Markdown a user hands to an external agent (RI-11).

Export is a read. It writes no file, starts no subprocess, and changes no
approval state: `plan/approve`, the execute façade, and the external runners
are all untouched by this module. In particular it never writes `plan.md`, so
exporting cannot overwrite a legacy execute session's plan.

The document follows §4.4 of `docs/ROOM-IDEATION-PLAN-2026-09.md`, and is
honest about what is missing: an unresolved BLOCK, a plan written against an
older concept, and unverified assumptions are all stated in the document
rather than smoothed over.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent_lab import ideation
from agent_lab.time_utils import utc_now_iso

EXPORT_SCHEMA = "ideation-export.v1"


def _bullet_list(values: Sequence[str]) -> list[str]:
    return [f"- {value}" for value in values if str(value).strip()]


def _block_warning(objections: Sequence[Mapping[str, Any]]) -> list[str]:
    if not objections:
        return []
    lines = [
        "> **미결 BLOCK이 있습니다.** 아래 이견이 풀리기 전에는 이 계획을 확정본으로 다루지 마세요.",
    ]
    for objection in objections:
        agent = str(objection.get("agent") or "?")
        text = str(objection.get("text") or objection.get("reason") or "").strip()
        refs = objection.get("refs") or []
        ref_text = f" (ref: {', '.join(str(r) for r in refs)})" if refs else ""
        lines.append(f"> - {agent}: {text}{ref_text}")
    return [*lines, ""]


def _stale_warning(data: Mapping[str, Any]) -> list[str]:
    if not data.get("plan_stale"):
        return []
    return [
        "> **계획이 최신 구상보다 오래됐습니다.** "
        f"계획은 revision {data.get('plan_source_revision')} 기준이고 현재 구상은 "
        f"revision {data.get('revision')}입니다. 아래 「바뀐 조건」을 먼저 읽으세요.",
        "",
    ]


def export_markdown(
    run_meta: Mapping[str, Any] | None,
    *,
    topic: str = "",
    plan_md: str = "",
    objections: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Render the export document. Raises for a session with no ideation state."""
    data = ideation.plan_input(run_meta)
    if data is None:
        raise ideation.IdeationError("session has no ideation state")
    state = ideation.read_ideation(run_meta) or {}
    selected = ideation.selected_option(state) or {}
    from agent_lab.room.context.ideation_quality import option_is_synthesis_ready, synthesis_quality

    selected_ready = option_is_synthesis_ready(selected)
    open_blocks = list(objections or [])

    title = str(topic or data.get("original_concept") or "구상").strip()
    lines: list[str] = [
        f"# {title}",
        "",
        f"<!-- {EXPORT_SCHEMA} · ideation revision {data['revision']} · exported {utc_now_iso()} -->",
        "",
        f"- 구상 revision: **{data['revision']}**",
        f"- 계획 기준 revision: {data.get('plan_source_revision') if data.get('plan_source_revision') is not None else '(계획 미작성)'}",
        f"- 단계: {data['stage']}",
        "",
    ]

    lines += _stale_warning(data)
    lines += _block_warning(open_blocks)
    plan_status = str(state.get("plan_status") or "missing")
    if plan_status != "ready":
        lines += [
            f"> **계획 상태: {plan_status}.** 이 문서는 완료된 계획으로 표시하지 않습니다.",
            "",
        ]
    if selected and not selected_ready:
        quality = synthesis_quality(selected)
        lines += [
            "> **검토 필요 — 선택한 구상은 아직 계획 사실로 사용할 수 없습니다.**",
            "미완성 필드나 미확인 레포 주장을 확인한 뒤 다시 계획을 요청하세요.",
            f"검토 상태: {quality['status']}",
            "",
        ]
        parent_ids = (state.get("selection") or {}).get("parent_ids") if isinstance(state.get("selection"), Mapping) else []
        if parent_ids:
            lines.append(
                "- 조합 후보: "
                + " + ".join(str(item) for item in parent_ids)
                + " (각 채택 요소를 확인한 뒤 계획에 반영하세요)"
            )
            lines.append("")

    if data["conditional"]:
        lines += [
            "> **조건부 계획 — 구상이 아직 선택되지 않았습니다.** "
            "아래 내용은 확정된 방향이 아니라 후보에 기반한 초안입니다.",
            "",
        ]

    # The plan body has its own `## 만들려는 것` (the Scribe addendum asks for
    # it), so this wrapper section must not collide with it.
    lines += ["## 고른 구상", ""]
    if data.get("original_concept"):
        lines.append(f"원래 개념: {data['original_concept']}")
    if data.get("desired_change"):
        lines.append(f"원하는 변화: {data['desired_change']}")
    if selected and selected_ready:
        lines.append("")
        lines.append(f"**고른 방향 — {selected.get('title') or selected.get('id')}**")
        for key, label in (
            ("principle", "작동 원리"),
            ("usage", "사용 장면"),
            ("difference", "다른 점"),
            ("tradeoff", "포기하는 것"),
            ("first_experiment", "첫 실험"),
        ):
            value = str(selected.get(key) or "").strip()
            if value:
                lines.append(f"- {label}: {value}")
    if data.get("selection_reason"):
        lines.append(f"- 사용자가 이 방향을 고른 이유: {data['selection_reason']}")
    lines.append("")

    concept = state.get("concept")
    if isinstance(concept, Mapping) and concept:
        lines += ["## 구체화된 구상", ""]
        for key, value in concept.items():
            text = str(value).strip()
            if text:
                lines.append(f"- {key}: {text}")
        lines.append("")

    if data["rejected"]:
        lines += ["## 이미 기각한 방향", "", "새 근거 없이 다시 제안하지 마세요.", ""]
        for item in data["rejected"]:
            lines.append(f"- {item['title']} ({item['id']}) — {item['reason'] or '(이유 미기록)'}")
        lines.append("")

    changes = data.get("condition_changes") or []
    if changes:
        lines += ["## 바뀐 조건", "", "이전 논의보다 아래가 우선합니다.", ""]
        for change in changes:
            for field, delta in (change.get("changed") or {}).items():
                for item in delta.get("added") or []:
                    lines.append(f"- {field} 추가: {item}")
                for item in delta.get("removed") or []:
                    lines.append(f"- {field} 해제: {item} — 더 이상 적용되지 않습니다")
            if change.get("reason"):
                lines.append(f"  - 이유: {change['reason']}")
        lines.append("")

    if data["constraints"]:
        lines += ["## 제약", "", *_bullet_list(data["constraints"]), ""]

    # Assumptions and open questions are the part a plan most often smooths
    # over; they get their own section so they travel with the document.
    if data["assumptions"] or data["open_questions"]:
        lines += ["## 아직 확인되지 않은 것", ""]
        if data["assumptions"]:
            lines += ["**가정 (사실 아님):**", *_bullet_list(data["assumptions"]), ""]
        if data["open_questions"]:
            lines += ["**미결 질문:**", *_bullet_list(data["open_questions"]), ""]

    body = (plan_md or "").strip()
    lines += ["## 구현 계획", ""]
    if body:
        lines += [body, ""]
    else:
        lines += [
            "아직 계획이 작성되지 않았습니다. Room에서 「이 구상으로 계획 만들기」를 먼저 요청하세요.",
            "",
        ]

    lines += [
        "---",
        "",
        "이 문서는 Agent Lab 아이디어 Room에서 내보낸 것입니다. Room은 이 계획을 실행하지 않았고, "
        "실행·merge·검증 승인 권한을 포함하지 않습니다. 첫 작업은 외부 에이전트에서 사용자가 시작합니다.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def export_filename(session_id: str, revision: int) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(session_id))[:60]
    return f"{safe or 'ideation'}-rev{int(revision)}.md"
