# Codex Handoff — IDE 기능 구현 (UI Tier 3 CSS 수렴)

> **작성:** 2026-06-13  
> **대상:** Codex (다음 구현 담당)  
> **워크스페이스:** `/Users/yoonjong/Projects/agent-lab`  
> **범위:** `Remove orphaned developer-console.css / app.css` — UI Tier 3 CSS 스택 수렴  
> **상태 SSOT:** 이 문서 + `web/src/main.tsx` + `git diff web/src/styles/`

---

## 1. 목적

Agent Lab 웹 UI는 2026-06-07부터 **프로토타입 디자인 스택**(`tokens → base → layout → …`)으로 전환되었습니다. 그러나 구 레거시 체인(`app.css` → `developer-console.css` → `workspace-shell.css` → …)이 디스크에 orphan으로 남아 있었고, 일부 규칙은 `satellites.css`에 추출만 된 채 **번들에 로드되지 않는** 상태였습니다.

**이 워크스트림의 목표:**

1. `main.tsx`에서 로드하지 않는 CSS 파일을 디스크에서 제거
2. 여전히 필요한 selector/미디어쿼리는 **현행 로드 스택**(`layout.css`, `overlays.css`, `surfaces.css` 등)으로 이전
3. CSS contract 테스트·빌드 green
4. `AGENTS.md` / `UI-IA-ROADMAP.md` / `UI-MIGRATION-GAPS.md`와 코드 일치

**범위 밖 (같은 워킹 트리에 섞여 있으나 이 handoff의 1차 목표 아님):** workspace files API/UI, hooks/response contracts, dogfood suite, LiveAgentsStrip 백엔드 연동 등 — §4 참고.

---

## 2. 세션 타임라인

| 순서 | 세션 | 역할 |
|------|------|------|
| 1 | [Developer Console 피벗](805125ba-5bc4-499d-b224-381fa5523910) | `developer-console.css` 생성, `app.css` import 체인, macOS 26 / workspace-shell UI |
| 2 | [프로토타입 UI 이식](4be93290-a455-4863-9185-273fe1d80331) | `main.tsx` 신규 CSS 스택 전환; `satellites.css`에 구 스택 위성 규칙 197블록 추출; orphan 파일은 디스크에 유지 |
| 3 | [Tier 3 백로그·doc-sync](647d26e7-6dad-4fc8-b4ae-1e0c22ce4c34) | Overview/context layer shipped 확인; doc-sync 커밋 `ec0a607`; **E 스프린트** classic 폐기 + `legacy-bridge.css` → `layout.css` merge 커밋 `ebde1a7` |
| 4 | [IDE 기능 구현 (CSS handoff)](84cdc1b8-24a5-4425-a45c-b2c5760b97f6) | orphan CSS 진행 상황 조사 → handoff 초안 → 사용자 요청으로 마무리 착수 → **중단 후** 백그라운드 subagent 위임 |
| 5 | Subagent [CSS cleanup 마무리](7f2c5866-3b18-4cfc-b132-1b5b2d32310f) | ✅ **완료** — orphan 5파일 삭제, `layout.css` 포팅, 테스트·문서 동기화, build + 34 contract tests green (미커밋) |

**관련 but 별도 세션 (같은 “IDE/console” 맥락):**

| 세션 | 내용 |
|------|------|
| [LiveAgentsStrip·running UX](ee848089-5a9c-4da5-af71-f271ed8739e5) | `LiveAgentsStrip.tsx`, `runningAgents.ts` — CSS는 `layout.css`로 포팅 완료 (subagent `7f2c5866`) |
| [Workspace Files Phase 1 리뷰](81bb956e-7c8a-426c-a75f-8b71192b304f) | `workspace_files.py` / Files 탭 설계 승인 — 구현은 untracked |

---

## 3. 대화에서 나온 결정/합의

### UI Tier 3 전반 (647d26e7)

- 백엔드 기능 큐는 소진; 잔량은 **live dogfood · Human Inbox · UI Tier 3 수렴** 축.
- Overview / Tasks / Inbox / context layer toggle은 **이미 shipped** — stale 문서(2026-06-07)를 믿지 말 것.
- UI Tier 3 E = **classic 폐기 + legacy-bridge merge** (완료, `ebde1a7`). orphan CSS 파일 삭제는 로드맵 잔량.
- CSS-only 변경은 **dogfood/Inbox와 분리 PR** 권장.

### 프로토타입 마이그레이션 (4be93290)

- 로직·API 불변, **프레젠테이션만** 프로토타입 IA/클래스에 맞춤.
- `satellites.css` = 구 `app.css` 스택에서 위성 컴포넌트 규칙 추출용 **과도기 파일** (최종 목표: canonical CSS로 흡수 후 삭제).
- dual-class bridge (`taskbar` + `room-task-bar` 등)는 cosmetic rename 완료 후 한 벌만 유지.

### IDE 기능 구현 세션 (84cdc1b8)

