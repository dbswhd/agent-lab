# MD 파일 작성 극대화 계획

> 작성: 2026-06-03  
> 목적: Agent Lab의 각 MD 파일을 어떻게 써야 에이전트가 가장 잘 따르는지,  
> 내용 구성·작성 방식·규칙·구조를 파일별로 완전히 정의한다.

> **구현 상태:** [EXTERNAL-REFS-TRACEABILITY.md](EXTERNAL-REFS-TRACEABILITY.md) §Dev-tool 섹션이 정식 추적처.  
> 이 문서는 **how to write** 가이드이며, **what is shipped**는 TRACEABILITY를 참조.  
> MD-SYSTEM-DESIGN.md(파일 맵)와 겹치는 내용은 이 문서가 canonical; 양쪽이 충돌하면 이 문서 기준.

> **현재 구현 상태 (2026-06-03):** CLAUDE.md 미작성, `.claude/rules/` 없음, PLATFORM.md/PROJECT.md 주입 미구현.  
> 아래 "전체 실행 계획" 섹션에서 shipped vs planned 구분 확인.

---

## 핵심 원리 (모든 MD에 공통 적용)

### 왜 에이전트가 MD를 무시하는가

MD는 context window에 텍스트로 주입됩니다. 에이전트에게 "강제"가 아닌 "부탁"입니다.  
잘 안 따르는 이유는 세 가지입니다:

```
1. 모호함     "코드를 깔끔하게 써라" → 에이전트가 판단 기준이 없음
2. 과부하     200줄 넘는 CLAUDE.md → 앞부분만 읽고 나머지 무시
3. 모순       파일 A에서 "항상 X", 파일 B에서 "절대 X 금지" → 임의 선택
```

### 극대화 원칙 5가지

```
[원칙 1] 검증 가능하게
  ❌  "코드를 잘 포매팅해라"
  ✅  "Python: ruff format 적용, line-length=120"

[원칙 2] 파일마다 한 가지 역할
  ❌  CLAUDE.md에 빌드 명령 + 아키텍처 설계 결정 + 개인 선호 혼재
  ✅  빌드 → CLAUDE.md / 아키텍처 깊은 내용 → SKILL.md / 개인 → CLAUDE.local.md

[원칙 3] 항상 로드 vs 필요 시 로드 분리
  ❌  모든 내용을 CLAUDE.md에 (매 세션 토큰 낭비)
  ✅  핵심 규칙 → CLAUDE.md (매 세션) / 참고 문서 → SKILL.md (필요 시)

[원칙 4] 금지형이 허용형보다 강하다
  ❌  "가능하면 main.py에 직접 추가하지 말아라"
  ✅  "main.py에 라우터 직접 추가 금지. 반드시 routers/ 사용."

[원칙 5] 에이전트별로 다르게 써라
  → CLAUDE.md는 Claude Code 관점에서 (개발 도구 레이어)
  → PROJECT.md는 Agent Lab 런타임 관점에서 (모든 에이전트에게 동일 주입)
  → AGENTS.md는 Codex CLI가 읽는 방식으로 (실행·검증 중심)
```

---

## 파일 1: CLAUDE.md (개발 도구 레이어)

### 역할

Claude Code가 Agent Lab **개발** 시 매 세션 자동으로 읽는 파일.  
"이 코드베이스에서 개발할 때 항상 알아야 하는 것"만 담는다.

### 크기 규칙

**목표: 80줄 이하** (200줄 한도의 40%만 사용)  
나머지는 `.claude/rules/` 또는 `SKILL.md`로 분산한다.

### 섹션 구조 (고정)

```markdown
# Agent Lab 개발 가이드

## 빠른 시작              ← 빌드/실행 명령 (10줄 이내)

## 핵심 모듈              ← 파일 → 역할 매핑 (10줄 이내)

## 코드 규칙              ← 검증 가능한 규칙만 (10줄 이내)

## 절대 금지              ← 금지 사항만 모아서 (5줄 이내)

## 아키텍처 불변 원칙     ← 설계 결정 (5줄 이내)
```

### 작성 실전 가이드

**빠른 시작 섹션 — 명령어만, 설명 최소화**
```markdown
## 빠른 시작
- make dev         → API(8765) + web(5173)
- make test        → pytest 316+ tests (~9s)
- make smoke-e2e   → E2E mock (MOCK_AGENTS=1)
- make score-session SESSION=sessions/<id>
```

