#!/usr/bin/env python3
"""솔로 vs Room 창발 벤치 — emergence_delta = room − max(solo) (P5).

같은 토픽을 ① 에이전트별 솔로 1회씩 ② 3-agent Room 1회 돌리고
`score_session` 기반 합성 점수로 비교한다. 평균이 아니라 **최강 솔로**를
이겨야 창발이다 (`1+1+1 > max`, not `> avg`).

기본은 mock (`judge: heuristic` 라벨, CI-safe). live는
``AGENT_LAB_EMERGENCE_BENCH_LIVE=1`` + ``--live`` 둘 다 필요하며 CI 금지.

리포트: ``sessions/_reports/emergence_bench_<ts>.json``
가설: deep/critical 카테고리에서만 delta > 0 — 라우터 정당성의 실증 근거.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "sessions" / "_reports"
DEFAULT_TOPICS_PATH = ROOT / "sessions" / "_benchmark" / "topics" / "emergence-v1.json"


def load_default_topics() -> list[dict[str, str]]:
    """SSOT topic set — docs/EMERGENCE-BENCH.md §2."""
    rows = json.loads(DEFAULT_TOPICS_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit(f"topics file must be a JSON list: {DEFAULT_TOPICS_PATH}")
    return rows

# 합성 점수에 들어가는 (key, higher_is_better) — None은 제외.
_COMPOSITE_KEYS: tuple[tuple[str, bool], ...] = (
    ("hybrid_action_rate", True),
    ("challenge_yield", True),
    ("ref_validity_rate", True),
    ("objection_resolution_rate", True),
    ("duplicate_speech_rate", False),
    ("partial_turn_rate", False),
)


def composite_score(scores: dict[str, Any]) -> float | None:
    """단순 평균 합성 (mock judge=heuristic) — 방향 통일 후 0..1."""
    vals: list[float] = []
    for key, higher in _COMPOSITE_KEYS:
        v = scores.get(key)
        if v is None:
            continue
        v = float(v)
        vals.append(v if higher else 1.0 - min(v, 1.0))
    if not vals:
        return None
    return sum(vals) / len(vals)


def _run_session(
    topic: str,
    agents: list[str],
    *,
    sessions_base: Path,
    consensus: bool,
) -> dict[str, Any]:
    from agent_lab import room
    from agent_lab.session.score import score_session

    folder, _messages, _plan = room.run_room(
        topic,
        agents=agents,
        synthesize=True,
        sessions_base=sessions_base,
        consensus_mode=consensus,
    )
    report = score_session(folder)
    return {
        "agents": agents,
        "session_id": report.get("session_id"),
        "composite": composite_score(report.get("scores") or {}),
        "scores": report.get("scores"),
    }


def _run_dispatch_arm(
    topic: str,
    agents: list[str],
    *,
    sessions_base: Path,
) -> dict[str, Any]:
    """Opt-in 4th arm — Room + DISPATCH parallel (CMD-fanout bench)."""
    from agent_lab import room
    from agent_lab.session.score import score_session

    pair = agents[:2]
    folder, _messages, _plan = room.run_room(
        topic,
        agents=agents,
        synthesize=False,
        sessions_base=sessions_base,
        consensus_mode=False,
    )
    room.continue_room_round(
        folder,
        f'DISPATCH parallel: {",".join(pair)}: "emergence bench dispatch survey"',
        agents=agents,
        synthesize=False,
        parallel_rounds=1,
    )
    report = score_session(folder)
    return {
        "agents": pair,
        "session_id": report.get("session_id"),
        "composite": composite_score(report.get("scores") or {}),
        "scores": report.get("scores"),
        "dispatch_fanout_rate": (report.get("scores") or {}).get("dispatch_fanout_rate"),
    }


def bench_topic(
    entry: dict[str, str],
    *,
    sessions_base: Path,
    solo_agents: list[str],
    include_dispatch: bool = False,
) -> dict[str, Any]:
    topic = entry["topic"]
    solos: list[dict[str, Any]] = []
    for agent in solo_agents:
        solos.append(_run_session(topic, [agent], sessions_base=sessions_base, consensus=False))
    room_run = _run_session(topic, list(solo_agents), sessions_base=sessions_base, consensus=True)
    solo_scores = [s["composite"] for s in solos if s["composite"] is not None]
    room_score = room_run["composite"]
    delta: float | None = None
    if solo_scores and room_score is not None:
        delta = room_score - max(solo_scores)
    out: dict[str, Any] = {
        "category": entry.get("category") or "standard",
        "topic": topic,
        "solo": solos,
        "room": room_run,
        "max_solo_composite": max(solo_scores) if solo_scores else None,
        "emergence_delta": delta,
    }
    if include_dispatch:
        out["room_dispatch"] = _run_dispatch_arm(topic, list(solo_agents), sessions_base=sessions_base)
    return out


def aggregate_by_category(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in rows:
        cat = str(row.get("category") or "standard")
        bucket = out.setdefault(cat, {"topics": 0, "deltas": []})
        bucket["topics"] += 1
        if row.get("emergence_delta") is not None:
            bucket["deltas"].append(row["emergence_delta"])
    for bucket in out.values():
        deltas = bucket.pop("deltas")
        bucket["delta_mean"] = (sum(deltas) / len(deltas)) if deltas else None
        bucket["delta_positive"] = sum(1 for d in deltas if d > 0)
    return out


def live_allowed() -> bool:
    return (os.getenv("AGENT_LAB_EMERGENCE_BENCH_LIVE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", help="카테고리 라벨된 토픽 JSON 파일 경로")
    parser.add_argument("--live", action="store_true", help="실 LLM 사용 (CI 금지)")
    parser.add_argument("--out", help="리포트 출력 경로 (기본 sessions/_reports/)")
    parser.add_argument("--sessions-base", help="벤치 세션 폴더 (기본 임시 디렉토리)")
    parser.add_argument(
        "--include-dispatch",
        action="store_true",
        help="opt-in 4th arm: DISPATCH parallel fan-out per topic (CI 기본 off)",
    )
    args = parser.parse_args()

    if args.live:
        if not live_allowed():
            print("live bench requires AGENT_LAB_EMERGENCE_BENCH_LIVE=1", file=sys.stderr)
            return 2
        judge = "oracle"
    else:
        os.environ["AGENT_LAB_MOCK_AGENTS"] = "1"
        judge = "heuristic"
    os.environ.setdefault("AGENT_LAB_CLARIFIER", "0")
    os.environ.setdefault("AGENT_LAB_INBOX_MODE", "soft")

    topics = load_default_topics()
    if args.topics:
        topics = json.loads(Path(args.topics).read_text(encoding="utf-8"))

    if args.sessions_base:
        sessions_base = Path(args.sessions_base)
        sessions_base.mkdir(parents=True, exist_ok=True)
    else:
        sessions_base = Path(tempfile.mkdtemp(prefix="emergence-bench-"))

    solo_agents = ["cursor", "codex", "claude"]
    include_dispatch = bool(
        args.include_dispatch
        or (os.getenv("AGENT_LAB_EMERGENCE_BENCH_DISPATCH") or "").strip().lower() in ("1", "true", "yes", "on")
    )
    rows = [
        bench_topic(
            entry,
            sessions_base=sessions_base,
            solo_agents=solo_agents,
            include_dispatch=include_dispatch,
        )
        for entry in topics
    ]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "judge": judge,
        "mock": judge == "heuristic",
        "solo_agents": solo_agents,
        "include_dispatch": include_dispatch,
        "topics": rows,
        "by_category": aggregate_by_category(rows),
    }

    if args.out:
        out_path = Path(args.out)
    else:
        REPORTS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = REPORTS / f"emergence_bench_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"emergence bench report: {out_path}")
    for cat, bucket in report["by_category"].items():
        print(
            f"  {cat}: topics={bucket['topics']} delta_mean={bucket['delta_mean']} positive={bucket['delta_positive']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
