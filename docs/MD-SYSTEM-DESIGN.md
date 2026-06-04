# Agent Lab MD 체계 설계

> 작성: 2026-06-03  
> 목적: 주요 AI 도구의 MD 파일 체계 분석 → Agent Lab에 최적화된 MD 아키텍처 설계

> **Status (2026-06):** Agent Lab **repo** MD stack (CC-*, MD-PLATFORM/PROJECT/P3) **shipped** — [EXTERNAL-REFS-TRACEABILITY.md §Dev-tool](EXTERNAL-REFS-TRACEABILITY.md).  
> **How to write:** [MD-WRITING-PLAN.md](MD-WRITING-PLAN.md) is canonical when this map and that guide conflict.  
> **Remaining:** workspace-side two-channel sync (`SHARED_CONTEXT` + per-tool files) and Claude auto memory — outside this repo; see §Part 4.

---

## Part 1 — 레퍼런스 MD 파일 전체 조사

### 1.1 CLAUDE.md (Claude Code)

**출처:** Anthropic Claude Code 공식 문서  
**읽는 주체:** Claude Code (Claude 에이전트)

#### 파일 위치 계층 (로드 순서, 넓은 범위 → 좁은 범위)

| 범위 | 위치 | 공유 대상 |
|------|------|-----------|
| 조직 정책 (최우선) | `/Library/Application Support/ClaudeCode/CLAUDE.md` | 기기의 모든 사용자 |
| 사용자 전역 | `~/.claude/CLAUDE.md` | 본인의 모든 프로젝트 |
| 프로젝트 공유 | `./CLAUDE.md` 또는 `./.claude/CLAUDE.md` | 팀 (git 커밋) |
| 프로젝트 개인 | `./CLAUDE.local.md` | 본인만 (gitignore) |

- 상위 디렉토리 CLAUDE.md도 모두 로드 (현재 위치에서 루트까지 순회)
- 하위 디렉토리 CLAUDE.md는 해당 디렉토리 파일 작업 시 lazy 로드

#### 구조 및 작성 규칙

```markdown
# 프로젝트명

## 빌드 & 테스트
- npm run dev
- npm test

## 코드 규칙
- 2-space 인덴테이션
- ES modules 사용

## 금지사항
- main 브랜치 직접 push 금지
```

**핵심 규칙:**
- 200줄 이하 유지 권장 (초과 시 adherence 저하)
- `@path/to/file` 로 다른 파일 import 가능 (로드 시 전체 주입)
- `<!-- HTML 주석 -->` 은 컨텍스트에서 제거됨 (Human 주석 용도)
- 매 세션 시작 시 전체 로드 (context window 비용 고정)

#### 장단점

| 장점 | 단점 |
|------|------|
| 매 세션 자동 로드 | 길어지면 adherence 저하 |
| 팀 공유 (git) | 강제 실행 아님 (Hooks가 강제) |
| 계층 상속으로 monorepo 지원 | 모든 세션에 토큰 비용 고정 |
| HTML 주석으로 Human 노트 가능 | 조건부 로드 불가 (Rules로 분리해야) |

---

### 1.2 .claude/rules/*.md (Claude Code Path-scoped Rules)

**출처:** Claude Code 공식 문서  
**읽는 주체:** Claude Code

특정 파일 경로에만 적용되는 규칙. `paths` frontmatter로 조건부 로드.

```markdown
---
paths:
  - "src/api/**/*.ts"
  - "tests/**/*.test.ts"
---

# API 개발 규칙

- 모든 엔드포인트에 입력 검증 필수
- 표준 에러 포맷: { error, code }
```

**경로 패턴:** glob, brace expansion, 다중 패턴 지원  
**로드 시점:** Claude가 해당 경로 파일 읽을 때 (lazy)  
**사용자 전역 규칙:** `~/.claude/rules/` (모든 프로젝트 적용)

| 장점 | 단점 |
|------|------|
| 관련 파일 작업 시에만 로드 → 컨텍스트 절약 | paths 설정 오버헤드 |
| 모듈화 (파일별 1개 주제) | 파일 수 증가 |
| symlink로 프로젝트 간 공유 가능 | lazy 로드라 초기 세션엔 없음 |

---

### 1.3 SKILL.md (Claude Code Skills)

**출처:** Claude Code 공식 문서 (Agent Skills 오픈 스탠다드 기반)  
**읽는 주체:** Claude Code (on-demand)

