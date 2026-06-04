#!/usr/bin/env python3
"""Ops: quant-pipeline workspace memory + preset binding smoke (mock agents)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from agent_lab.project_memory import project_md_path
    from agent_lab.quant_utility_validation import detect_pipeline_root
    from agent_lab.room import continue_room_round
    from agent_lab.session_guidance import build_session_guidance_block
    from agent_lab.session_setup import merge_setup_permissions, seed_session_setup

    pipeline = detect_pipeline_root()
    if pipeline is None:
        print(
            "FAIL: set QUANT_PIPELINE_ROOT or use ~/Desktop/pipeline",
            file=sys.stderr,
        )
        return 1

    project = project_md_path(pipeline)
    if not project.is_file():
        print(f"FAIL: missing {project} — run: make init-project-memory WORKSPACE={pipeline}")
        return 1

    text = project.read_text(encoding="utf-8")
    if "Human이 채움" in text and "2026-06" not in text:
        print("WARN: PROJECT.md still has empty template context — fill ## 현재 작업 맥락")

    with tempfile.TemporaryDirectory(prefix="agent-lab-quant-verify-") as tmp:
        folder = Path(tmp) / "quant-workspace-verify"
        folder.mkdir()
        topic = "[verify] quant-pipeline PROJECT.md injection check"
        (folder / "topic.txt").write_text(topic + "\n", encoding="utf-8")
        (folder / "plan.md").write_text("# plan\n", encoding="utf-8")
        (folder / "chat.jsonl").write_text("", encoding="utf-8")
        seed_session_setup(
            folder,
            workspace_id="quant-pipeline",
            session_template="general",
            topic=topic,
        )
        perms = merge_setup_permissions({}, "quant-pipeline")
        run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        binding = run.get("workspace_binding") or {}
        if binding.get("preset") != "quant-pipeline":
            print(f"FAIL: preset={binding.get('preset')}", file=sys.stderr)
            return 1
        if Path(str(binding.get("path"))).resolve() != pipeline.resolve():
            print(f"FAIL: path mismatch {binding.get('path')}", file=sys.stderr)
            return 1

        block = build_session_guidance_block(run)
        if "PROJECT.md" not in block or len(block) < 200:
            print("FAIL: empty session guidance / no PROJECT", file=sys.stderr)
            return 1

        messages, _ = continue_room_round(
            folder,
            "mock verify turn",
            agents=["cursor", "codex", "claude"],
            synthesize=False,
            parallel_rounds=1,
            permissions=perms,
        )
        replies = [m for m in messages if m.role == "agent" and (m.content or "").strip()]
        if len(replies) < 3:
            print(f"FAIL: expected 3 mock replies, got {len(replies)}", file=sys.stderr)
            return 1

        last = (json.loads((folder / "run.json").read_text(encoding="utf-8")).get("turns") or [])[-1]
        if not (last.get("permissions") or {}).get("cursor", {}).get("local_pipeline"):
            print("FAIL: cursor local_pipeline not set", file=sys.stderr)
            return 1

    print(f"OK: {pipeline}")
    print(f"  PROJECT.md: {project} ({len(text)} chars)")
    print(f"  guidance: {len(block)} chars, mock discuss: {len(replies)} agents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
