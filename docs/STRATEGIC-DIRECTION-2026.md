# Agent Lab 방향성 재검토 플랜

> **기준일**: 2026-06-20 (claude/fugu-release-research-fk8ee4 커밋 상태 기준)
> **참조 분석**: Sakana Fugu (ICLR 2026), revfactory/Harness

---

## 현황 요약

Agent Lab은 264 Python 모듈, 108개 플래그, 40개 회귀 테스트를 가진 Human-in-the-loop Mission OS.

최근 작업(모두 올바른 방향):
- Code-memory MCP 파일럿
- Model Policy
- Dynamic-room
- KIMI Daimon

**문제**: 핵심 강점(검증, 격리, 감사)은 충분하나, 자율성·속도·모델 다양성에서 구조적 열세.

---

## 외부 레포가 보여주는 시장 방향

### Sakana Fugu (ICLR 2026)
- 프론티어 모델 풀 + TRINITY(진화 전략) + Conductor(RL 위상 설계) → 단일 API로 노출
- 새 모델 출시 시 자동 재훈련

### revfactory/Harness
- 6가지 팀 패턴(Pipeline/Fan-out/Expert Pool/Producer-Reviewer/Supervisor/Hierarchical)
- A/B 테스트 +60% 품질
- Progressive Disclosure로 토큰 효율 극대화

---

## 진단: Agent Lab의 구조적 포지션

### 이길 수 없는 영역 (포기해야 할 방향)

| 영역 | 이유 |
|---|---|
| 완전 자율 처리량 | Fugu는 인간 게이트 없이 무한 큐 처리 — Agent Lab의 설계 철학과 정면 충돌 |
| 모델 앙상블 벤치마크 | Fugu Ultra는 ICLR 논문 + RL 훈련 기반 조율 — 단기 따라잡기 불가 |

### 이길 수 있는 영역 (집중해야 할 방향)

| 강점 | 설명 |
|---|---|
| **검증 우월성** | Oracle + Repair loop + Adversarial gate — Fugu에 없음 |
| **격리 안전성** | Git worktree 기반 실행 — 실패해도 main 브랜치 안전 |
| **감사 가능성** | run.json 전체 의사결정 이력 — 규제·팀 환경의 필수 요소 |
| **거버넌스 메커니즘** | BLOCK → 409, objection 추적 — 조직 신뢰 기반 배포의 핵심 |
| **Human-AI 협업 깊이** | Human Inbox, plan 공동 작성 — Fugu가 줄 수 없는 것 |

---

## 전략적 방향: "Trusted Autonomous Mission Platform"

현재 `"Human-in-the-loop OS"` → `"신뢰 수준에 따라 자율도가 조정되는 미션 플랫폼"`으로 전환.

인간 게이트를 없애는 게 아니라, **신뢰도가 높을 때는 자동으로, 불확실할 때는 반드시 인간을 거치게 하는 구조**.

---

## 북극성 (North Star): 협업을 통한 창발 → 자기발전

> 개인이 모델 성능 자체를 끌어올릴 수는 없다. 대신 **다중 에이전트의 협업과 그로부터 발생하는 창발(emergence)** 로 AGI적 자기발전에 접근한다.

대형 AI 회사들이 **모델 가중치**를 개선하는 경쟁을 하는 동안, Agent Lab이 노리는 틈새는 **런타임의 협업 토폴로지와 창발 과정 그 자체**다. 약간의 컨셉·토픽·과제만 주어지면 에이전트들이 **스스로 계획하고 서로 보완하는 과정을 반복**할 수 있어야 한다 — loop와 Room이 존재하는 이유.

### 단순 병렬 ≠ 창발. 창발의 3대 전제 조건

| 조건 | 의미 | Agent Lab 현 위치 |
|---|---|---|
| **비대칭 역할** | 서로 다른 관점이 충돌해야 한다. 동일 에이전트 N개는 그냥 투표 | Proposer/Critic/Synthesizer 역할 레이어 (29456bc) |
| **피드백 루프** | 이번 라운드 출력이 다음 라운드 컨텍스트를 바꿔야 한다 | Room turn flow |
| **실패 학습** | 검증 실패를 기록하고 다음 실행이 그 실패를 알고 시작 | run.json + Code-memory MCP |

### Fugu가 할 수 없는 것 = Agent Lab만의 공간

Fugu는 재훈련 루프로 **모델 자체**를 개선하지만, 런타임에 **도메인 지식과 팀 구성을 스스로 바꾸는** 것은 하지 않는다. Agent Lab이 목표하는 자기발전 루프:

```
토픽/과제 입력
  → 어떤 역할 조합이 필요한지 스스로 결정 (topic_router + Expert Pool)
  → 실행 → Oracle 검증
  → 실패면 역할 재구성 / 다른 에이전트 풀 선택
  → 성공·실패 패턴을 cross-session 메모리에 기록
  → 다음번엔 더 나은 팀 구성으로 시작
```

이것이 "모델을 못 바꾸는 개인"이 도달할 수 있는 자기발전에 가장 가까운 형태다.

### 3단계 로드맵 (장기)

| 단계 | 목표 | 의존 |
|---|---|---|
| **S1. 내부 루프 폐쇄** | Oracle 성공/실패 패턴이 다음 Room 세팅에 자동 반영되는 피드백 회로 | P0 (Dynamic Room, Code-memory MCP) 완성 후 |
| **S2. 팀 구성 자기조정** | 과제 유형별 최적 역할 조합을 스스로 학습·재사용 (Expert Pool 진화) | S1 + run.json 패턴 집계 |
| **S3. 외부 능력 자가 통합** | Codex/Cursor/Claude Code의 스킬·플러그인 + 외부 MCP를 스스로 연결·활용 | S1/S2 안정화 후 (먼저 내부 루프가 돌아야 외부 확장이 의미 있음) |

