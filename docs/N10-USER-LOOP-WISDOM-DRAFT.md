# N10 User-Loop Wisdom — NORTH-STAR 개정안 (DRAFT)

> **작성:** 2026-07-06 · **상태:** ✅ 승인·반영 완료 (2026-07-06) — §2~§5의 삽입 diff는 [NORTH-STAR.md](./NORTH-STAR.md) 본문에 반영됨. 이 문서는 이제 N10 설계 상세(spec)이며, 방향·완성도의 단일 진실은 NORTH-STAR가 가진다.
> **근거 데이터:** 2026-07-06 4-하네스 사용 진단 — Codex 71스레드 · Cursor 389 composer 세션(22.5만 메시지) · gjc 16세션 · Claude Code agent-lab 237세션 샘플링 분석.
> **어휘·모트 선언:** 새 1급 개념 **없음** (§2.2 어휘 6개 동결 준수 — 아래 전부 Wisdom·Oracle·Mission·Room의 하위 개념). 5모트 전부 **강화 또는 중립** (§6 모트 체크).

---

## 0. 배경 — 사용 진단이 드러낸 것

Agent Lab 사용자(운영자 본인)의 4개 하네스 사용 기록을 교차 분석한 결과, 반복 갭 6개가 관측됐다:

| # | 갭 | 근거 (실측) |
|---|---|---|
| G1 | 교정이 설정으로 고정 안 됨 | gjc에서 "한국어로" 재지시 **12회** 반복 |
| G2 | 실패 시 진단 없는 재시도 반사 | gjc 사용자 메시지의 **~12%**가 원인 진단 없는 `retry` |
| G3 | 초장문 세션의 목표 드리프트 | gjc 6일 연속 세션에서 초반 합의 구현 유실을 사용자가 수동 발견 |
| G4 | 위험 영역일수록 검증 느슨 (역전) | 실거래 API 연동이 agent-lab 코어 작업보다 검증 게이트 약함 |
| G5 | UI 미세조정의 왕복 소모 | CC 세션 36개에서 동일 유형 재교정("제대로") 반복 |
| G6 | 설치 능력의 미활용 | CC 스킬 54개 중 실호출 **3개** · Codex context7/codegraph 활성-미사용 · Cursor rules 0개 |

**핵심 재해석:** 6개 갭은 전부 하나의 구조 — **"피드백이 발생하는데 축적되지 않는다"** — 의 변주다. 이는 Agent Lab이 미션 레벨에서 S1 루프(RECALL→APPLY→MEASURE→RECORD)로 풀고 있는 문제와 동형이며, 차이는 관측 대상뿐이다: S1은 **에이전트 턴**을 학습하고, 위 갭은 **사용자 턴**이 학습되지 않아 생긴다.

따라서 본 개정안의 원칙은 NORTH-STAR §1 S3c와 동일하다: **새 학습 시스템을 만들지 않는다. S1 루프의 입력 차원을 사용자 턴까지 확장한다.**

---

## 1. 어휘 매핑 (§2.2 동결 준수 확인)

| 제안 항목 | 소속 어휘 | 하위 개념으로서의 위치 |
|---|---|---|
| N10a Correction Harvester | **Wisdom** | W1 episode의 새 유형 `user_correction` |
| N10b Rule Sync | **Wisdom** | W3 memory의 export 경로 (하네스별 규칙 컴파일) |
| C1 Diagnose-before-retry | **Oracle** | repair loop의 UX 표면화 (§2.4 확장) |
| C2 Drift Audit | **Mission** | goal_ledger 대조의 정례화 (L3 안전장치) |
| C3 Risk-inverse Pinning | **Mission**(라우팅) | topic_router 카테고리 → 프로필 하한 (N2 확장) |
| C4 S3a-0 로컬 인벤토리 | **Wisdom**(도구 카드) | N7/S3a의 선행 단계 재정의 |

---