**핵심 모듈 섹션 — 파일 경로 + 한 줄 역할**
```markdown
## 핵심 모듈
- `src/agent_lab/room.py` — 멀티에이전트 오케스트레이션 (2600줄)
- `src/agent_lab/plan_execute*.py` — execute gate + worktree + merge
- `src/agent_lab/room_objections.py` — BLOCK → execute 409
- `src/agent_lab/cli_retry.py` — CLI retry (429/timeout, ✅ 구현됨)
- `src/agent_lab/subprocess_env.py` — CLI env allowlist (✅ 구현됨)
- `app/server/routers/` — FastAPI 라우터 (ops-P2 분리 완료)
- `web/src/components/` — React 컴포넌트 40+
```

**코드 규칙 섹션 — 검증 가능 = 동사+대상+기준**
```markdown
## 코드 규칙
- Python 파일 첫 줄: `from __future__ import annotations` 필수
- 새 API 라우터: `app/server/routers/` 에 추가 (`main.py` 직접 추가 금지)
- 테스트: `AGENT_LAB_MOCK_AGENTS=1` mock-only (316+ tests, 실 LLM 호출 없음)
- run.json 수정: `patch_run_meta()` 경유 (`json.dump` 직접 쓰기 금지)
- subprocess 실행: `subprocess_env.py:subprocess_env()` 사용 (env 전체 상속 금지)
```

**절대 금지 섹션 — 금지만 모아서 (경고 강도 높임)**
```markdown
## 절대 금지
- `sessions/*` 커밋 금지 (`sessions/_regression/` 제외, gitignore 처리됨)
- `plan_execute.py` 검증 없이 execute gate 우회 금지
- 에이전트 subprocess에 `.env` 전체 환경변수 전달 금지
```

**아키텍처 불변 원칙 — 설계 철학, 짧게**
```markdown
## 아키텍처 불변 원칙
- 합의=Room · 격리=worktree · 완료=Oracle verified
- BLOCK → execute 409 (plan 모드 한정, discuss는 soft)
- plan.md = 세션 메모리 + execute 계약 + provenance 앵커
- Human gate 유지 (완전 자율 실행 배제)
```

### import 활용법 (크기 초과 시)

```markdown
# CLAUDE.md (80줄 초과 시)

@.claude/CONTEXT.md        ← 추가 아키텍처 설명
@docs/STABILITY.md         ← 안정성 체크리스트

## 빠른 시작
...
```

> ⚠️ import된 파일도 세션 시작 시 전체 로드됨 (컨텍스트 절약 아님)  
> → 절약이 목적이면 SKILL.md 사용

### 유지 관리 규칙

| 트리거 | 액션 |
|--------|------|
| 같은 실수를 Claude가 두 번 반복 | CLAUDE.md에 금지 규칙 추가 |
| CLAUDE.md 100줄 초과 | 가장 긴 섹션을 rules/ 또는 SKILL.md로 이동 |
| 팀원이 "이거 어디 있어?" 자주 질문 | 해당 내용 CLAUDE.md 핵심 모듈에 추가 |
| 규칙이 서로 충돌 | 즉시 제거 (모호한 쪽 삭제) |

---

## 파일 2: .claude/rules/*.md (경로별 규칙)

### 역할

CLAUDE.md가 80줄 이하를 유지하도록 경로별 세부 규칙을 분산 저장.  
해당 경로 파일 작업 시에만 로드 → 토큰 절약.

### 구조 규칙

```markdown
---
paths:
  - "src/agent_lab/**/*.py"
  - "app/**/*.py"
---

# 파일명으로 주제 명확히 (python-backend, react-frontend 등)

## 핵심 패턴
(가장 중요한 것 3–5개)

## 금지
(이 경로에서 절대 하면 안 되는 것)

## 참고 모듈
(연관된 파일/함수 링크)
```

### Agent Lab용 rules 파일 상세

**python-backend.md**
```markdown
---
paths:
  - "src/agent_lab/**/*.py"
  - "app/**/*.py"
  - "tests/**/*.py"
---

# Python 백엔드 규칙

## 타입 & 스타일
- `from __future__ import annotations` 모든 파일 첫 줄
- dataclass(`@dataclass`) 우선; 단순 dict return보다 typed class
- 에러: `RuntimeError` 대신 도메인 Exception (`ObjectionBlocksExecute` 패턴)
- 함수 반환 타입 명시 (`-> dict[str, Any]` 등)