CLAUDE.md와 달리 **on-demand**. `/skill-name`으로 호출하거나 Claude가 자동 판단 로드.

```markdown
---
name: deploy
description: 프로덕션 배포 체크리스트 실행
model: claude-sonnet-4-6
tools: Bash, Edit
context: fork          # 격리된 컨텍스트에서 실행 (subagent)
disable-model-invocation: false  # true면 Human만 호출 가능
---

# 배포 체크리스트

1. npm run build && npm test
2. git tag v{version}
3. gh release create
...
```

**위치 계층:**
```
~/.claude/skills/         → 사용자 전역
.claude/skills/           → 프로젝트 공유
.claude/commands/         → 레거시 (동일 기능, 호환 유지)
```

| 장점 | 단점 |
|------|------|
| 필요할 때만 로드 (컨텍스트 절약) | 호출 필요 (자동 아님) |
| `/name` 명시적 실행 | 설명이 모호하면 자동 발동 미스 |
| subagent 격리 실행 가능 | 파일 구조 학습 필요 |
| 오픈 스탠다드 (agentskills.io) | |

---

### 1.4 MEMORY.md + Auto Memory (Claude Code)

**출처:** Claude Code 공식 문서  
**읽는 주체:** Claude Code (자동 읽기/쓰기)

Human이 아닌 **Claude가 작성**하는 기억 파일.

```
~/.claude/projects/<git-repo>/memory/
├── MEMORY.md          # 인덱스 (200줄/25KB 제한, 매 세션 자동 로드)
├── debugging.md       # 디버깅 패턴 상세 (요청 시 로드)
├── api-conventions.md # API 결정사항 (요청 시 로드)
└── ...
```

- `MEMORY.md` 200줄 이상은 세션 시작 시 로드 안됨 (Claude가 on-demand로 읽음)
- 토픽 파일들은 세션 시작 시 로드 안됨, Claude가 필요시 읽음
- git 저장소 기준 → 모든 worktree가 동일 memory 공유

| 장점 | 단점 |
|------|------|
| Human 작업 없이 자동 축적 | Claude가 쓰는 내용 제어 어려움 |
| 프로젝트 전반에 걸친 패턴 학습 | 기계 내부에만 존재 (팀 공유 불가) |
| 자연어로 "기억해줘" 가능 | 25KB 상한 후 세부 내용 접근 수동 |
| CLAUDE.md와 분리 (오염 방지) | |

---

### 1.5 AGENTS.md (Codex CLI / Google Gemini CLI / 다양한 AI 도구)

**출처:** OpenAI Codex CLI, Google Gemini CLI, LazyCodex/OmO  
**읽는 주체:** Codex CLI, Gemini, LazyCodex — **Claude Code는 읽지 않음**

> **중요:** Claude Code 공식 문서 명시 — "Claude Code reads CLAUDE.md, not AGENTS.md."  
> 이미 AGENTS.md가 있는 저장소라면 CLAUDE.md에서 `@AGENTS.md`로 import하거나 symlink 사용.

**계층 구조 (per-directory):**
```
project-root/
├── AGENTS.md              ← 전체 프로젝트 규칙
├── src/
│   └── AGENTS.md          ← src/ 전용 규칙 (상위 + 추가)
├── tests/
│   └── AGENTS.md          ← 테스트 전용 규칙
└── api/
    └── AGENTS.md          ← API 전용 규칙
```

에이전트는 작업 디렉토리에서 루트까지 모든 AGENTS.md를 읽고 합성.

**LazyCodex `/init-deep` 생성 예시:**
```markdown
# Project Context

## Architecture
Single-page app, React 18, TypeScript strict mode

## Key Modules
- src/api/ — REST handlers (Express)
- src/models/ — TypeORM entities
- src/services/ — Business logic

## Rules
- Never import from ../models directly in handlers
- All DB calls must be wrapped in try-catch

## Test Conventions
- Jest, co-located tests (`*.test.ts`)
```

| 장점 | 단점 |
|------|------|
| 여러 AI 도구가 공통으로 읽음 | Claude Code는 직접 읽지 않음 |
| 계층형 (디렉토리별 세분화) | 도구마다 해석 방식 차이 |
| LazyCodex /init-deep 자동 생성 | 단일 파일이 커질 수 있음 |
| 오픈 컨벤션 | 공식 표준화 미흡 |