## 2. 개정안 A — §1 Layer 1 "S3의 구체화" 목록에 S3a-0 삽입

**삽입 위치:** NORTH-STAR §1 Layer 1, "S3의 구체화" 리스트의 S3a 항목 **앞**.

**삽입 텍스트:**

> - **S3a-0 로컬 인벤토리 (선행):** 외부 registry 크롤 전에 **이미 설치된 능력**(CC skills · MCP 서버 · Codex/Cursor 플러그인)을 도구 카드로 인덱싱한다. 사용 진단 실측 — 설치 54개 중 실사용 3개: S3의 첫 병목은 발견(discovery)이 아니라 **회상(recall)** 이다. 미션 RECALL 시점에 "이 카테고리 × 미사용 설치 능력" 매칭을 SetupHint로 주입 (`plugin_discovery.py` 로컬 스캔 확장 + `feedback_advisor` 힌트 채널 재사용). **S1-first 불변과의 정합:** 새 학습 루프가 아니라 RECALL 입력 확장이므로 "S3는 S1 닫힌 후" 순서를 위반하지 않는다. 측정: `tool_card_hit_rate` (§1.4 추가분).

**S3a 문구 후속 수정:** "MCP registry + CC skills 디렉터리 + ... 크롤/인덱싱" 앞에 "(S3a-0 로컬 인벤토리 소진 후)"를 추가.

---

## 3. 개정안 B — §2.1 이니셔티브 표에 N10 행 추가

**삽입 위치:** NORTH-STAR §2.1 표, N9 행 아래.

| # | 이니셔티브 | 내용 | 층 | 시기 |
|---|---|---|---|---|
| **N10** | **User-Loop Wisdom** | 사용자 턴을 S1 입력 차원으로 편입. **N10a Correction Harvester:** 사용자 교정 발화를 `outcomes.jsonl`의 `user_correction` episode로 수확(`outcome_harvester.py` 확장) → 동일 교정 `MIN_SAMPLE`(3회) 이상 관측 시 규칙 후보 승격 → `skill_drafts.py`로 초안 생성 → **Human Inbox 승인** → 영속 규칙 확정. **N10b Rule Sync:** 승인된 규칙을 SSOT로 두고 하네스별 포맷(`.claude/rules/*.md` · `.cursor/rules/*.mdc` · Codex `config.toml`)으로 단방향 export — N6 화이트리스트(`.claude/skills/**`·프롬프트·preset) 경계 안, 코어/전역 config 자동 수정 금지 | L1 | N10a 지금 병행 가능 · N10b 분기 |

**N10a가 S1 dogfood와 병행 가능한 이유 (F1·순서 불변 정합):** RECORD 확장이라 S1 루프 구조를 바꾸지 않고, 재료(`outcome_harvester.py` · `skill_drafts.py` · Human Inbox)가 전부 shipped 상태다. 신규 모듈 0개가 목표.

---

## 4. 개정안 C — 기존 섹션 확장 3건

### C1. §2.4 UX 설계 방향에 6번 항목 추가 — Diagnose-before-retry

> 6. **재시도는 진단을 통과해야 한다** — 도구/턴 실패 시 UI의 재시도 동선을 "진단 요약 1줄 + 재시도"로 교체. 직전 실패와 동일 시그니처의 재시도는 차단하고 Inbox escalation. 새 기능이 아니라 Oracle repair loop(실패→진단→수리)의 UX 표면화 — §2.4-3 Evidence-first의 실패 버전.

### C2. Layer 2 (N4) L3 안전장치로 Drift Audit 명시

**삽입 위치:** §1 Layer 2 "불변:" 문단 뒤.

