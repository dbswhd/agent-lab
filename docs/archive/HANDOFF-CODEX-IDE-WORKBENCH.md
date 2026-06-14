# Codex Handoff — IDE 기능 구현 (Workbench / clever-questing-moth)

> **Archived 2026-06-14** — point-in-time handoff; Workbench core is shipped on `main`. Do not use for status. See [archive/README.md](./README.md) · [EXTERNAL-REFS-TRACEABILITY.md](../EXTERNAL-REFS-TRACEABILITY.md).

> **작성:** 2026-06-13  
> **대상:** Codex (이어서 구현)  
> **SSOT 플랜:** [`/Users/yoonjong/.claude/plans/clever-questing-moth.md`](/Users/yoonjong/.claude/plans/clever-questing-moth.md)  
> **Claude Desktop 세션:** slug `clever-questing-moth`, custom title **「IDE 기능 구현」**  
> **상태:** Phase 1 완료(미커밋) · Phase 2 Track 1 코드 완료 · Phase 2 검증/Track 2 미완 · **전체 미커밋**

---

## 0. 이전 handoff 정정

`docs/archive/HANDOFF-CODEX-IDE-CSS-CLEANUP.md`는 **별도 Cursor 스레드**의 orphan CSS 정리용입니다.  
**본 Workbench(파일·프리뷰·터미널·백그라운드) 작업과 무관**합니다. Codex는 **이 문서**를 SSOT로 삼으세요.

---

## 1. 목적 (플랜 요약)

Agent Lab에 **「작업대」편의 기능**을 붙여 Cursor/Codex/Claude를 따로 쓰지 않고도 IDE형 체감을 주는 것.

**불변 원칙:** 합의=Room · 격리=worktree · 완료=Oracle verified · Human gate 유지.  
읽기는 자유, **repo 직접 쓰기 금지** → execute 게이트 경유.

| Phase | 기능 | 상태 (2026-06-13) |
|-------|------|-------------------|
| **1** | Workspace Files (⌘5 탭) | ✅ 구현·테스트·브라우저 검증 완료 (미커밋) |
| **2a** | 산출물/파일 인라인 프리뷰 | ✅ 코드 완료, **수동 검증 중단** |
| **2b** | dev server 리버스 프록시 | ❌ 미착수 |
| **3** | 범용 백그라운드 작업 | ❌ |
| **4** | 사용자 터미널 | ❌ |

---

## 2. 세션 타임라인

| 단계 | 세션/문서 | 내용 |
|------|-----------|------|
| 진단 | Claude `clever-questing-moth` (85bb74d9…) | 「편의 기능 5종 부재」→ 로드맵 필요 |
| 플랜 작성 | `clever-questing-moth.md` | 4 Phase 로드맵 + Phase 1 상세(B.0–B.5) |
| 플랜 리뷰 | Cursor [플랜 검토](81bb956e-7c8a-426c-a75f-8b71192b304f) | 3라운드 리뷰 → LGTM, B.1a/B.1c/B.2 보강 반영 |
| 구현 승인 | Claude ExitPlanMode | 사용자 승인 후 코딩 시작 |
| **Phase 1** | Claude `clever-questing-moth` | backend + Files 탭 + 13 API tests + browser 검증 |
| UI 폴리시 | 동일 세션 | `tokens.css` 타입/스페이싱 축소, Files 패널 디자인 통일 |
| CSS 정리 | 동일 세션 (또는 Cursor) | `app.css`/`developer-console.css` 등 orphan 삭제 (별도 handoff 참고) |
| **Phase 2a** | Claude `clever-questing-moth` | Track 1: `FilePreview`, `files/raw`, Artifacts 확장 |
| **끊김** | L960 근처 | `npm run build` green 직후, task #9「브라우저 프리뷰 검증」`in_progress`에서 세션 종료 |

---

## 3. 대화에서 나온 결정

