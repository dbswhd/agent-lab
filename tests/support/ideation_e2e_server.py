"""Dedicated real HTTP server for web/playwright.ideation.config.ts.

Only the provider response/readiness boundary is replaced. Session creation,
Room turns, SSE, Scribe orchestration, quality gates, and storage are production.
Startup daemons are omitted: this harness is a foreground test HTTP service.
No session or ideation state is seeded here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    sandbox = Path(os.environ["AGENT_LAB_IDEATION_E2E_ROOT"])
    for name in ("config", "sessions", "logs"):
        (sandbox / name).mkdir(parents=True, exist_ok=True)
    os.environ.update({
        "AGENT_LAB_CONFIG_DIR": str(sandbox / "config"),
        "AGENT_LAB_SESSIONS_DIR": str(sandbox / "sessions"),
        "AGENT_LAB_LOG_DIR": str(sandbox / "logs"),
        "AGENT_LAB_BOOTSTRAPPED": "1",  # never read a developer's .env/credentials
        "AGENT_LAB_MOCK_AGENTS": "1",
        "AGENT_LAB_RUN_PROFILE": "fast",
        "AGENT_LAB_ROOM_MODELS": "cursor,codex,claude",
        "AGENT_LAB_MISSION_AUTHORITY": "0",
        "AGENT_LAB_MISSION_SCHEDULER": "0",
        "AGENT_LAB_AUTO_EXECUTE": "0",
        "AGENT_LAB_TOOL_LOOP": "0",
    })

    from agent_lab.agents import registry
    from agent_lab.agent import health, preflight

    def provider_ready(agent_id: str, **_kwargs: object) -> dict[str, object]:
        return {
            "id": agent_id, "label": agent_id, "model": "ideation-e2e",
            "ready": True, "configured": True, "bridge": "ok", "hint": None,
            "reason": None, "bridge_mode": "mock-provider",
        }

    health.agent_health_row = provider_ready
    preflight.agent_preflight_row = provider_ready

    def response(agent: str, user: str, *, scribe: bool = False) -> str:
        # Provider calls are audit evidence, not state injection.
        with (sandbox / "provider-calls.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"agent": agent, "scribe": scribe, "user": user}, ensure_ascii=False) + "\n")
        if scribe:
            if "E2E_SCRIBE_FAILURE" in user:
                raise RuntimeError("Deterministic provider failure for E2E")
            return """# 강의자료 학습 도구

## 만들려는 것
강의자료를 바탕으로 근거를 추적할 수 있는 학습 자료를 만든다.

## 선택한 방향
출처 연결 학습 카드와 회상 문제를 함께 제공한다.

## 제약
브라우저에서만 사용한다. 비용은 월 1만원 이내다. 오프라인 복습을 지원한다.

## 구체화
첫 과목 한 개에서 강의자료의 출처 페이지를 표시하고 회상 문제 10개를 만든다.

## 지금 실행
1. 첫 과목에서 학습 자료를 시험한다
   - 무엇을: 출처 페이지가 표시된 회상 문제 10개를 만들어 대조한다
   - 어디서: 새 학습 자료
   - 검증: 문제 10개 모두 근거 페이지와 정답을 사람이 확인한다

## 아직 확인되지 않은 것
가정: 교수자의 시험 출제 범위는 별도로 확인해야 한다.
"""
        title = {"cursor": "출처 연결 학습 카드", "codex": "회상 문제 학습 루프", "claude": "누락 점검 학습 지도"}.get(agent, "학습 카드")
        principle = "출처 페이지와 핵심 개념을 함께 저장한다"
        if "E2E_UNVERIFIED" in user:
            principle = "현재 레포 src/nonexistent-e2e.py에 완성된 파서가 구현되어 있다"
        return f"""제목: {title}
작동 원리: {principle}
사용 장면: 강의가 끝나면 개념을 읽고 회상 문제를 푼다
다른 점: 요약에 출처와 이해도 확인을 연결한다
포기하는 것: 모든 과목을 한 번에 지원하지 않는다
첫 실험: 한 과목으로 문제 10개를 만들어 근거와 정답을 확인한다
"""

    registry._mock_agent_response = response
    from app.server.main import create_app
    import uvicorn
    uvicorn.run(create_app(bootstrap=False), host="127.0.0.1", port=8877, lifespan="off")


if __name__ == "__main__":
    main()