---

### 1.6 .cursorrules / .cursor/rules/*.md (Cursor IDE)

**출처:** Cursor IDE  
**읽는 주체:** Cursor AI

```
.cursorrules          → 전역 단일 파일 (레거시, 하위 호환)
.cursor/
└── rules/
    ├── global.md     → 항상 적용
    ├── frontend.md   → paths: src/components/**
    └── testing.md    → paths: tests/**
```

Claude Code의 `.claude/rules/`와 동일한 패턴. frontmatter로 path 스코핑.

| 장점 | 단점 |
|------|------|
| IDE 통합 (자동 적용) | Cursor 전용 |
| path 스코핑 지원 | 다른 AI 도구와 공유 안됨 |
| .cursorrules 레거시 호환 | 조직 수준 정책 없음 |

---

### 1.7 .windsurfrules / .github/copilot-instructions.md (기타)

| 파일 | 도구 | 특징 |
|------|------|------|
| `.windsurfrules` | Windsurf IDE | .cursorrules와 거의 동일 구조 |
| `.github/copilot-instructions.md` | GitHub Copilot | 저장소 전체 Copilot 지침 |
| `GEMINI.md` | Google Gemini CLI | AGENTS.md와 유사 컨벤션 |
| `llms.txt` | 웹사이트 | LLM이 사이트 탐색 시 읽는 인덱스 |

---

### 1.8 plan.md, RECIPE.md (Agent Lab 현재)

**Agent Lab 고유 파일들:**

| 파일 | 위치 | 역할 | 읽는 주체 |
|------|------|------|-----------|
| `plan.md` | `sessions/{id}/plan.md` | 합의 요약 + execute 계약 + provenance | 에이전트, Human, execute gate |
| `RECIPE.md` | `workspace_root/RECIPE.md` | 빌드 INPUT→OUTPUT→검증 황금 경로 | 에이전트 (session_guidance 주입) |
| `chat.jsonl` | `sessions/{id}/` | 원문 대화 기록 | plan 합성, 검색 |
| `run.json` | `sessions/{id}/` | 실행 메타 (run_schema, turns, steps) | 서버, Oracle |
| `meta.json` | `sessions/{id}/` | 세션 메타 (topic, agents, timestamp) | UI, 세션 목록 |

---

## Part 2 — 도구별 MD 체계 비교

### 핵심 비교 매트릭스

| 파일 | 도구 | 로드 시점 | 작성자 | 범위 | 계층 | 강제성 |
|------|------|-----------|--------|------|------|--------|
| `CLAUDE.md` | Claude Code | 매 세션 | Human | 조직/유저/프로젝트/로컬 | ✅ 4계층 | 소프트 (Hooks가 강제) |
| `.claude/rules/` | Claude Code | 파일 접근 시 | Human | 프로젝트/유저 | path-scoped | 소프트 |
| `SKILL.md` | Claude Code | on-demand | Human | 유저/프로젝트 | 이름 우선순위 | 소프트 (호출 시) |
| `MEMORY.md` | Claude Code | 매 세션 (200줄) | Claude | 저장소 | 단일 (index+topics) | 없음 |
| `AGENTS.md` | Codex/Gemini/LazyCodex | 매 세션 | Human | 디렉토리 계층 | ✅ 디렉토리별 | 소프트 |
| `.cursorrules` | Cursor | 매 세션 | Human | 프로젝트 | 단일 파일 | IDE 통합 |
| `.cursor/rules/` | Cursor | path 매칭 시 | Human | 프로젝트 | path-scoped | IDE 통합 |
| `plan.md` | Agent Lab | 에이전트 페이로드 | Scribe (Claude) | 세션 | 세션 단위 | execute gate 하드 |
| `RECIPE.md` | Agent Lab | workspace 바인딩 시 | Human | workspace | workspace 단위 | 소프트 |

### 도구별 철학 차이

```
Claude Code:  "지속 맥락은 CLAUDE.md, 재사용 워크플로는 SKILL.md, 
               강제 실행은 Hooks, 기억은 Claude가 쌓음"

Codex CLI:    "디렉토리 계층형 AGENTS.md — 작업 폴더가 가까울수록 우선"

LazyCodex:    "프로젝트 전체 분석 후 AGENTS.md 자동 생성 (/init-deep)"

Cursor:       "IDE 통합 — 파일 열면 자동 적용, path-scoped 지원"

Agent Lab:    "세션 단위 plan.md = 메모리 + 실행 계약 (현재)"
              → "워크스페이스 단위 영속 메모리 필요 (목표)"
```