> **L3 드리프트 감사:** autonomous mission은 N턴(기본 10)마다 초기 `plan.md`+`goal_ledger` 대비 미커버 항목을 자동 대조하고, 미커버 발견 시 Inbox에 "재접지(re-ground) 또는 미션 분할"을 제안한다. 근거: 6일 단일 세션에서 초반 합의가 컨텍스트 요약으로 유실된 실사례 — L3에서는 인간이 이를 발견할 수 없으므로 시스템이 해야 한다. 재료: `completed_steps` + `goal_ledger` (신규 학습 없음, 대조 함수 1개).

### C3. N2 프로필에 Risk-inverse Pinning 추가

**삽입 위치:** §2.1 N2 행의 내용 셀 말미.

> **위험역전 방지 핀:** `topic_router`가 외부 위험 카테고리(trading/live-API/결제 — F5 extension lane 경계와 동일 목록)를 감지하면 프로필 하한 `thorough` + autonomy ceiling **L1**을 핀 고정. 사용자 완화는 명시 override로만 가능하며 `run.json`에 기록. 근거: 사용 진단 G4 — 위험이 클수록 검증이 느슨해지는 역전 관측.

*(참고: 진단 G5 — UI 미세조정 왕복 — 는 N3 `parallel` topology의 기존 옵션(변형 N개 동시 제안)으로 커버 가능하므로 본 개정안에서 신규 항목을 만들지 않는다. §2.5 MoA 행의 "순수 품질 상승 실험" 스코프에 위임.)*

---

## 5. 개정안 D — §1.4 KPI Lexicon에 3행 추가

| KPI | 정의 | 소스 / 메트릭 | 활성 |
|-----|------|----------------|------|
| `correction_recurrence_rate` | 동일 교정 패턴의 세션 간 재발률 (하강 목표 — N10a 효과 측정) | `outcomes.jsonl` `user_correction` rows | N10a 착수 시 |
| `rule_sync_coverage` | SSOT 규칙 중 대상 하네스에 export 완료된 비율 | rule manifest (N10b) | N10b 착수 시 |
| `tool_card_hit_rate` | RECALL이 제안한 설치 능력이 clean-pass에 기여한 비율 | `feedback_report` source 버킷 확장 | S3a-0 착수 시 |

**측정 없는 주장 금지 원칙 준수:** 세 KPI 모두 기존 판독 경로(`make feedback-report JSON=1`)의 필드 확장으로 구현하며, 신규 리포트 도구를 만들지 않는다.

---

## 6. D-사다리 착수 계획 + 모트 체크 (F1 재발 방지)

