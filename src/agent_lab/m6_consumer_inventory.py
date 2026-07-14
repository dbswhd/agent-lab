from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final


REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
ALLOWLIST_PATH: Final[Path] = REPO_ROOT / "docs/redesign-2026-07/m6-compatibility-consumer-allowlist-2026-07-14.json"
TARGET_FILES: Final[tuple[str, ...]] = (
    "src/agent_lab/mission/tick.py",
    "src/agent_lab/mission/advance.py",
    "src/agent_lab/runtime/transitions.py",
    "src/agent_lab/runtime/orchestration.py",
    "src/agent_lab/clarity.py",
    "app/server/routers/room.py",
    "web/src/components/ComposerEventStack.tsx",
    "web/src/components/WorkToolPanel.tsx",
    "web/src/components/HumanInboxPanel.tsx",
    "web/src/hooks/useRoomSseHandler.ts",
    "web/src/hooks/useRoomChatInteractions.ts",
    "web/src/utils/workStatusPhase.ts",
    "web/src/components/ContextOverviewPanel.tsx",
    "web/src/components/NotificationCenter.tsx",
    "web/src/components/MissionOverviewSection.tsx",
    "web/src/hooks/useAutonomySession.ts",
    "web/src/utils/missionReadModel.ts",
    "web/src/utils/missionOverviewView.ts",
)


@dataclass(frozen=True, slots=True)
class LegacyReference:
    path: str
    line: int
    kind: str
    operation: str

    @property
    def key(self) -> str:
        return f"{self.path}:{self.line}:{self.kind}"


_PATTERNS: Final[tuple[tuple[str, str, str], ...]] = (
    ("legacy_import", r"\bfrom agent_lab\.(?:run\.meta|mission\.loop|human_inbox) import\b", "import"),
    ("read_run_meta", r"\b(?:read_run_meta|write_run_meta)\b", "read"),
    ("patch_run_meta", r"\bpatch_run_meta\b", "write"),
    ("get_mission_loop", r"\bget_mission_loop\b", "read"),
    ("pending_inbox_items", r"\b(?:pending_inbox_items|fan_out_inbox_item|create_inbox_item)\b", "write"),
    ("run.json", r"run\.json", "read/write"),
    ("mission_loop", r"\bmission_loop\b", "read/write"),
    ("human_inbox", r"\bhuman_inbox\b", "read/write"),
    ("plan_workflow", r"\bplan_workflow\b", "read/write"),
    ("web_mission_loop", r"(?:session\?\.run\?\.mission_loop|mission_loop\.phase)", "read"),
    ("web_human_inbox", r"(?:payload\.human_inbox|human_inbox \?\?)", "read"),
    ("web_plan_workflow", r"(?:runtime\?\.plan_workflow|planWorkflow\?\.)", "read"),
    ("web_merge_oracle", r"(?:mergeChecks|exec\?\.oracle)", "read"),
    (
        "mission_ui_read_model",
        r"\b(?:useMissionReadModel|fetchMissionReadModelIfEnabled|missionReadModelPhase)\b",
        "read",
    ),
)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def collect_references(paths: Iterable[Path], *, root: Path = REPO_ROOT) -> tuple[LegacyReference, ...]:
    found: list[LegacyReference] = []
    for path in paths:
        relative = _relative(path, root)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for kind, pattern, operation in _PATTERNS:
                if re.search(pattern, line):
                    found.append(LegacyReference(relative, line_number, kind, operation))
    return tuple(found)


def load_allowlist(path: Path = ALLOWLIST_PATH) -> frozenset[str]:
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid compatibility allowlist payload: {path}")
    references = payload.get("references")
    if not isinstance(references, list) or not all(isinstance(item, str) for item in references):
        raise ValueError(f"invalid compatibility allowlist references: {path}")
    return frozenset(references)


def check_references(
    paths: Iterable[Path],
    *,
    allowlist_path: Path = ALLOWLIST_PATH,
    root: Path = REPO_ROOT,
) -> tuple[tuple[LegacyReference, ...], tuple[LegacyReference, ...]]:
    references = collect_references(paths, root=root)
    allowed = load_allowlist(allowlist_path)
    unknown = tuple(reference for reference in references if reference.key not in allowed)
    present = {reference.key for reference in references}
    stale_keys: set[str] = set(allowed - present) if root.resolve() == REPO_ROOT.resolve() else set()
    stale = tuple(
        LegacyReference(parts[0], int(parts[1]), parts[2], "unknown")
        for key in sorted(stale_keys)
        for parts in (key.rsplit(":", 2),)
        if len(parts) == 3 and parts[1].isdigit()
    )
    return unknown, stale


def _main() -> int:
    parser = argparse.ArgumentParser(description="Check the M6 compatibility-consumer boundary")
    _ = parser.add_argument("--check", action="store_true")
    parser.parse_args()
    check_requested = "--check" in sys.argv[1:]
    paths = tuple(REPO_ROOT / relative for relative in TARGET_FILES)
    references = collect_references(paths)
    unknown, stale = check_references(paths)
    print(
        json.dumps(
            {
                "target_files": list(TARGET_FILES),
                "reference_count": len(references),
                "unknown": [reference.key for reference in unknown],
                "stale": [reference.key for reference in stale],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if check_requested and (unknown or stale) else 0


if __name__ == "__main__":
    raise SystemExit(_main())