---

## Part 3 — Agent Lab에 최적화된 MD 체계

### 3.1 설계 원칙

Agent Lab은 일반 코드 에디터가 아닌 **3-에이전트 룸 오케스트레이터**입니다.

이 차이가 MD 체계 설계에 결정적입니다:

```
일반 에디터:  Human ↔ 에이전트 1:1 (CLAUDE.md 하나면 충분)

Agent Lab:   Human → Room (Cursor + Codex + Claude 동시)
             각 에이전트가 읽는 파일이 다르다
             세션이 워크스페이스에 바인딩된다
             plan.md가 실행 엔진의 상태다
```

**3가지 설계 원칙:**
1. **에이전트별 분리** — Claude Code용 CLAUDE.md ≠ Codex용 AGENTS.md
2. **레이어 분리** — 개발 도구 레이어 ≠ 런타임 세션 레이어 ≠ 워크스페이스 레이어
3. **한 파일 한 역할** — 세션 기억(plan.md)과 프로젝트 기억(PROJECT.md)은 섞지 않음

### 3.2 전체 MD 파일 맵

```
Agent Lab 전체 파일 구조
─────────────────────────────────────────────────────────

[Layer 0 — Agent Lab 플랫폼 개발 도구]
agent-lab/
├── CLAUDE.md                  ← Claude Code가 읽음 (플랫폼 개발 지침)
├── CLAUDE.local.md            ← 개인 개발 환경 (gitignore)
└── .claude/
    ├── rules/
    │   ├── python-backend.md  ← paths: src/agent_lab/**/*.py
    │   └── react-frontend.md  ← paths: web/src/**/*.tsx
    ├── skills/
    │   ├── smoke-and-score/SKILL.md
    │   ├── regression-check/SKILL.md
    │   └── init-project-memory/SKILL.md
    └── settings.json          ← hooks (PostEdit ruff, Stop pytest)

─────────────────────────────────────────────────────────

[Layer 1 — Agent Lab 런타임 설정]
agent-lab/
└── .agent-lab/
    ├── hooks.toml             ← 이미 있음 (pre_execute 등)
    └── PLATFORM.md            ← Agent Lab 런타임이 읽음 (신규)
                                  (에이전트에게 주입하는 플랫폼 규칙)

─────────────────────────────────────────────────────────

[Layer 2 — 워크스페이스 (Agent Lab이 작업하는 프로젝트)]
~/Desktop/pipeline/           ← 예: quant-pipeline
├── AGENTS.md                 ← Codex CLI가 읽음
├── .cursor/rules/            ← Cursor가 읽음
└── .agent-lab/
    └── PROJECT.md            ← Agent Lab 런타임이 읽음 (신규)
                                  (에이전트에게 주입하는 프로젝트 기억)

─────────────────────────────────────────────────────────

[Layer 3 — 세션 런타임 (실시간 상태)]
sessions/{id}/
├── chat.jsonl                ← 원문 대화
├── plan.md                   ← 합의 + execute 계약 + provenance
├── run.json                  ← 실행 메타 (steps, oracle, objections)
├── meta.json                 ← 세션 메타
└── attachments/              ← 첨부 파일
```

---

### 3.3 각 파일 상세 설계

#### CLAUDE.md (Layer 0 — 개발 도구)

**역할:** Agent Lab 플랫폼 개발 시 Claude Code가 읽는 지침  
**작성자:** 개발팀 (git 커밋)  
**로드 시점:** Claude Code 매 세션

```markdown
# Agent Lab 개발 가이드

## 빌드 & 실행
- make dev         — API(8765) + web(5173) 동시
- make test        — pytest (see `make ci`)
- make smoke       — mock 스모크
- make smoke-e2e   — E2E (MOCK_AGENTS=1)
- make score-session SESSION=sessions/<id>

## 핵심 모듈
- room.py (2600줄) — 멀티에이전트 오케스트레이션
- plan_execute*.py — execute gate + worktree + merge
- room_objections.py — BLOCK → execute 409
- cli_retry.py — CLI retry (429/timeout)
- app/server/main.py + app/server/routers/* (ops-P2 split)

## 코드 규칙
- from __future__ import annotations 필수
- 새 라우터: routers/ 폴더에 (main.py 직접 추가 금지)
- 테스트: mock-only (AGENT_LAB_MOCK_AGENTS=1)
- sessions/* 커밋 금지 (_regression/ 제외)

## 아키텍처 불변 원칙
- 합의=Room · 격리=worktree · 완료=Oracle verified
- BLOCK → execute 409 (plan 모드 한정)
- plan.md = 세션 메모리 + execute 계약 + provenance
- Human gate는 설계상 유지 (자율 실행 배제)
```