## 상태 변경 규칙
- `run.json` 직접 수정 금지 → `patch_run_meta(folder, {...})` 경유
- `chat.jsonl` 직접 쓰기 금지 → `session.py` 함수 경유
- `plan.md` 직접 쓰기 금지 → `synthesize_plan()` 또는 `_write_plan_if_changed()` 경유

## 테스트
- 모든 테스트: `AGENT_LAB_MOCK_AGENTS=1` 환경에서 동작해야 함
- 실 LLM 호출 테스트 금지 (CI에서 secrets 없음)
- fixture 패턴: `sessions/_regression/` 에 JSONL로 저장

## 금지
- `subprocess.run(env=None)` → 반드시 허용 키만 필터링된 `safe_env` 전달
- `json.loads(open(...).read())` → `run_meta.read_run_meta(folder)` 경유
```

**react-frontend.md**
```markdown
---
paths:
  - "web/src/**/*.tsx"
  - "web/src/**/*.ts"
---

# React 프론트엔드 규칙

## API 호출
- 모든 서버 통신: `web/src/api/client.ts` 함수만 사용
- 직접 fetch 금지, axios 도입 금지
- SSE 스트림: `useRoomStream` 훅 사용 (직접 EventSource 생성 금지)

## 컴포넌트
- 새 컴포넌트: `web/src/components/` (기존 패턴 따라 작명)
- 스타일: CSS Modules 또는 인라인 style (Tailwind/styled-components 도입 금지)
- 상태: React state + context (Redux/Zustand 도입 금지)

## 타입
- API 응답 타입: `web/src/api/client.ts` 에 정의된 타입 사용
- `any` 사용 시 주석으로 이유 명시

## 금지
- `console.log` 커밋 금지 (dev-only라도)
- 하드코딩 API URL 금지 → `API_BASE` 상수 사용
```

---

## 파일 3: SKILL.md (반복 워크플로)

### 역할

CLAUDE.md에 넣기엔 너무 길고, 매 세션 필요하지도 않은 **반복 절차**.  
`/skill-name`으로 호출하거나 Claude가 자동 판단.

### 프론트매터 필드 (중요한 것만)

```markdown
---
name: skill-name              # /skill-name 으로 호출
description: 한 줄 설명      # Claude가 자동 판단 시 이 설명으로 매칭
model: claude-sonnet-4-6     # 기본값과 다를 때만 명시
tools: Bash, Read, Edit       # 허용 도구 명시 (생략 시 전체)
context: fork                 # 격리 실행 원하면 (기본: 현재 세션)
disable-model-invocation: false  # true면 Human만 호출 가능
---
```

### 작성 전략

**Good skill의 조건:**
1. 3번 이상 같은 프롬프트를 붙여 넣었다 → Skill로
2. 10줄 이상의 절차가 있다 → Skill로
3. 특정 도구 조합이 필요하다 → Skill로 (도구 제한 가능)

**Bad skill의 조건:**
- 매 세션 항상 필요한 것 → CLAUDE.md로
- 1–2줄짜리 단순 명령 → alias 또는 Makefile로

### Agent Lab Skill 작성 실전

**smoke-and-score/SKILL.md**
```markdown
---
name: smoke-and-score
description: 스모크 테스트 실행 후 가장 최근 세션의 품질 KPI를 측정하고 리포트
tools: Bash
---

# 스모크 + 세션 스코어 리포트

## 실행 순서

1. **E2E 스모크 테스트**
   ```bash
   AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/smoke_room_e2e.py
   ```

2. **최근 세션 찾기**
   ```bash
   LATEST=$(ls -t sessions | grep -v _regression | grep -v '^\.' | head -1)
   echo "대상 세션: $LATEST"
   ```

3. **품질 스코어 측정**
   ```bash
   make score-session SESSION=sessions/$LATEST
   ```

## 리포트 형식
다음 지표를 표로 요약:
- objection_resolution_rate (목표 >80%)
- execute_retry_rate (목표 <30%)
- ref_validity_rate (목표 >90%)
- duplicate_speech_rate (목표 <20%)

임계값 미달 항목은 원인과 개선 제안 포함.
```

**regression-check/SKILL.md**
```markdown
---
name: regression-check
description: 전체 회귀 테스트 실행 후 실패 원인 분석 및 수정 방향 제시
tools: Bash, Read
---

