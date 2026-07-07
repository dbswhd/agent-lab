# Agent Lab Work Task Kickoff Template

> **목적:** 새 작업을 시작할 때 `NORTH-STAR.md` + `WORKFLOW-DYNAMIC-REFERENCE.md` + `EVAL-SURFACE-*` 기준으로 범위·의도·검증을 빠르게 고정한다.  
> **사용법:** 이 파일을 복붙해 작업 메모/이슈/PR 초안으로 쓰거나, 필요한 섹션만 채운다.  
> **권장 순서:** `NORTH-STAR.md` → `WORKFLOW-DYNAMIC-REFERENCE.md` → `EVAL-SURFACE-SUPER-SAMPLE-PLAN.md` → `EVAL-SURFACE-V1-PLAN.md`

---

## 0. 작업 한 줄 정의

- **작업명:**
- **한 줄 목적:**
- **왜 지금 필요한가:**

예시:

- **작업명:** Human gate escalation UX 정리
- **한 줄 목적:** inbox escalation 발생 시 사용자와 에이전트가 같은 상태를 보게 만든다
- **왜 지금 필요한가:** N4 autonomy evidence를 쌓으려면 escalation surface가 더 명확해야 한다

---

## 1. NORTH-STAR 기준 분류

### 1.1 이번 작업이 속하는 축

- **Initiative:** `N?`
- **Defect / debt:** `F?`
- **Layer / trust:** `S? / L? / T? / D?`
- **흡수 대상 샘플:**
- **흡수 금지 체크:** 위반 없음 / 있음

예시:

- **Initiative:** `N4`
- **Defect / debt:** `F9`
- **Layer / trust:** `L1~L3`, `D2`
- **흡수 대상 샘플:** Codex approval policy, Devin interactive planning
- **흡수 금지 체크:** Human gate 제거 없음, auto-merge 없음

### 1.2 이번 작업의 north-star 의도

- **이 작업이 강화하는 것:**
- **이 작업이 절대 약화하면 안 되는 것:**
  - [ ] BLOCK→409
  - [ ] worktree 격리
  - [ ] Oracle+Repair
  - [ ] run.json 감사성
  - [ ] Human Inbox

### 1.3 닫힘 기준

- **목표 단계:** `D0 / D1 / D2 / D3 / D4`
- **완료라고 볼 증거:**
- **이번 작업에서 일부러 하지 않는 것:**

---

## 2. Workflow 단계 지정

### 2.1 4과정 중 어디를 건드리는가

- [ ] **① topic_router + role_plan**
- [ ] **② Room agents + objection**
- [ ] **③ Human gate (MCP inbox / autonomy)**
- [ ] **④ plan/execute + worktree + Oracle**
- [ ] **cross-cutting** (`outcomes`, `feedback`, `evals`, docs, runtime flags)

### 2.2 직접 영향받는 단계

- **Primary stage:**
- **Secondary stage:**
- **단계 간 파급:**

예시:

- **Primary stage:** ③ Human gate
- **Secondary stage:** ② Room objection, ④ execute gate
- **단계 간 파급:** inbox escalation 메시지가 execute 409 설명과 연결되어야 함

### 2.3 관련 문서 절

- `WORKFLOW-DYNAMIC-REFERENCE.md` 참고 절:
- `FLOW.md` 참고 절(필요 시):
- `TURN-MODES.md` / `MCP-FIRST-INBOX.md` / `05-room-agent-roles.md` 참고 여부:

---

## 3. 변경 대상 맵

### 3.1 1차 수정 파일

- **코드:**
- **테스트:**
- **fixture / regression session:**
- **문서:**

예시:

- **코드:** `src/agent_lab/autonomy_ladder.py`, `src/agent_lab/human_inbox.py`
- **테스트:** `tests/test_autonomy_ladder.py`, `tests/test_human_inbox.py`
- **fixture:** `sessions/_regression/...`
- **문서:** `docs/WORKFLOW-DYNAMIC-REFERENCE.md` (필요 시)

### 3.2 관련 읽기 범위

- 반드시 읽을 파일:
- 읽으면 좋은 파일:
- 이번 작업에서 건드리지 않을 파일:

### 3.3 플래그 / 프로필 영향

- 신규 플래그 추가 여부: Yes / No
- 추가한다면 `run/profile.py` `flags`/`owns` 반영 필요 여부: Yes / No
- 관련 env:
  - `AGENT_LAB_*`
  - 기본값 / override 방식

---

## 4. 동적 적응 관점에서의 가설

### 4.1 현재 문제

- 현재는 무엇이 **정적**인가?
- 현재는 무엇이 **잘못된 적응**을 하는가?
- 사용자/시스템 입장에서 왜 문제인가?

### 4.2 바꾸고 싶은 적응

- 어떤 신호를 더 읽게 할 것인가?
- 어떤 조건에서 경로를 바꿀 것인가?
- 어떤 조건에서는 **절대** 경로를 바꾸지 말아야 하는가?

예시:

- `pending inbox item` + `risk high`면 Human gate 카피 강화
- `fast preset` discuss lane에서는 여전히 harvest skip 유지
- execute 전 Human gate 제거는 절대 금지

### 4.3 기대되는 결과

- **정확성 측면:**
- **효율 측면:**
- **자율성 측면:**
- **관측성 측면:**

---

## 5. Eval / supersample 영향 분석

### 5.1 영향받는 grader