- `"Remove orphaned developer-console.css / app.css"` 타이틀의 **완료된 별도 세션은 transcripts에 없음**.
- 실제 파일 삭제는 **미커밋 워킹 트리**에만 존재 (~90% 진행).
- `satellites.css` **미로드** 상태에서 위성 UI 스타일 누락 가능 — 단기 import 추가 vs 규칙 이전 후 삭제 **택일**했으나, 후속 조사에서 **대부분 이미 `layout.css`/`overlays.css`에 canonical 클래스로 존재**함을 확인. `satellites.css` unique root class ~0에 가깝다는 분석이 있었음.
- **`--console-*` 토큰**은 `tokens.css`에 없음; `satellites.css`·`workspace-shell.css`만 참조 (둘 다 미로드).
- 사용자: *「이거 너가 맡아서 진행해줘」* → 구현 착수 후 interrupt → subagent `7f2c5866`에 위임.

---

## 4. 완료됨 / 진행 중 / 미착수

### ✅ 완료 (커밋됨, HEAD `ebde1a7` 기준)

| 항목 | 근거 |
|------|------|
| `main.tsx` 신규 스택 | `tokens → base → layout → surfaces → plan-execute → overlays → tweaks → prototype-panels` — `app.css` import 없음 |
| classic 모드 제거 | `App.tsx` `mode: "classic"` 분기 삭제 (`ebde1a7`) |
| `legacy-bridge.css` 삭제·병합 | `layout.css` 하단 `/* === Merged from legacy-bridge.css === */` |
| Inspector Overview/Tasks/Inbox | `workspaceTabs.ts`, `ContextOverviewPanel.tsx`, contract tests |
| doc-sync (Tier 3 shipped 반영) | `ec0a607` — `UI-MIGRATION-GAPS.md`, `UI-IA-ROADMAP.md` 등 |

### ✅ 완료 (미커밋 워킹 트리 — subagent `7f2c5866`)

| 항목 | 근거 |
|------|------|
| **`app.css` / `developer-console.css` 삭제** | `git status`: `D` — 이미 삭제됨 (선행 세션) |
| **Orphan CSS 5파일 삭제** | `satellites.css`, `layout-extensions.css`, `content-surfaces.css`, `workspace-shell.css`, `chrome.css` — 디스크에서 제거됨 |
| **`layout.css` 포팅** | `live-agents-strip*`, `notification-center__item|__body|__time`, `room-task-bar` `@media (max-width: 1000px)` |
| **`tokens.css` / `base.css` 소폭 수정** | design token 정리 |
| **Contract 테스트 수정·green** | `test_room_ui_p2_contract.py` → `layout.css`; `test_workspace_ui_contract.py` 동기화 — **34건 pass** |
| **`npm run build`** | green |
| **`web/src/AGENTS.md`** | `main.tsx` 로드 순서 기준 스택 목록 반영 |
| **`docs/UI-IA-ROADMAP.md` §1.1** | orphan 삭제 완료 반영 |
| **`docs/UI-MIGRATION-GAPS.md` §1** | `satellites.css` / `layout-extensions.css` shipped 표기 제거, 현행 스택 일치 |
| **`docs/developer-agent-console.md`** | 토큰 SSOT `tokens.css`, `--console-*` dead code, `workspace-shell.css` 삭제 반영 |

### 🔄 진행 중 / 잔여 (Codex)

| 항목 | 상태 |
|------|------|
| **커밋 / PR** | CSS-only diff 준비 완료; workspace files·hooks·dogfood 등 **대규모 미커밋 diff와 혼재** — 분리 커밋 필요 |
| **`macos26.css` (선택)** | Figma reference only (`web/src/figma/macos26-library.json`); `main.tsx`·tests 미참조 — 삭제 또는 `figma/` 이동 검토 가능 |

### ❌ 미착수 (이 handoff 범위 밖 또는 후속)

### ⚠️ 같은 워킹 트리, 별도 workstream (Codex가 scope 분리 필요)

| 변경 | 파일 예시 |
|------|-----------|
| Workspace Files Phase 1 | `app/server/routers/workspace_files.py`, `WorkspaceFilesPanel.tsx`, `FilePreview.tsx` (untracked) |
| Live agents UX | `LiveAgentsStrip.tsx`, `web/src/run/runningAgents.ts` |
| Hooks / response contracts | `response_contracts.py`, `HooksResponseSettings.tsx` |
| Eval / dogfood | `scripts/run_dogfood_suite.py`, `docs/EVAL-PROGRAM.md` |

---

## 5. Codex 액션 아이템

**Subagent `7f2c5866`가 §5.1–5.5를 완료했습니다. Codex 잔여 작업은 커밋/PR과 선택적 `macos26.css` 정리뿐.**

### ✅ 완료됨 (subagent `7f2c5866`)

| 섹션 | 내용 |
|------|------|
| **5.1 검증 게이트** | `npm run build` pass; CSS contract 34건 pass |
| **5.2 `layout.css` 포팅** | `live-agents-strip*`, `room-task-bar` `@media 1000px`, `notification-center__item|__body|__time` |
| **5.3 테스트 수정** | `test_room_ui_p2_contract.py`, `test_workspace_ui_contract.py` → `layout.css` |
| **5.4 Orphan 삭제** | `satellites.css`, `layout-extensions.css`, `content-surfaces.css`, `workspace-shell.css`, `chrome.css` |
| **5.5 문서 동기화** | `AGENTS.md`, `UI-MIGRATION-GAPS.md`, `UI-IA-ROADMAP.md`, `developer-agent-console.md` |