# 회귀 테스트 체크

1. **테스트 실행**
   ```bash
   .venv/bin/pytest tests/ -q --tb=short 2>&1 | head -80
   ```

2. **실패 시 분석**
   - 실패한 테스트 파일을 Read
   - 관련 소스 파일 Read (에러 라인 기준 ±20줄)
   - 원인 분류: API 변경 / 로직 버그 / 테스트 코드 문제

3. **출력 형식**
   ```
   PASS: N tests
   FAIL: M tests
   
   실패 원인:
   - test_xxx: [원인] → [수정 방향]
   ```

4. **수정 제안만** — 직접 수정은 Human 확인 후 진행
```

**init-project-memory/SKILL.md**
```markdown
---
name: init-project-memory
description: 워크스페이스를 분석해 .agent-lab/PROJECT.md를 생성하거나 업데이트
tools: Read, Bash, Edit
---

# 프로젝트 메모리 초기화

대상: $ARGUMENTS (없으면 현재 디렉토리의 workspace_binding)

## 분석 단계

1. **프로젝트 파악**
   ```bash
   find $TARGET -maxdepth 2 \( -name "README.md" -o -name "package.json" \
     -o -name "pyproject.toml" -o -name "Makefile" \) 2>/dev/null | head -15
   ```

2. **핵심 파일 읽기** (3–5개)
   - README, 메인 진입점, 빌드 설정

3. **PROJECT.md 작성** — 아래 구조 엄수, 2000자 이내

## PROJECT.md 구조

```markdown
# 프로젝트 메모리 — {프로젝트명}

## 아키텍처 한 줄
{한 줄로 이 프로젝트가 뭔지}

## 핵심 모듈
- `파일경로` — 역할
(5개 이내)

## 빌드 & 실행
- {명령어} — {설명}

## 에이전트 주의사항
- {이 프로젝트에서 에이전트가 알아야 할 제약/금지사항}

## 현재 작업 맥락
(비워둠 — Human이 채움)
```

## 완료 기준
`.agent-lab/PROJECT.md` 파일이 존재하고 2000자 이내.
```

---

## 파일 4: PLATFORM.md (런타임 프로토콜)

### 역할

Agent Lab 런타임이 **모든 에이전트 payload**에 주입하는 플랫폼 수준 프로토콜.  
현재 `prompts.py`와 `room_context.py`에 하드코딩된 규칙을 외부화.

### 구현 연결

```python
# session_guidance.py:build_session_guidance_block() 에 추가
def _read_platform_md() -> str:
    path = Path(__file__).resolve().parents[2] / ".agent-lab" / "PLATFORM.md"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")[:1500]
```

### 내용 구성 (완성본)

```markdown
# Agent Lab 플랫폼 프로토콜

## Speech-act 봉투

발화마다 다음 act 중 하나를 사용:
- **PROPOSE** — 새 제안 (refs 선택)
- **AMEND** — 기존 제안 수정 (target refs 필수)
- **ENDORSE** — 동의 (body: "이의 없습니다" 한 줄)
- **CHALLENGE** — 반증 (refs 필수 — 무근거 CHALLENGE 금지)
- **BLOCK** — 실행 차단 (refs 필수 — plan_action:N 또는 task ID)
- **PASS** — 발언권 넘김 (이번 턴 추가할 것 없을 때)

ENDORSE/PASS는 짧게. CHALLENGE/BLOCK은 refs + 구체적 이유 필수.

## 역할 분담

| 에이전트 | 기본 역할 | R1 specialist | R2 specialist |
|----------|-----------|---------------|---------------|
| **Cursor** | 구현·패치·SDK 실행 | 대기 | 패치 적용 |
| **Codex** | 분해·검증·CLI 실행 | 분해·검증 계획 | 종료 |
| **Claude** | 리스크·반증·리뷰 | 리스크 분석 | 종료 |

## 완료 기준

"완료했습니다"는 에이전트의 주장. 완료는 다음이 충족될 때:
1. plan.md `검증:` 필드의 조건이 실제 파일/결과로 확인됨
2. Oracle (독립 에이전트)이 검증 기준 충족을 확인

→ 확인 없이 "PASS" 또는 "완료" 발화 금지.

## 금지 행동