**크기 목표:** 60–80줄 (나머지는 Rules로 분산)

#### .claude/rules/ (Layer 0 — 경로별 규칙)

```markdown
# .claude/rules/python-backend.md
---
paths:
  - "src/agent_lab/**/*.py"
  - "app/**/*.py"
---

# Python 백엔드 규칙
- type hint 필수, from __future__ import annotations
- dataclass 우선 (dict 직접 return 지양)
- 에러: RuntimeError보다 도메인별 Exception 서브클래스
- patch_run_meta()로 run.json 수정 (직접 json.dump 금지)
```

```markdown
# .claude/rules/react-frontend.md
---
paths:
  - "web/src/**/*.tsx"
  - "web/src/**/*.ts"
---

# React 프론트엔드 규칙
- SSE 스트림: useRoomStream 훅 사용
- API 호출: web/src/api/client.ts 함수만 사용
- 새 컴포넌트: web/src/components/ 에 추가
- 스타일: CSS Modules 또는 인라인 (Tailwind 사용 안 함)
```

#### SKILL.md — 반복 워크플로 (Layer 0)

```markdown
# .claude/skills/smoke-and-score/SKILL.md
---
name: smoke-and-score
description: 스모크 테스트 후 최근 세션 품질 KPI 리포트
tools: Bash
---
1. AGENT_LAB_MOCK_AGENTS=1 .venv/bin/python scripts/smoke_room_e2e.py
2. LATEST=$(ls -t sessions | grep -v _regression | head -1)
3. make score-session SESSION=sessions/$LATEST
4. 결과 요약 (objection 해결률, execute retry율, ref 유효율)
```

```markdown
# .claude/skills/regression-check/SKILL.md
---
name: regression-check
description: 회귀 테스트 전체 실행 후 실패 원인 분석 및 수정 제안
tools: Bash, Read
---
1. .venv/bin/pytest tests/ -q --tb=short 2>&1 | head -50
2. 실패 테스트 파일 Read
3. 원인 분석 → 수정 제안 (코드 직접 수정은 확인 후)
```

```markdown
# .claude/skills/init-project-memory/SKILL.md
---
name: init-project-memory
description: 워크스페이스 분석 후 .agent-lab/PROJECT.md 생성
tools: Read, Bash, Edit
---
대상 워크스페이스: $ARGUMENTS (없으면 현재 디렉토리)

1. find $TARGET -maxdepth 2 -name "*.md" -o -name "package.json" -o -name "pyproject.toml" | head -20
2. 핵심 파일 3-5개 Read (README, main entry, config)
3. .agent-lab/PROJECT.md 작성:
   - 아키텍처 한 줄
   - 핵심 모듈 (파일 → 역할)
   - 빌드/실행 명령어
   - 에이전트 주의사항
   - 현재 작업 맥락 (비워둠)
4. 2000자 이하 유지
```

---

#### PLATFORM.md (Layer 1 — Agent Lab 런타임 규칙)

**역할:** Agent Lab 런타임이 에이전트 payload에 주입하는 플랫폼 수준 규칙  
**위치:** `agent-lab/.agent-lab/PLATFORM.md`  
**읽는 주체:** Agent Lab 런타임 → 에이전트 payload에 주입  
**작성자:** 개발팀 (플랫폼 업그레이드 시 수정)

```markdown
# Agent Lab 플랫폼 규칙

## Speech-act 프로토콜
- PROPOSE: 새 제안
- AMEND: 기존 제안 수정
- ENDORSE: 동의
- CHALLENGE: 반증 (ref 필수)
- BLOCK: 실행 차단 (ref 필수)
- PASS: 발언권 넘김

## 검증 기준
- "완료"를 주장하기 전에 실제 파일/결과로 확인
- plan.md의 `검증:` 필드 기준이 충족돼야 PASS

## 금지
- 에이전트끼리 서로의 발언 그대로 반복 (중복 발화)
- 근거 없는 BLOCK (refs 없으면 소프트 CHALLENGE로)
```