1. **우선순위:** 파일 → 라이브 프리뷰 → 백그라운드 → 터미널 (브라우저 자동화는 보류).
2. **Phase 1 API:** `root_id` + `rel_path` 단일 표면; 가상 `@session/` 경로는 UI breadcrumb 전용.
3. **쓰기:** `attachments/`만 PUT 허용; repo·`run.json`·`chat.jsonl` 거부(409 + `route_to_execute`).
4. **path-safety:** `Path.resolve()` + `relative_to()`; `_path_exists_under`의 `is_file()` 재사용 금지.
5. **Phase 2 분기:** Track 1(산출물 인라인) 먼저 — dev-server 프록시(Track 2)는 SSRF 설계 후.
6. **UI 밀도:** 전역 `tokens.css` 베이스 축소(타입 −1px, spacing ~15%) — Files 톤에 맞춤.
7. **검증:** `preview_*` MCP 사용 안 함(플랜 B.4); TestClient + browser MCP / smoke.

---

## 4. 완료됨 (코드 기준, 미커밋)

### Phase 1 — Workspace Files

| 영역 | 파일 |
|------|------|
| 헬퍼 | `src/agent_lab/workspace_files.py` — `list_roots`, `list_dir`, `read_file`, `write_session_file`, traversal 가드 |
| 라우터 | `app/server/routers/workspace_files.py` — roots/list/content/put |
| 등록 | `app/server/main.py` import + `include_router` |
| API 클라이언트 | `web/src/api/client.ts` — `listWorkspaceFileRoots`, `listWorkspaceFiles`, `readWorkspaceFile`, `writeSessionFile`, `workspaceFileRawUrl` |
| UI | `web/src/components/WorkspaceFilesPanel.tsx` |
| 탭 wiring | `workspaceTabs.ts`, `WorkspaceTabBar.tsx`, `desktopShortcuts.ts` (⌘5), `messages.ts` (en/ko), `RoomChat.tsx` 마운트 |
| 테스트 | `tests/test_workspace_files_api.py` — **13 passed** |
| 계약 | `tests/test_macos_desktop_controls_contract.py` — SHORTCUT_INDEX `"5"` |
| 스타일 | `web/src/styles/layout.css` — `.files-tab*`, `.files-tree*` 등 |

### Phase 2a — 인라인 프리뷰 (Track 1)

| 영역 | 파일 / 내용 |
|------|-------------|
| Raw bytes | `GET /api/sessions/{id}/files/raw` — 이미지 등 |
| 헬퍼 | `resolve_readable_file()` in `workspace_files.py` |
| 테스트 | `test_raw_serves_image_bytes`, `test_raw_rejects_traversal` |
| 공유 뷰어 | `web/src/components/FilePreview.tsx` — image / md / diff / html / plain |
| Files 탭 | `WorkspaceFilesPanel` → `FilePreview` 연동 |
| Artifacts 탭 | `ArtifactsListPanel` — `sessionId` prop, 카드 expand + `FilePreview` |
| RoomChat | `ArtifactsListPanel items={...} sessionId={sessionId}` |
| CSS | `layout.css` — `.artifact-card__preview`, `.files-preview*`, `.files-diff*` |

### 검증 완료 (세션 내)

- `pytest tests/test_workspace_files_api.py` — 13 pass  
- `npm run build` — pass (Phase 2a 직후)  
- Phase 1 browser: Files 탭 트리/뷰/attachments 저장 확인됨  
- 전체 pytest: 1007 passed / 3 failed (`test_trading_mission_native_ingest` — 무관)

---

## 5. 미완 / 끊긴 지점 (Codex가 할 일)

### 5.1 Phase 2a 마무리 (우선)

- [ ] **수동 검증** — Artifacts 탭에서 카드 클릭 → md/png/diff 인라인 렌더
- [ ] **수동 검증** — Files 탭에서 html/md/diff/이미지 프리뷰
- [ ] (선택) UI contract 테스트 — `ArtifactsListPanel`에 `sessionId` 전달, `FilePreview` import