- 동료 발언을 그대로 반복 (중복 발화)
- Human에게 에이전트끼리 해결 가능한 질문 던지기
- 근거 없는 BLOCK (refs 없으면 CHALLENGE로 전환)
- plan.md의 검증: 필드를 무시한 approve 요청
```

### 크기 목표

이 파일은 **모든 에이전트 모든 턴**에 주입됩니다.

| 모드 | 한도 | 비고 |
|------|------|------|
| **주입 hard cap** | 500자 | `session_guidance.py`에서 truncate |
| **전체 파일** | 1000자 | 인간 가독성 유지, truncate 최소화 |

위 완성본 예시는 전체 파일 형태(~900자)입니다. 실제 주입 시 500자 이내로 런타임이 truncate합니다.  
섹션 우선순위: Speech-act > 완료 기준 > 금지 행동 > 역할 분담 (긴 표는 마지막에).

---

## 파일 5: PROJECT.md (워크스페이스 영속 메모리)

### 역할

Agent Lab이 작업하는 외부 프로젝트(quant-pipeline, 교재 등)의 영속 기억.  
`session_guidance.py`에서 workspace_binding 경로의 `.agent-lab/PROJECT.md`를 읽어 주입.

### 섹션 설계 원칙

**세션마다 변하는 것** → plan.md  
**프로젝트 전체에서 변하지 않는 것** → PROJECT.md

```
PROJECT.md에 넣는 것:
  ✅ 아키텍처, 모듈 구조
  ✅ 도메인 용어 정의
  ✅ 절대 하면 안 되는 것 (브로커 API 호출, 프로덕션 DB 수정 등)
  ✅ 검증 기준 (어떤 파일이 있어야 완료인지)
  ✅ 현재 스프린트 목표 (Human이 채움)

PROJECT.md에 넣지 않는 것:
  ❌ 이번 세션의 합의 → plan.md
  ❌ 실행 액션 → plan.md ## 지금 실행
  ❌ 이슈 트래킹 → sessions/ 아카이브
```

### 완성 템플릿

```markdown
# 프로젝트 메모리 — {프로젝트명}
> 업데이트: {날짜}

## 아키텍처 한 줄
{이 프로젝트가 뭘 하는지 한 줄}

## 핵심 모듈
- `{경로}` — {역할} (에이전트 작업 시 가장 자주 건드는 파일 위주)
(최대 7개)

## 도메인 용어
- **{용어}**: {정의} (오해하기 쉬운 것만)

## 검증 기준 (공통)
- {이 프로젝트에서 "완료"를 확인하는 파일/지표}
- 예: `break-report.json` appliedBreaks 확인, OOS Sharpe > 0.5

## 절대 하면 안 되는 것
- {브로커 API 직접 호출 등 돌이킬 수 없는 행동}
- {금지된 파일 수정}

## 현재 작업 맥락
### 이번 스프린트
{Human이 채움}

### 최근 결정 (상위 3개)
- {날짜}: {결정 내용} (ref: sessions/{id}/plan.md)

### 미결 리스크
- {지금 진행하면 안 되는 이유가 있는 것}
```

### 크기 목표: 1500자 이내

`session_guidance.py`에서 1500자 cap으로 truncate.  
크면 "현재 작업 맥락" 섹션만 자주 업데이트하고 나머지는 stable하게 유지.

### 유지 관리

| 언제 업데이트 | 누가 | 내용 |
|-------------|------|------|
| 새 스프린트 시작 | Human | "현재 작업 맥락" 섹션 |
| 중요 결정 완료 | Human 또는 `/init-project-memory` | "최근 결정" 에 추가 |
| 모듈 구조 변경 | Human | "핵심 모듈" 업데이트 |
| 돌이킬 수 없는 실수 발생 | Human | "절대 하면 안 되는 것" 추가 |

---

## 파일 6: plan.md (세션 실행 계약)

### 역할 재정의

현재 plan.md는 5가지 역할을 동시에 합니다:
1. 세션 대화 요약 (Human 가독성)
2. 에이전트 다음 턴 컨텍스트 (agreed_bullets, open_bullets 추출)
3. execute gate 계약 (## 지금 실행 파싱)
4. provenance 앵커 (chat.jsonl#L 링크)
5. 합의 상태 표시 (미해결 이의, 에이전트별 기여)

이 역할들이 **섹션별로 분리**되어야 합니다.

### 섹션별 작성 규칙 (Scribe 프롬프트 확장)

#### § 지금 논의 중인 것 (Human 가독성)

```
규칙:
- 3문장 이내 산문 또는 불릿 3개 이하
- "~하는 중" 이 아닌 "~이 쟁점" 형태
- 이미 결론난 것은 여기 넣지 않음

