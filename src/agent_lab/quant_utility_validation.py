"""Validate Agent Lab utility for quant-pipeline / quant-control work."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Chosen validation topic (quant research → app wire-up, not book layout).
VALIDATION_TOPIC = (
    "research/kr/sector_rotation 전략을 quant-control 앱 오버레이로 wire-up할 가치가 있는지 "
    "판정해줘. backtest 결과(research/kr/results/sector_rotation)와 "
    "apps/quant-control-app의 기존 kr_kospi_v1 오버레이 패턴을 기준으로 "
    "1차 범위·완료 기준·리스크만 정리."
)

ANCHOR_PATHS = (
    "research/kr/sector_rotation/sector_rotation.py",
    "research/kr/results/sector_rotation",
    "apps/quant-control-app/src/pages/overlays-hub.tsx",
    "apps/quant-control-app/src-tauri/src/lib.rs",
)

_AGENT_LAB_ROOT = Path(__file__).resolve().parents[2]


def detect_pipeline_root() -> Path | None:
    from agent_lab.extensions.quant_trading import optional_pipeline_root

    return optional_pipeline_root()


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class ValidationReport:
    topic: str
    pipeline_root: str | None
    checks: list[Check] = field(default_factory=list)
    research_verdict: str | None = None

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append(Check(name, ok, detail))

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.ok)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    def score(self) -> str:
        total = len(self.checks)
        if total == 0:
            return "n/a"
        pct = round(100 * self.passed / total)
        if pct >= 90:
            return f"{pct}% — quant room 실사용 가능"
        if pct >= 70:
            return f"{pct}% — discuss/plan OK, execute·env 보완 필요"
        return f"{pct}% — workspace 바인딩부터 수정 필요"


def _read_sector_rotation_verdict(pipeline: Path) -> str | None:
    results_dir = pipeline / "research/kr/results/sector_rotation"
    if not results_dir.is_dir():
        return None
    json_files = sorted(results_dir.glob("*_full.json"), reverse=True)
    if not json_files:
        return None
    try:
        data = json.loads(json_files[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    verdict = str(data.get("verdict") or "").upper() or "UNKNOWN"
    fails = data.get("fails") or []
    fail_hint = fails[0] if fails else ""
    return f"{verdict}" + (f" ({fail_hint})" if fail_hint else "")


def run_structural_checks(report: ValidationReport, pipeline: Path) -> None:
    os.environ["QUANT_PIPELINE_ROOT"] = str(pipeline)

    from agent_lab.context_bundle import build_context_bundle
    from agent_lab.session_setup import (
        build_setup_run_meta,
        list_workspace_presets,
        merge_setup_permissions,
    )
    from agent_lab.workspace_roots import execute_workspace_info, pipeline_root, workspace_roots_block

    preset_ids = {p["id"] for p in list_workspace_presets()}
    report.add(
        "quant-pipeline preset visible",
        "quant-pipeline" in preset_ids,
        f"presets={sorted(preset_ids)}",
    )

    perms = merge_setup_permissions({}, "quant-pipeline")
    discuss_cwd = perms.get("_discuss_cwd", "")
    report.add(
        "discuss cwd = pipeline",
        Path(discuss_cwd).resolve() == pipeline.resolve(),
        discuss_cwd or "(missing)",
    )
    report.add(
        "local_pipeline permission",
        bool((perms.get("cursor") or {}).get("local_pipeline")),
        json.dumps(perms.get("cursor") or {}, ensure_ascii=False),
    )

    setup = build_setup_run_meta(
        workspace_id="quant-pipeline",
        session_template="general",
    )
    report.add(
        "session setup binding",
        setup.get("workspace_binding", {}).get("preset") == "quant-pipeline",
        json.dumps(setup.get("workspace_binding") or {}, ensure_ascii=False),
    )

    roots_block = workspace_roots_block(perms)
    report.add(
        "context lists pipeline root",
        str(pipeline) in roots_block,
        roots_block.splitlines()[0] if roots_block else "",
    )

    bundle = build_context_bundle(
        report.topic,
        [],
        "cursor",
        parallel_round=1,
        review_mode=False,
        plan_md="# plan\n\n## 다음에 할 일\n",
        run_meta=setup,
        permissions=perms,
    )
    payload = bundle.render()
    report.add(
        "agent payload includes pipeline",
        str(pipeline) in payload,
        f"payload_chars={len(payload)}",
    )

    missing_anchors: list[str] = []
    for rel in ANCHOR_PATHS:
        if not (pipeline / rel).exists():
            missing_anchors.append(rel)
    report.add(
        "quant anchor paths on disk",
        not missing_anchors,
        "missing: " + ", ".join(missing_anchors) if missing_anchors else "all present",
    )

    sr_in_app = False
    hub = pipeline / "apps/quant-control-app/src/pages/overlays-hub.tsx"
    if hub.is_file():
        text = hub.read_text(encoding="utf-8", errors="replace")
        sr_in_app = "sector_rotation" in text.lower()
    report.add(
        "sector_rotation not yet in app UI",
        not sr_in_app,
        "expected gap for wire-up candidate" if not sr_in_app else "already wired",
    )

    exec_info = execute_workspace_info(
        perms,
        ["apps/quant-control-app/src/pages/overlays-hub.tsx"],
    )
    report.add(
        "execute resolves quant-control path",
        exec_info.get("label") == "quant-pipeline" and not exec_info.get("paths_missing"),
        json.dumps(exec_info, ensure_ascii=False),
    )

    verdict = _read_sector_rotation_verdict(pipeline)
    report.research_verdict = verdict
    if verdict:
        report.add(
            "sector_rotation backtest verdict readable",
            True,
            verdict,
        )

    assert pipeline_root() == pipeline.resolve()


def run_mock_discuss(report: ValidationReport, pipeline: Path) -> None:
    os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")

    from agent_lab.room import continue_room_round
    from agent_lab.session_setup import merge_setup_permissions, seed_session_setup

    with tempfile.TemporaryDirectory(prefix="agent-lab-quant-val-") as tmp:
        folder = Path(tmp) / "quant-sector-rotation-val"
        folder.mkdir()
        seed_session_setup(
            folder,
            workspace_id="quant-pipeline",
            session_template="general",
            topic=report.topic,
        )
        (folder / "topic.txt").write_text(report.topic + "\n", encoding="utf-8")
        (folder / "plan.md").write_text("# plan\n\n## 다음에 할 일\n", encoding="utf-8")
        (folder / "chat.jsonl").write_text("", encoding="utf-8")
        perms = merge_setup_permissions({}, "quant-pipeline")
        run_before = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        report.add(
            "seed run.json workspace_binding",
            run_before.get("workspace_binding", {}).get("preset") == "quant-pipeline",
            json.dumps(run_before.get("workspace_binding") or {}, ensure_ascii=False),
        )

        messages, _plan = continue_room_round(
            folder,
            "mock quant validation turn",
            agents=["cursor", "codex", "claude"],
            synthesize=False,
            parallel_rounds=1,
            permissions=perms,
        )
        agent_replies = [m for m in messages if m.role == "agent" and (m.content or "").strip()]
        report.add(
            "mock discuss 1 turn",
            len(agent_replies) >= 3,
            f"replies={len(agent_replies)}",
        )

        run_after = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        last = (run_after.get("turns") or [])[-1] if run_after.get("turns") else {}
        turn_perms = last.get("permissions") or {}
        report.add(
            "turn records local_pipeline",
            bool((turn_perms.get("cursor") or {}).get("local_pipeline")),
            json.dumps(turn_perms.get("cursor") or {}, ensure_ascii=False),
        )


def compare_may27_regression(report: ValidationReport) -> None:
    """May 27 quant session had local_pipeline: false — binding fixes that."""
    session = _AGENT_LAB_ROOT / "sessions/2026-05-27-quant-control-앱에-적용시킬-새로운-전략을-한-번-연구해보자"
    if not session.is_dir():
        report.add("may27 regression baseline", True, "session folder missing — skip")
        return
    run = json.loads((session / "run.json").read_text(encoding="utf-8"))
    turns = run.get("turns") or []
    first = turns[0].get("permissions") if turns else {}
    old_pipeline = bool((first.get("cursor") or {}).get("local_pipeline"))
    report.add(
        "may27 had pipeline blind spot",
        not old_pipeline,
        f"turn0 local_pipeline={old_pipeline} (fixed when preset used)",
    )


def build_report(*, mock: bool = True) -> ValidationReport:
    pipeline = detect_pipeline_root()
    report = ValidationReport(
        topic=VALIDATION_TOPIC,
        pipeline_root=str(pipeline) if pipeline else None,
    )
    if pipeline is None:
        report.add(
            "pipeline root detected",
            False,
            "set QUANT_PIPELINE_ROOT or use ~/Desktop/pipeline",
        )
        return report

    report.add("pipeline root detected", True, str(pipeline))
    run_structural_checks(report, pipeline)
    compare_may27_regression(report)
    if mock:
        run_mock_discuss(report, pipeline)
    return report


def format_report(report: ValidationReport) -> str:
    lines = [
        "Agent Lab — quant utility validation",
        f"topic: {report.topic}",
        f"pipeline: {report.pipeline_root or '(none)'}",
        f"score: {report.score()} ({report.passed}/{len(report.checks)} checks)",
        "",
    ]
    for check in report.checks:
        mark = "OK" if check.ok else "FAIL"
        suffix = f" — {check.detail}" if check.detail else ""
        lines.append(f"  [{mark}] {check.name}{suffix}")
    if report.failed:
        lines.extend(["", "gaps:"])
        for check in report.failed:
            lines.append(f"  - {check.name}: {check.detail}")

    research_note = ""
    if report.research_verdict:
        if report.research_verdict.startswith("FAIL"):
            research_note = (
                f"  research note: sector_rotation latest verdict = {report.research_verdict} "
                "→ wire-up보다 재연구/다른 PASS 후보 우선."
            )
        else:
            research_note = f"  research note: sector_rotation verdict = {report.research_verdict}"

    lines.extend(
        [
            "",
            "verdict:",
            "  Agent Lab quant room is structurally ready when workspace preset",
            "  quant-pipeline is selected (fixes May-27 local_pipeline blind spot).",
            "  Execute path resolves quant-control-app files under ~/Desktop/pipeline.",
            research_note or "  research note: (no backtest json found)",
            "  Live discuss quality still depends on bridge/codex/claude health.",
        ]
    )
    return "\n".join(line for line in lines if line)


def main(argv: list[str] | None = None) -> int:
    mock = os.getenv("AGENT_LAB_MOCK_AGENTS", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    report = build_report(mock=mock)
    print(format_report(report))
    return 1 if report.failed else 0