현재 `prompts.py`의 ROOM_SCRIBE, CLAUDE_ROOM 등에 하드코딩된 내용을 파일로 외부화.

---

#### PROJECT.md (Layer 2 — 워크스페이스 영속 메모리)

**역할:** Agent Lab이 작업하는 프로젝트의 영속 기억  
**위치:** `{workspace_root}/.agent-lab/PROJECT.md`  
**읽는 주체:** Agent Lab 런타임 → `build_session_guidance_block()`에서 주입  
**작성자:** Human 직접 또는 `/init-project-memory` skill 자동 생성

```markdown
# 프로젝트 메모리 — quant-pipeline

## 아키텍처 한 줄
한국 퀀트 전략 백테스팅 + 자동 실행 파이프라인

## 핵심 모듈
- research/kr/ — 한국 전략 연구
- research/cross_asset/ — 크로스 에셋 오버레이
- overlay_corr_*.json — 상관관계 검증 canonical

## 검증 기준 (공통)
- OOS PASS: IS 필터 통과 + OOS Sharpe > 0.5
- break-report.json appliedBreaks 확인 필수

## 에이전트 주의사항
- 실거래 코드 수정 금지 (연구/검증만)
- .env에 브로커 API 키 있음 — 절대 노출 금지
- 1105× ratio는 철회됨 (2026-06-02 결정)

## 현재 작업 맥락
(Human이 채움 — 이번 스프린트 목표 등)
```

**PROJECT.md vs plan.md 차이:**

| | PROJECT.md | plan.md |
|-|-----------|---------|
| 범위 | 워크스페이스 전체 | 세션 단위 |
| 지속성 | 영속 (Human 관리) | 세션 종료 후 아카이브 |
| 작성자 | Human + init-project-memory skill | Scribe (Claude) 자동 합성 |
| 내용 | 프로젝트 배경, 모듈, 제약 | 합의, 미결, 실행 액션 |
| execute gate | ❌ 없음 | ✅ ## 지금 실행 파싱 |

---

#### plan.md (Layer 3 — 세션 실행 계약) — 현재 구조 유지

역할이 명확하고 이미 잘 설계돼 있습니다.

```markdown
## 지금 논의 중인 것
(세션 토픽, 현재 상태)

## 합의된 점
- bullet (ref: chat.jsonl#Ln)

## 쟁점 / 미결정
- bullet (ref: chat.jsonl#Ln)

## 에이전트별 핵심
**Cursor:** ...
**Codex:** ...
**Claude:** ...

## 미해결 이의                    ← E1/E2 (이미 구현)
- claude · BLOCK → plan_action:1: 근거 없는 수치

## 에이전트별 기여 (자동)          ← H1 (이미 구현)
- codex: PROPOSE 2건, AMEND 1건

## 지금 실행                       ← execute gate 파싱 대상
1.
   - 무엇을: ...
   - 어디서: ...
   - 검증: ...

## 실행 순서 (이후)
1. ...
```

---

### 3.4 에이전트별 MD 읽기 매핑

**Agent Lab의 3 에이전트가 각각 읽는 파일:**

```
Cursor (SDK 에이전트)
  ├─ .cursor/rules/        ← IDE에서 직접 읽음
  └─ Agent Lab payload     ← PLATFORM.md + PROJECT.md + plan.md 주입됨

Codex CLI
  ├─ AGENTS.md             ← Codex가 직접 읽음 (워크스페이스 디렉토리 계층)
  └─ Agent Lab payload     ← PLATFORM.md + PROJECT.md + plan.md 주입됨

Claude Code / claude -p
  ├─ CLAUDE.md             ← Claude Code가 직접 읽음
  └─ Agent Lab payload     ← PLATFORM.md + PROJECT.md + plan.md 주입됨
```

**핵심 통찰:** 각 에이전트에게 "두 채널"이 있습니다.
1. **직접 채널** — 에이전트 CLI가 자기 파일을 읽음 (CLAUDE.md, AGENTS.md, .cursor/rules)
2. **Agent Lab 채널** — Agent Lab 런타임이 context_bundle로 주입 (PLATFORM.md, PROJECT.md, plan.md)