### 5.2 Phase 2b — dev server 프리뷰 (플랜 §A Phase 2)

플랜 요구:

- `GET /api/sessions/{id}/preview/*` 리버스 프록시
- **localhost-only** + 포트 allowlist + 세션 인증 (SSRF 방지)
- worktree 경로: `plan_execute_worktree.py` / `_worktree_paths`
- iframe UI (Run 탭 또는 별도 Preview 패널)

**미착수** — 설계·라우터·UI 모두 없음.

### 5.3 커밋 전략 (중요)

워킹 트리에 **Workbench 외 대량 WIP** 혼재:

- `LiveAgentsStrip`, `runningAgents.ts`, hooks/response contracts, dogfood suite, workspace files 외 backend 등
- orphan CSS 삭제 (`app.css`, `satellites.css` 등)

**권장:** Workbench만 분리 커밋

```text
feat(web): add Workspace Files tab and inline artifact preview

- Phase 1: workspace_files API + Files tab (⌘5)
- Phase 2a: FilePreview + files/raw + Artifacts expand
- tests: test_workspace_files_api.py (13), shortcut contract
```

### 5.4 Phase 3·4

플랜 그대로 보류. Phase 2b 완료 후 착수.

---

## 6. Codex 액션 체크리스트 (순서)

1. 플랜 재독: `clever-questing-moth.md` §A Phase 2
2. `make dev` → Artifacts/Files 프리뷰 수동 스모크
3. 부족하면 CSS/edge case 수정 (html sandbox, diff 대용량 등)
4. Phase 2b 설계 초안 → 라우터 스켈레톤 (allowlist 상수부터)
5. `git add -p`로 Workbench-only 커밋
6. `make test` + `npm run build`

---

## 7. 검증 명령

```bash
cd /Users/yoonjong/Projects/agent-lab

# API (mock)
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/pytest tests/test_workspace_files_api.py -q

# Shortcut contract
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/pytest tests/test_macos_desktop_controls_contract.py -q

# Web
cd web && npm run build

# 회귀 (선택)
AGENT_LAB_MOCK_AGENTS=1 .venv/bin/pytest -m "not live" -q
python scripts/smoke_room.py
```

---

## 8. 함정 / 리스크

| 항목 | 설명 |
|------|------|
| **혼재 diff** | RoomChat에 LiveAgents 등 **다른 WIP**가 같이 수정됨 — Workbench 커밋 시 분리 필수 |
| **artifact path** | `room_artifacts` path는 **세션 폴더 상대** → `root_id="session"`으로 읽기 |
| **HTML preview** | `FilePreview` html은 `iframe sandbox=""` — 스크립트 없음 (의도적) |
| **Track 2 SSRF** | dev proxy 없이 localhost curl 금지 — allowlist 설계 선행 |
| **플랜 vs 코드** | 플랜 B.2는 `developer-console.css` 언급 → **삭제됨**, 스타일은 `layout.css`/`tokens.css` |

---

## 9. 완료 정의 (Phase 2 전체)

- [x] Phase 1 DoD (플랜 B.4) — 코드·테스트·Files 탭 수동 확인
- [x] Phase 2a 코드 — FilePreview + raw + Artifacts wiring
- [ ] Phase 2a 수동 검증 — Artifacts/Files 프리뷰 스모크 문서화
- [ ] Phase 2b — preview proxy + iframe + SSRF 가드
- [ ] Workbench 전용 git commit (다른 WIP 제외)

---

## 10. 참고

- 플랜 리뷰: Cursor [clever-questing-moth 검토](81bb956e-7c8a-426c-a75f-8b71192b304f)
- 구현 세션: Claude Desktop slug `clever-questing-moth` (custom title: IDE 기능 구현)
- CSS orphan 정리: `docs/archive/HANDOFF-CODEX-IDE-CSS-CLEANUP.md` (별도 트랙)