| 항목 | 현 위치 | D2 닫힘 기준 | D3 도달 계획 | 착수 트리거 |
|---|---|---|---|---|
| N10a Harvester | **D2** (2026-07-06 구현) | ✅ mock: 교정 3회(distinct sessions) → Inbox `correction_rule` 카드 → approve/reject → `.agent-lab/wisdom/correction_rules.md` 승격, 재중복 제안 차단 (`tests/test_correction_harvester.py` 19 cases) | supervisor dogfood에서 `correction_recurrence_rate` 하강 관측 후 default 유지 확정 (현재 이미 default ON — SKILL_DRAFTS 선례) | **완료** — `src/agent_lab/correction_harvester.py`, 플래그 `AGENT_LAB_CORRECTION_HARVESTER`(default 1), `feedback_report.py` `correction_patterns`/`correction_recurrence_rate` |
| C1 retry UX | **D2** (2026-07-06 구현) | ✅ mock: 동일 실패 시그니처 재시도 차단 → Inbox `retry_diagnosis` 에스컬레이션 → force/ack 우회 1회성 소비 (`tests/test_partial_retry.py` 신규 9 cases) + 실브라우저 E2E 확인 | dogfood 2주 후 기본 동선 확정 (현재 로직 상시 ON — 별도 플래그 없음, Oracle repair loop 자체 속성) | **완료** — `src/agent_lab/room/retry.py` (`_failure_signature`/`diagnosis_line`/`_escalate_retry_diagnosis`), `human_inbox.py` kind 추가 |
| C2 Drift Audit | **D2** (2026-07-06 구현) | ✅ mock: 의도적 미커버 plan → Inbox `drift_audit` 제안 발생 → reground 시 재스냅샷 (`tests/test_drift_audit.py` 15 cases) + 실브라우저 E2E 확인 | L3 dogfood 편입 (N4 D3와 동행) | **완료** — `src/agent_lab/drift_audit.py`, 플래그 `AGENT_LAB_DRIFT_AUDIT`(default 1)·`AGENT_LAB_DRIFT_AUDIT_INTERVAL`(default 10), `mission/loop.py`의 `enable_mission_loop(start_autonomous=True)`에서 베이스라인 스냅샷 |
| C3 Risk Pinning | **D2** (2026-07-06 구현, 축소 스코프) | ✅ mock: trading 토픽 감지 → autonomy ceiling L1 핀 → 기존 N4 demotion inbox("Keep L1"/"Restore ceiling") 재사용 → Human override 후 재핀 안 함 확인 (`tests/test_risk_pin.py` 10 cases) | F5 lane 실미션 1회 검증 | **부분 완료** — `src/agent_lab/risk_pin.py`, 플래그 `AGENT_LAB_RISK_PIN`(default 1). **스코프 축소:** "프로필 하한 thorough"는 미구현 — `run/profile.py`의 프로필 적용이 `os.environ` 전역 변경(`apply_run_profile`)이라 세션 단위로 안전하게 못 핀다(다른 동시 세션 오염 위험). Autonomy ceiling L1 핀만으로 이미 실질 안전성 확보(L1은 human 승인 없이 자동실행 안 됨) — profile 하한은 별도 세션 스코프 오버라이드 메커니즘이 생기면 후속 검토 |
| S3a-0 인벤토리 | D0~D1 (`plugin_discovery.py` 부품) | 로컬 스캔 → 도구 카드 ≥ 10 · RECALL 힌트 주입 mock | `tool_card_hit_rate` > 0 관측 | 분기 (N7 설계 문서에 포함) |
| N10b Rule Sync | D0 | 규칙 1개 → 3포맷 export 왕복 테스트 | Human 승인 flow 포함 실사용 1회 | 분기 |

**모트 체크 (착수 전 한 문장 규칙):**

| 모트 | 판정 |
|---|---|
| BLOCK→409 | 중립 — 전 항목 execute 경로 무변경 |
| worktree 격리 | 중립 |
| Oracle+Repair | **강화** — C1이 repair loop를 UX 기본값으로 만듦 |
| run.json 감사 | **강화** — 교정 episode·override·드리프트 제안 전부 기록 |
| Human Inbox | **강화** — 규칙 확정·export·재접지·핀 완화 전부 Inbox 단일 표면 수렴 (§2.4-2) |

**금지 (명시):**
- 사용자 전역 config(`~/.claude/**` · `~/.codex/config.toml` · Cursor 설정)를 **Human Inbox 승인 없이 자동 수정 금지**.
- N10 산출물로 새 1급 어휘·새 리포트 도구·새 학습 루프 신설 금지 — 전부 기존 W1~W3/KPI 판독 경로의 확장이어야 한다.
- D1 상태를 "구현 완료"라 부르는 것 (D-사다리 언어 규칙 준수).

---

## 7. 우선순위 요약

1. **지금:** N10a Correction Harvester — S1 RECORD 확장, 재료 전부 존재, S1 dogfood와 같은 ledger를 공유하므로 관측 비용 0에 가까움.
2. **~1달:** C1 retry UX + C2 Drift Audit — 둘 다 기존 모트(Oracle·goal_ledger)의 표면화.
3. **분기:** C3 Risk Pinning · S3a-0 (N7 `S3-TOOL-CARD-SPEC.md`에 S3a-0 섹션으로 포함) · N10b Rule Sync — §3.3 분기 행의 매트릭스 재검토와 함께.