> **순서가 핵심**: 외부 도구 통합(S3)은 매력적이지만, 내부 자기발전 루프(S1)가 닫히기 전에는 도구만 늘고 창발은 안 생긴다. 내부 루프 → 팀 자기조정 → 외부 확장 순으로 간다.

---

## 우선순위별 이니셔티브

### P0 — 진행 중인 작업 완성 (지금 당장)

**1. Dynamic Room 완성** (`feat(dynamic-room)` 브랜치)
- 현재: cursor/codex/claude 3개 고정
- 목표: 작업 유형에 따른 에이전트 구성 동적 선택
- 구체적으로: `topic_router.py`의 quick/analyze/deep 분기에 맞는 에이전트 풀 매핑
- Harness의 "Expert Pool" 패턴 적용 — 코드 작업에는 cursor+codex, 리뷰에는 claude+kimi

**2. Model Policy 강화** (`feat(model-policy)`)
- 현재: conservative profiles for substitute agents (이미 시작됨)
- 목표: Fugu처럼 작업 복잡도 → 모델 선택 자동화
- `trust_budget.py` + `model_policy.py` 연동: 신뢰 예산 소진 시 보수적 모델로 자동 강등

**3. Code-memory MCP 파일럿** (`feat(code-memory)`)
- 현재: Phase 0 read-only pilot for Claude/Codex
- 목표: Wisdom Index(MB-10)와 연결해 cross-session 학습
- Fugu가 모델 재훈련으로 하는 것을 Agent Lab은 세션 메모리로 대체

---

### P1 — 핵심 경쟁력 강화 (다음 2주)

**4. 신뢰 기반 자동 승인 (Trust-gated Auto-approval)**
- 문제: 인간 게이트 2개(plan 승인 + diff 승인)가 효율의 최대 병목
- 해결: Oracle confidence + diff risk score 조합으로 자동 통과 기준 정의

  | 위험도 | 처리 방식 |
  |---|---|
  | LOW + Oracle 신뢰도 HIGH | 30초 타임아웃 후 자동 승인 |
  | MEDIUM | 현행 인간 게이트 |
  | HIGH | 필수 인간 게이트 + 추가 adversarial review |

- 구현 위치: `plan_execute_verify.py` + `verify_repair_policy.py`
- 관련 플래그: `AGENT_LAB_ORACLE_LIVE` + 새 `AGENT_LAB_AUTO_APPROVE_THRESHOLD`

**5. Harness 패턴 통합 (Room Preset System)**
- 현재: 모든 작업이 같은 3-agent consensus 흐름
- 목표: Harness의 6 패턴을 Agent Lab Room preset으로 구현

  | 프리셋 | 설명 |
  |---|---|
  | `quick` | 단일 에이전트 (현재 topic_router 있음) |
  | `pipeline` | 순차 전문화 (scribe 패턴 확장) |
  | `producer_reviewer` | 제안 → Oracle 검증 (verified loop 재활용) |
  | `consensus` | 현행 3-agent 합의 (유지) |
  | `supervisor` | Mission Loop의 DISCUSS→EXECUTE FSM (이미 존재) |

- 구현 위치: `turn_modes.py` + `room_turn_flow.py`에 preset 파라미터 추가
- 프론트엔드: 세션 생성 시 Room Preset 선택 UI

**6. 108개 플래그 → 4개 프로필 정리**
- 문제: 108개 플래그는 전문가 전용 — 일반 사용자 진입 장벽
- 목표: 프로필 개념 도입

  | 프로필 | 구성 |
  |---|---|
  | `fast` | 단일 에이전트, 자동 승인, Oracle mock |
  | `balanced` | 3-agent, 인간 gate, Oracle live (기본) |
  | `thorough` | 3-agent + kimi, 전체 adversarial, live judge |
  | `autonomous` | mission loop + 자동 승인 + 예산 기반 실행 |

- 구현: `app_config.py`에 profile → flag 매핑 테이블 추가
- 플래그는 여전히 개별 override 가능 (전문가용 유지)

---

### P2 — 중기 경쟁력 (다음 한 달)

**7. OpenAI-compatible API 노출**
- Fugu의 핵심 가치: 복잡한 내부 조율을 단일 API로 노출
- Agent Lab도 가능: FastAPI 기반 `/v1/chat/completions` 엔드포인트
- 내부에서는 Room 토론 + Oracle 검증 + worktree execute를 모두 수행
- 응답에 audit trail 포함 (선택적 `X-AgentLab-RunId` 헤더)
- 이렇게 하면 Agent Lab이 Fugu와 같은 레이어에서 경쟁 가능
- 구현: `app/server/routers/openai_compat.py` 라우터 추가

**8. Evidence + Verification API 공개**
- Agent Lab의 독보적 강점: Oracle 검증 + 증거 게이트
- 이를 외부에서 호출 가능한 API로 노출
- 다른 에이전트 시스템(Fugu 포함)이 실행한 결과를 Agent Lab Oracle이 검증하는 "검증 서비스"
- 구현: `app/server/routers/evidence_gates.py` 공개 엔드포인트

---

## Agent Lab만의 모트 (절대 포기하지 말 것)

```
1. BLOCK → 409         # 어떤 에이전트도 이의 제기 가능
2. Worktree 격리        # 실패가 main을 오염시키지 않음
3. Oracle + Repair     # 실행 후 자동 검증 + 자동 수정
4. run.json 감사 이력   # 모든 결정의 who/why/when 기록
5. Human Inbox         # 에이전트가 인간에게 질문 가능
```

이 5개는 Fugu와 Harness 어디에도 없다. 여기에 집중할 것.