Good: "R2 Cursor가 artifact만 보고 패치 제안할지, 여전히 full context를 볼지가 쟁점이다."
Bad:  "현재 Agent Lab의 Room 기능을 개선하고 있습니다. F2 비대칭 컨텍스트 구현 중..."
```

#### § 합의된 점 (컨텍스트 재주입용)

```
규칙:
- 불릿마다 (ref: chat.jsonl#Ln) 필수
- 동사로 시작: "~하기로 함", "~로 확정"
- 이미 실행 완료된 것: "~완료 (merged)"

Good: "execute 시 git worktree 격리가 기본값. approve = merge. (ref: chat.jsonl#L45)"
Bad:  "worktree에 대한 내용이 논의됐습니다. (ref: 불명확)"
```

#### § 쟁점 / 미결정 (에이전트 다음 턴 지시)

```
규칙:
- 불릿마다 "아직 결정 안 된 것 + 왜 미결인지" 포함
- 다음 턴에서 에이전트가 이 불릿을 보고 무엇을 해야 하는지 명확하게
- 완료되면 즉시 삭제 (plan.md는 살아있는 문서)

Good: "R2 Cursor context slimming: 실제 LLM이 artifact만 따르는지 검증 필요. Codex가 확인 예정."
Bad:  "F2 관련 이슈가 있음."
```

#### § 미해결 이의 (E1 execute gate 연동)

```
규칙:
- harvest_objections_from_turn()이 자동 생성 (Human 직접 작성 안 함)
- 포맷: "- **{에이전트}** · {act} → {target_ref}: {body_요약}"
- Human이 resolve하면 자동 제거됨

자동 생성 예:
- **claude** · BLOCK → plan_action:1: artifact에 없는 수치를 검증 기준으로 인용
```

#### § 지금 실행 (execute gate 파싱 대상)

```
규칙 — 3-필드 형식 엄수:
1.
   - 무엇을: {동사+대상 — "X파일의 Y함수에 Z를 추가"}
   - 어디서: `{절대 경로 또는 상대 경로만}` (함수명, 기능명 backtick 금지)
   - 검증: {통과 기준 — "N개 테스트 모두 통과", "`file.json` 생성됨"}
   (ref: chat.jsonl#Ln)

파싱 실패 케이스 (plan_actions.py가 executable=False로 처리):
  ❌  어디서: 백엔드 API 함수   ← 경로 아님
  ❌  검증: 잘 동작하면 됨      ← 기준 없음
  ✅  어디서: `src/agent_lab/plan_execute_merge.py`
  ✅  검증: `pytest tests/test_plan_execute.py -q` 통과
```

#### § 실행 순서 (이후) (로드맵)

```
규칙:
- 3-필드 완성 가능한 것만 번호 항목
- gate/조율/보류는 한 줄 설명으로
- 번호는 실행 우선순위 순서

Good:
2.
   - 무엇을: Oracle 검증 함수 추가
   - 어디서: `src/agent_lab/plan_execute_merge.py`
   - 검증: `pytest tests/test_oracle_verify.py` 통과
3. F2 R2 slimming은 #2 완료 후 착수. (ref: chat.jsonl#L89)
```

---

## 파일 7: AGENTS.md (워크스페이스, Codex 전용)

### 역할

Codex CLI가 워크스페이스에서 직접 읽는 파일.  
Claude Code는 읽지 않으므로 **Codex의 관점**으로 작성.

### Codex가 잘 따르는 포맷

Codex는 **실행·검증 중심**입니다. "왜"보다 "어떻게"를 더 잘 따릅니다.

```markdown
# {프로젝트명} — Codex 가이드

## 환경 설정
- Python: .venv/bin/python (또는 npm, cargo 등)
- 실행: {명령어}
- 테스트: {명령어}

## 작업 전 반드시 확인
1. {확인해야 할 것 1}
2. {확인해야 할 것 2}

## 파일 수정 시 규칙
- {어떤 파일} 수정 시 → {무엇을 함께 수정/확인}
- {어떤 함수} 변경 시 → {영향받는 테스트 파일 경로}

## 절대 하면 안 되는 것
- {금지 1}
- {금지 2}

## 자주 쓰는 검증 명령
```bash
# {목적}
{명령어}
```
```

### SHARED_CONTEXT.md 패턴 (고급)

CLAUDE.md와 AGENTS.md가 공통 내용을 공유할 때:

```markdown
# SHARED_CONTEXT.md (워크스페이스 공통)
## 아키텍처
...
## 공통 규칙
...
```

```markdown
# CLAUDE.md
@SHARED_CONTEXT.md

## Claude Code 전용
- plan 모드에서 변경 전 /plan으로 계획 먼저 확인
```

```markdown
# AGENTS.md
@SHARED_CONTEXT.md

## Codex CLI 전용
- 실행 전 반드시 테스트 명령 확인
- 검증 파일 경로를 --add-dir에 포함
```

---

## 전체 MD 체계 작성 순서 (실행 계획)

> 구현 추적: [EXTERNAL-REFS-TRACEABILITY.md §Dev-tool](EXTERNAL-REFS-TRACEABILITY.md)

### Dev-tool 레이어 (Agent Lab 개발 속도 향상)

| 순위 | 항목 | 상태 | TRACEABILITY ID |
|------|------|------|-----------------|
| **P0** | `CLAUDE.md` 작성 (60–80줄) | ⬜ 미작성 | CC-CLAUDE |
| **P0** | `.claude/settings.json` hooks | ⬜ 미작성 | CC-hooks |
| P1 | `.claude/rules/python-backend.md` | ⬜ | CC-rules |
| P1 | `.claude/rules/react-frontend.md` | ⬜ | CC-rules |
| P1 | `.claude/skills/smoke-and-score/` | ⬜ | CC-skills |
| P1 | `.claude/skills/regression-check/` | ⬜ | CC-skills |
| P2 | `.claude/skills/init-project-memory/` | ⬜ | CC-skills |

### 런타임 레이어 (Room/에이전트 품질 향상)

| 순위 | 항목 | 상태 | TRACEABILITY ID |
|------|------|------|-----------------|
| P1 | `.agent-lab/PLATFORM.md` + `session_guidance.py` 주입 | ⬜ | MD-PLATFORM |
| P2 | 워크스페이스 `.agent-lab/PROJECT.md` + 주입 | ⬜ | MD-PROJECT |
| P3 | 워크스페이스 `AGENTS.md` (Codex 전용) | ⬜ | — |
| P3 | `SHARED_CONTEXT.md` 패턴 | ⬜ | — |

### 우선순위 원칙

- **Dev-tool P0** (CLAUDE.md + hooks): 1시간, 즉시 개발 속도 향상. 런타임과 무관.  
- **런타임 P1** (PLATFORM.md): `prompts.py` 하드코딩 대체. 에이전트 프로토콜 adherence 향상.  
- **런타임 P2** (PROJECT.md): Human이 topic에 프로젝트 설명 반복 입력하는 마찰 제거.

---

## 파일별 크기 한도 요약

| 파일 | 한도 | 초과 시 조치 |
|------|------|-------------|
| `CLAUDE.md` | 80줄 | `.claude/rules/` 로 분산 |
| `.claude/rules/*.md` | 50줄 | 파일 분리 (주제별) |
| `SKILL.md` | 제한 없음 | on-demand 로드라 OK |
| `PLATFORM.md` | 파일 1000자 / 주입 500자 | 런타임이 500자 hard cap으로 truncate |
| `PROJECT.md` | 1500자 | "현재 작업 맥락"만 압축 |
| `plan.md` | 600단어 | Scribe가 자동 관리 |
| `MEMORY.md` | 200줄/25KB | Claude가 자동 분리 |

---

## 검증 체크리스트

작성 후 각 파일을 이 기준으로 검토:

```
□ 모든 규칙이 검증 가능한가? ("잘 써라" 같은 모호한 것 없는가)
□ 파일 간 충돌하는 규칙이 없는가?
□ 파일 크기가 한도 이내인가?
□ "항상 로드"해야 하는 것만 CLAUDE.md에 있는가?
□ 에이전트 관점에서 작성됐는가? (Human이 읽는 문서 아님)
□ import 사용 시 imported 파일도 한도 계산에 포함됐는가?
□ plan.md의 ## 지금 실행이 3-필드 형식이고 경로가 backtick으로 감싸졌는가?
□ PROJECT.md의 "현재 작업 맥락"이 최신인가?
```
