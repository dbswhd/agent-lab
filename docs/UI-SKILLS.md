# UI Agent Skills

Claude Code · Codex · Cursor에서 Agent Lab 프론트 UI 품질을 올리기 위한 skill 설치·사용 가이드.

## 한 번 설치 (repo root)

```bash
cd ~/Projects/agent-lab

# Core UI craft (Codex + Claude Code)
npx skills add emilkowalski/skills --skill emil-design-eng --skill review-animations -a claude-code -a codex -y
npx skills add ibelick/ui-skills --skill ui-skills-root --skill fixing-motion-performance -a claude-code -a codex -y
npx skills add anthropics/skills --skill frontend-design -a claude-code -a codex -y
npx skills add pbakaus/impeccable --skill impeccable -a claude-code -a codex -y
npx skills add addyosmani/agent-skills --skill frontend-ui-engineering -a claude-code -a codex -y
```

설치 위치: `.agents/skills/` (Claude Code는 `.claude/skills/` symlink).

**커밋 대상 아님** — clone 후 위 명령 재실행. 프로젝트 전용 skill만 git 추적: `.claude/skills/agent-lab-ui/`.

## 전역 설치 (모든 프로젝트)

`~/.agents/skills/` — Codex · Cursor · Claude Code 등에서 공통 사용.

```bash
# 한 번만 (이미 설치됨 — 2026-06-26)
npx skills add emilkowalski/skill --skill emil-design-eng --skill review-animations -g -y
npx skills add ibelick/ui-skills \
  --skill ui-skills-root --skill baseline-ui \
  --skill fixing-motion-performance --skill fixing-accessibility -g -y
npx skills add anthropics/skills --skill frontend-design -g -y
npx skills add pbakaus/impeccable --skill impeccable -g -y
npx skills add addyosmani/agent-skills --skill frontend-ui-engineering -g -y
npx skills add mblode/agent-skills --skill ui-animation -g -y
```

확인: `npx skills list -g`

| 전역 skill | 용도 |
|------------|------|
| `emil-design-eng` | polish · 모션 taste |
| `review-animations` | 모션 코드 리뷰 |
| `impeccable` | audit / polish / animate … |
| `frontend-design` | AI slop 방지 |
| `frontend-ui-engineering` | 컴포넌트 · a11y |
| `ui-skills-root` | skill 라우팅 |
| `baseline-ui` | spacing · hierarchy 빠른 정리 |
| `fixing-motion-performance` | jank · GPU |
| `fixing-accessibility` | WCAG · keyboard |
| `ui-animation` | CSS motion 규칙 |

`agent-lab-ui`는 **프로젝트 전용** — 전역 설치하지 않음.

## 프로젝트 skill (항상 추적)

| Skill | 경로 | 용도 |
|-------|------|------|
| `agent-lab-ui` | `.claude/skills/agent-lab-ui/` | tokens, IA, migration gaps, 검증 명령 |
| `smoke-and-score` | `.claude/skills/smoke-and-score/` | E2E smoke + KPI |
| `regression-check` | `.claude/skills/regression-check/` | pytest 회귀 |

## Impeccable 컨텍스트

- `PRODUCT.md` (repo root) — register, personality, anti-references
- `web/DESIGN.md` — color, type, motion, components
- `docs/DESIGN.md` → `web/DESIGN.md` symlink (context loader용)

첫 UI 작업 전 (Claude Code / Codex):

```text
/impeccable init   # PRODUCT.md·DESIGN.md 없을 때만
/impeccable polish WorkStatusBar
```

## 추천 워크플로

```text
1. /agent-lab-ui          # 또는 "web UI polish" — 프로젝트 규칙 로드
2. /impeccable polish …   # 또는 /emil-design-eng
3. /review-animations web/src/styles/plan-execute.css
4. cd web && npm run build && npx react-doctor . --verbose --diff
```

## skill 라우팅 (선택)

```bash
npx ui-skills start
```

에이전트에게: `Run npx ui-skills start to fix this panel motion.`

## 업데이트

```bash
npx skills update
npx skills check
```