- [ ] `routing_contract`
- [ ] `session_contract`
- [ ] `generated_mock_quality`
- [ ] `gate_integrity`
- [ ] `objection_flow`
- [ ] `plan_contract`
- [ ] `oracle_coverage`
- [ ] `trace_completeness`

### 5.2 영향받는 case

- `S? / M? / L? / X?`
- 기존 case 수정 / 신규 case 추가 여부:
- mock_run / regression fixture 어느 쪽인지:

### 5.3 영향받는 supersample 지표

- [ ] `routing_pass_rate`
- [ ] `human_gate_bypass_count`
- [ ] `oracle_verdict_coverage`
- [ ] `trace_completeness_rate`
- [ ] `objection_flow_pass_rate`
- [ ] `s_case_quality_pass_rate`
- [ ] `fork_time_minutes`
- [ ] `advisor_lift.*`
- [ ] `turn_source_counts`
- [ ] `escalation_rate_by_level`

### 5.4 canonical definition 충돌 여부

- `completed episode` 정의 영향: Yes / No
- `MIN_SAMPLE` 해석 영향: Yes / No
- `phase == "execute"` 분모 규칙 영향: Yes / No
- 있다면 어떤 문서를 먼저 고쳐야 하는가:

---

## 6. 구현 계획

### 6.1 최소 변경안

1.
2.
3.

### 6.2 대안 비교

| 대안 | 장점 | 단점 | 선택 여부 |
|------|------|------|-----------|
| A | | | |
| B | | | |

### 6.3 이번 PR 범위

- **포함:**
- **제외:**
- **후속 작업으로 미룸:**

### 6.4 불변 조건

- [ ] 기존 regression fixture semantics 유지
- [ ] public re-export 실수로 삭제하지 않기
- [ ] `run_meta` 직접 subscript 금지
- [ ] child process에 전체 env 상속 금지
- [ ] sessions 실데이터 커밋 금지

---

## 7. 검증 계획

### 7.1 최소 로컬 검증

```bash
# 예시
pytest <relevant tests> -q
```

### 7.2 단계별 검증

```bash
# lint / format
make lint
make format-check

# focused tests
pytest ...

# workflow / smoke
python scripts/smoke_room.py

# eval
make eval-surface-check
make feedback-report JSON=1
```

### 7.3 성공 기준

- 어떤 테스트가 초록이어야 하는가:
- 어떤 리포트 수치가 유지/개선되어야 하는가:
- 어떤 regression fixture가 깨지면 안 되는가:

### 7.4 실패 시 확인 순서

1. lint / format
2. 관련 pytest
3. regression fixture
4. eval grader
5. supersample field drift

---

## 8. 커밋/PR 메모 초안

### 8.1 커밋 메시지 초안

```text
<type>(<scope>): <summary>
```

### 8.2 PR 본문 메모

- **문제:**
- **변경:**
- **보호한 모트:**
- **검증:**
- **잔여 리스크:**

---

## 9. 작업 후 기록

### 9.1 실제 결과

- 구현 완료 여부:
- 범위 변경 여부:
- 추가로 발견한 부채:

### 9.2 문서 갱신 필요 여부

- [ ] `NORTH-STAR.md`
- [ ] `WORKFLOW-DYNAMIC-REFERENCE.md`
- [ ] `EVAL-SURFACE-SUPER-SAMPLE-PLAN.md`
- [ ] `EVAL-SURFACE-V1-PLAN.md`
- [ ] `README.md`
- [ ] 없음

### 9.3 다음 작업 제안

- 바로 이어서 할 수 있는 후속:
1.
2.
3.

---

## 10. 빠른 축약 템플릿

짧게 쓰고 싶으면 아래 10줄짜리만 써도 된다.

```md
## Task Kickoff

- 작업명:
- 목적:
- NORTH-STAR 축: `N? / F? / S? / L? / T? / D?`
- 흡수 대상 / 금지 체크:
- Workflow 단계: `① / ② / ③ / ④ / cross-cutting`
- 주요 파일:
- Eval 영향: `grader / case / supersample`
- 검증 명령:
- 모트 체크:
- 완료 기준:
```

---

## 11. 권장 사용 순서

1. `NORTH-STAR.md` 보고 §1 작성
2. `WORKFLOW-DYNAMIC-REFERENCE.md` 보고 §2~4 작성
3. `EVAL-SURFACE-*` 보고 §5 작성
4. §6~7 구현/검증 계획 작성
5. 코딩 시작

---

## 12. 관련 문서

| 문서 | 용도 |
|------|------|
| [NORTH-STAR.md](./NORTH-STAR.md) | 북극성 · 흡수/금지 · D단계 |
| [WORKFLOW-DYNAMIC-REFERENCE.md](./WORKFLOW-DYNAMIC-REFERENCE.md) | 4과정 상세 · 동적 적응 · 비교 · 백로그 |
| [EVAL-SURFACE-SUPER-SAMPLE-PLAN.md](./EVAL-SURFACE-SUPER-SAMPLE-PLAN.md) | canonical definitions · T0/T1/T2 |
| [EVAL-SURFACE-V1-PLAN.md](./EVAL-SURFACE-V1-PLAN.md) | EvalTrace · graders · cases |
| [FLOW.md](./FLOW.md) | 구조 플로우 상세 |
| [MCP-FIRST-INBOX.md](./MCP-FIRST-INBOX.md) | Human gate SSOT |

