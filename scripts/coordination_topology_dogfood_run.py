#!/usr/bin/env python3
"""Coordination-topology shadow dogfood — real agent_lab.room.run_room() sessions
(mock agents) across topics spanning every route category, so the shadow decision
wired in topic_router.py has real usage to observe.

Companion to scripts/coordination_topology_report.py — that script reads back
what this one writes. Mirrors the mock/isolated-config conventions already used
by scripts/mission_dual_write_room_dogfood.py and scripts/x2_lift_dogfood_run.py.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "src", ROOT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Real, keyword-verified topics — each one is a plausible thing a user would
# actually type, chosen to land in a specific (category, task_type) cell
# without gaming the classifier beyond what any real prompt would trigger.
TOPICS: tuple[str, ...] = (
    # quick
    "이거 머지됐어?",
    "오타 수정",
    "README 오타 고쳐줘",
    "이 커밋 메시지 리뷰해줘",
    # standard
    "로그인 API 구현해줘 — FastAPI 엔드포인트와 JWT 토큰 검증 로직을 추가해야 합니다.",
    "이 PR 코드 리뷰해줘 — 유저 프로필 업데이트 모듈 변경사항에 대해 피드백 부탁드립니다.",
    "세 에이전트가 합의할 일반적인 작업 주제를 충분히 길게 설명하는 문장입니다. 후속 작업 범위와 담당을 정해야 합니다.",
    "회원 탈퇴 API 구현해줘 — soft delete 방식으로 처리해야 합니다.",
    "이 리팩터링 PR 검토해 봐줘 — 유틸 함수 분리 변경사항 피드백 부탁드립니다.",
    # trading
    "오늘 장중 trading mission 진행 상황 공유",
    "[Trading Mission — 장전] proposal batch 작성",
    # deep
    "모듈 구조 재설계 아키텍처 논의 — 트레이드오프 비교 필수",
    "캐시 아키텍처 설계 검토를 부탁합니다 — 트레이드오프 포함",
    "전체 아키텍처 재설계 — 트레이드오프 비교 필수",
    "이벤트 소싱 전환 아키텍처 논의 — 여러 트레이드오프 비교 필요",
    # critical
    "프로덕션 DB 마이그레이션 절차 결정",
    "프로덕션 DB 마이그레이션 PR 코드 리뷰해줘 — 보안 취약점 검토 필요",
    "프로덕션 시크릿 롤백 불가 변경사항 코드 리뷰해줘",
    "결제 시스템 권한 상승 취약점 보안 검토 및 코드 리뷰",
    # a few more, still real keyword-verified cells, to comfortably clear the
    # report's min-volume gate rather than land exactly on the threshold
    "배포 일정 논의",
    "이 설계 의견 줘",
    "새 클래스 작성해",
    "테스트 작성해줘",
    "PR 검토해 봐줘",
)


@contextmanager
def _isolated_config_dir() -> Any:
    previous = os.environ.get("AGENT_LAB_CONFIG_DIR")
    with tempfile.TemporaryDirectory(prefix="coordination-topology-dogfood-config-") as tmp:
        os.environ["AGENT_LAB_CONFIG_DIR"] = tmp
        try:
            yield Path(tmp)
        finally:
            if previous is None:
                os.environ.pop("AGENT_LAB_CONFIG_DIR", None)
            else:
                os.environ["AGENT_LAB_CONFIG_DIR"] = previous


def _utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _run_one(sessions_base: Path, topic: str, index: int) -> dict[str, Any]:
    from agent_lab import room
    from agent_lab.run.meta import read_run_meta

    session_id = f"dogfood-coordination-topology-{_utc_slug()}-{index:03d}"
    folder, _messages, _plan_md = room.run_room(
        topic,
        agents=["cursor", "codex", "claude"],
        synthesize=False,
        sessions_base=sessions_base,
        session_folder=sessions_base / session_id,
        consensus_mode=True,
    )
    run = read_run_meta(folder)
    turns = run.get("turns") or []
    last_category = None
    for turn in reversed(turns):
        if isinstance(turn, dict) and isinstance(turn.get("category"), dict):
            last_category = turn["category"]
            break
    return {
        "session_id": folder.name,
        "topic": topic,
        "category": (last_category or {}).get("value"),
        "task_type": (last_category or {}).get("task_type"),
        "agent_subset": (last_category or {}).get("agent_subset"),
        "coordination_topology": (last_category or {}).get("coordination_topology"),
        "coordination_topology_reason": (last_category or {}).get("coordination_topology_reason"),
    }


def run_dogfood(sessions_base: Path, *, topics: tuple[str, ...] = TOPICS) -> list[dict[str, Any]]:
    os.environ.setdefault("AGENT_LAB_MOCK_AGENTS", "1")
    os.environ["AGENT_LAB_CLARIFIER"] = "0"
    sessions_base.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    with _isolated_config_dir():
        for i, topic in enumerate(topics):
            try:
                results.append(_run_one(sessions_base, topic, i))
            except Exception as exc:  # noqa: BLE001 - dogfood run, keep going and report the failure
                results.append({"topic": topic, "error": f"{type(exc).__name__}: {exc}"})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Coordination-topology shadow dogfood run (mock agents)")
    parser.add_argument("--sessions", type=str, default=str(ROOT / "sessions"), help="sessions directory")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    results = run_dogfood(Path(args.sessions))
    ok = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    if args.json:
        print(json.dumps({"ok": len(ok), "failed": len(failed), "results": results}, ensure_ascii=False, indent=2))
    else:
        print(f"ran {len(results)} topics — {len(ok)} ok, {len(failed)} failed")
        for row in ok:
            print(
                f"  {row['session_id']}: {row['category']}/{row['task_type']} "
                f"subset={row['agent_subset']} -> {row['coordination_topology']} "
                f"({row['coordination_topology_reason']})"
            )
        for row in failed:
            print(f"  FAILED {row['topic']!r}: {row['error']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
