from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from agent_lab.run_meta import patch_run_meta

ResponseContractPreset = Literal[
    "concise",
    "evidence_first",
    "plan_ready",
    "review_only",
    "build_handoff",
]


PRESET_LABELS: dict[ResponseContractPreset, str] = {
    "concise": "Concise",
    "evidence_first": "Evidence-first",
    "plan_ready": "Plan-ready",
    "review_only": "Review-only",
    "build_handoff": "Build handoff",
}

RESPONSE_CONTRACT_PRESETS: tuple[ResponseContractPreset, ...] = (
    "concise",
    "evidence_first",
    "plan_ready",
    "review_only",
    "build_handoff",
)

PRESET_GUIDANCE: dict[ResponseContractPreset, str] = {
    "concise": (
        "[Response contract · Concise]\n"
        "Give the shortest useful answer. Lead with status and one concrete next step."
    ),
    "evidence_first": (
        "[Response contract · Evidence-first]\n"
        "Lead with evidence: files, line refs, tests, command output, or artifacts before conclusions."
    ),
    "plan_ready": (
        "[Response contract · Plan-ready]\n"
        "Structure output so Scribe can turn it into `## 지금 실행`: what, where, verify, risks."
    ),
    "review_only": (
        "[Response contract · Review-only]\n"
        "Review and critique only. Do not propose broad implementation unless Human asks."
    ),
    "build_handoff": (
        "[Response contract · Build handoff]\n"
        "End with a clear Build handoff: scope, acceptance checks, blockers, and owner suggestion."
    ),
}


def response_contract_presets() -> list[dict[str, str]]:
    return [
        {
            "preset": preset,
            "label": PRESET_LABELS[preset],
            "guidance": PRESET_GUIDANCE[preset],
        }
        for preset in RESPONSE_CONTRACT_PRESETS
    ]


def normalize_response_contract_preset(value: str) -> ResponseContractPreset:
    preset = value.strip().lower().replace("-", "_")
    for known in RESPONSE_CONTRACT_PRESETS:
        if preset == known:
            return known
    raise ValueError(f"unknown response contract preset: {value}")


def response_contract_guidance(run_meta: dict[str, Any] | None) -> str:
    contract = (run_meta or {}).get("response_contract")
    if not isinstance(contract, dict):
        return ""
    preset_raw = contract.get("preset")
    if not isinstance(preset_raw, str):
        return ""
    try:
        preset = normalize_response_contract_preset(preset_raw)
    except ValueError:
        return ""
    return PRESET_GUIDANCE[preset]


def set_response_contract(
    session_folder: Path,
    preset_value: str,
    *,
    set_by: str = "human",
) -> dict[str, Any]:
    preset = normalize_response_contract_preset(preset_value)
    record: dict[str, Any] = {
        "preset": preset,
        "label": PRESET_LABELS[preset],
        "guidance": PRESET_GUIDANCE[preset],
        "set_by": set_by,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    def _patch(run: dict[str, Any]) -> dict[str, Any]:
        run["response_contract"] = record
        return run

    updated = patch_run_meta(session_folder, _patch)
    saved = updated.get("response_contract")
    return saved if isinstance(saved, dict) else record