### 5.1 커밋 전략 (잔여)

```text
refactor(web): remove orphaned app.css stack and port remaining rules

- Delete app.css, developer-console.css, satellites.css, …
- Port room-task-bar media query, live-agents-strip, notification-center items
- Fix test_room_ui_p2_contract CSS source
- Sync UI-MIGRATION-GAPS / UI-IA-ROADMAP
```

**다른 workstream 파일은 이 커밋에 넣지 말 것.** `git add -p` 또는 stash로 CSS-only path 분리.

### 5.2 `macos26.css` (선택, 미착수)

| 파일 | 조치 |
|------|------|
| `web/src/styles/macos26.css` | Figma reference only (`macos26-library.json`); `main.tsx`·tests 미참조 — 삭제 또는 `web/src/figma/` 이동 검토 |

### 5.3 완료 정의 (DoD)

- [x] `app.css`, `developer-console.css` 및 orphan 5파일 (`satellites`, `layout-extensions`, `content-surfaces`, `workspace-shell`, `chrome`) 디스크에서 없음
- [x] `main.tsx` import 8개 유지; 번들 dead CSS 0 (`macos26.css`는 미import·Figma ref only)
- [x] §7 검증 명령 green (build + 34 contract tests)
- [ ] 브라우저/Tauri 수동: Transcript · Work · Inbox · ⌘K · NotificationCenter · LiveAgentsStrip 시각 회귀 없음 (커밋 전 권장)
- [x] `AGENTS.md` + roadmap + migration-gaps 일치
- [ ] **CSS-only 커밋 / PR** (mixed diff에서 분리)

---

## 6. 함정/리스크

| 함정 | 설명 | 완화 |
|------|------|------|
| **Mixed uncommitted diff** | CSS 완료 but workspace files·hooks·dogfood 등과 혼재 | `git add -p` 또는 stash로 CSS-only 커밋 (§5.1) |
| **수동 시각 회귀** | contract tests는 green; narrow layout·strip·notification UI는 눈으로 확인 권장 | `make dev` 후 §7 수동 스모크 |
| **`layout.css` 비대화** | ~5,000줄 + legacy-bridge merge | 이번 스프린트는 **삭제·포팅만** 완료; 파일 split은 별도 |
| **`macos26.css` 잔존** | Figma ref only, 번들 미로드 | §5.2 선택 정리 |

---

## 7. 검증 명령

```bash
cd /Users/yoonjong/Projects/agent-lab

# Frontend build
cd web && npm run build && cd ..

# CSS / UI contract subset (mock-only)
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/pytest \
  tests/test_room_ui_p2_contract.py \
  tests/test_liquid_glass_scope_contract.py \
  tests/test_workspace_ui_contract.py \
  tests/test_macos_desktop_controls_contract.py \
  -q

# Optional full gate (시간 있을 때)
make test
make ci
```

**수동 스모크 (권장):**

```bash
make dev   # API :8765 + web :5173
```

확인: Room task bar 좁은 창(Tauri ≤1000px), LiveAgentsStrip 칩, NotificationCenter item body/time, ⌘K palette.

---

## 8. 아키텍처 참고 (한 줄)

```text
[삭제 완료 — dead import chain]
app.css → developer-console.css → workspace-shell.css
         (+ satellites.css, layout-extensions.css, content-surfaces.css, chrome.css)

[미import — Figma ref only, 선택 정리]
macos26.css

[현행 번들 — web/src/main.tsx]
tokens → base → layout (+ merged legacy-bridge) → surfaces → plan-execute
       → overlays → tweaks → prototype-panels
```

**SSOT 문서:** `docs/UI-IA-ROADMAP.md` §1.1 · `docs/UI-MIGRATION-GAPS.md` · `docs/developer-agent-console.md`

---

## 9. 요약 (Codex용)

선행 세션 [프로토타입 UI 이식](4be93290-a455-4863-9185-273fe1d80331)에서 import 전환 + `satellites.css` 추출까지 끝났고, [Tier 3 E](647d26e7-6dad-4fc8-b4ae-1e0c22ce4c34)에서 classic/legacy-bridge까지 커밋됐습니다. [IDE 기능 구현](84cdc1b8-24a5-4425-a45c-b2c5760b97f6)에서 `app.css`/`developer-console.css` 삭제를 시작했고, subagent [CSS cleanup 마무리](7f2c5866-3b18-4cfc-b132-1b5b2d32310f)가 **orphan 5파일 삭제·`layout.css` 포팅·테스트·문서 동기화·build green**까지 완료했습니다 (**미커밋**). Codex 잔여: **CSS-only 커밋/PR** + 선택적 `macos26.css` 정리 + 수동 시각 스모크.