이 두 채널을 일치시키는 것이 체계의 핵심입니다.

**공유 컨텍스트 파일 (모든 에이전트에게 동일하게 보임):**
```
{workspace_root}/SHARED_CONTEXT.md   ← 선택적 도입
```
CLAUDE.md에서 `@SHARED_CONTEXT.md`, AGENTS.md에서도 `@SHARED_CONTEXT.md` import.  
공통 프로젝트 규칙을 한 파일에 유지하면서 각 에이전트의 고유 파일에도 추가 지침.

---

### 3.5 실제 저장소 구조 (Agent Lab이 작업하는 프로젝트 예시)

```
~/Desktop/pipeline/              ← quant-pipeline (워크스페이스)
├── SHARED_CONTEXT.md            ← 에이전트 공통 규칙 (선택)
├── AGENTS.md                    ← @SHARED_CONTEXT.md + Codex 전용
├── CLAUDE.md                    ← @SHARED_CONTEXT.md + Claude 전용
├── .cursor/
│   └── rules/
│       └── quant.md             ← paths: research/**
└── .agent-lab/
    ├── PROJECT.md               ← Agent Lab 런타임 주입용
    └── hooks.toml               ← pre_execute 등
```

---

## Part 4 — 구현 로드맵

### Agent Lab repo — ✅ shipped (2026-06)

| # | 항목 | TRACEABILITY |
|---|------|----------------|
| 1 | `CLAUDE.md` | CC-CLAUDE |
| 2 | `.claude/settings.json` hooks | CC-hooks |
| 3 | `.claude/rules/*.md` | CC-rules |
| 4 | `.claude/skills/smoke-and-score`, `regression-check` | CC-skills |
| 5 | `.agent-lab/PLATFORM.md` + injection | MD-PLATFORM |
| 6 | `.agent-lab/PROJECT.md` injection | MD-PROJECT |
| 7 | `.claude/skills/init-project-memory` | CC-skills |
| 8 | workspace `PROJECT.md` bootstrap | `scripts/init_project_memory.py`, `project_memory.py` |

### 워크스페이스 연동 (장기 — 대상 repo에서 Human/스크립트)

| # | 항목 | 상태 |
|---|------|------|
| 9 | `AGENTS.md` ↔ `CLAUDE.md` + `SHARED_CONTEXT.md` two-channel align | ⬜ per workspace — runtime inject ✅ (MD-P3); CLI `@import` sync는 워크스페이스 작업 |
| 10 | Claude Code auto memory (`MEMORY.md`) | ⬜ 제품 기능 — Agent Lab 티켓 없음 |

---

## 요약표

| 파일 | 레이어 | 읽는 주체 | 내용 | 지속성 | Status |
|------|--------|-----------|------|--------|--------|
| `CLAUDE.md` | 개발 도구 | Claude Code | 플랫폼 개발 지침 | 영속 (git) | ✅ CC-CLAUDE |
| `.claude/rules/` | 개발 도구 | Claude Code | 경로별 규칙 | 영속 (git) | ✅ CC-rules |
| `SKILL.md` | 개발 도구 | Claude Code | 반복 워크플로 | 영속 (git) | ✅ CC-skills |
| `MEMORY.md` | 개발 도구 | Claude Code (자동) | 학습된 패턴 | 로컬 축적 | ⬜ 제품 (repo 밖) |
| `.agent-lab/PLATFORM.md` | 런타임 | Agent Lab → 3 에이전트 | 프로토콜 규칙 | 영속 (git) | ✅ MD-PLATFORM |
| `.agent-lab/PROJECT.md` | 워크스페이스 | Agent Lab → 3 에이전트 | 프로젝트 기억 | 영속 (워크스페이스) | ✅ MD-PROJECT |
| `plan.md` | 세션 | Scribe + execute gate | 합의 + 실행 계약 | 세션 단위 | ✅ 현재 |
| `AGENTS.md` | 워크스페이스 | Codex CLI (직접) | Codex 전용 규칙 | 영속 (워크스페이스) | ✅ MD-P3 inject + workspace bootstrap |
| `SHARED_CONTEXT.md` | 워크스페이스 | CLAUDE.md + AGENTS.md import | 에이전트 공통 | 영속 (워크스페이스) | ✅ MD-P3 inject; `@import` sync ⬜ workspace |
