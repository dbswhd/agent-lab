# 작업 로그 — 2026-06-19 (반응성 · 인증/슬래시 UX · 안정화)

> 단일 세션 dogfooding 중 발견한 문제들을 고친 기록. 큼직한 단위로만 정리.
> 커밋은 사용자가 직접 함 — 아래 변경은 모두 워킹트리 상태.

---

## 1. `/api/commands` 반응 지연 → TTL 캐시

- **문제**: "반응이 약간 느림". 측정 결과 `/api/commands`만 **3.6~5.3초** (나머지 엔드포인트는 ≤64ms).
- **원인**: `discover_plugins()`가 호출마다 `claude/codex mcp·plugin list` **CLI 4개를 동기 호출**, 캐시 없음. composer가 슬래시 실행 후 매번 재요청.
- **수정**: `src/agent_lab/plugin_discovery.py` — `discover_plugins`를 TTL(60s) 캐시로 래핑(`_discover_plugins_uncached` + `reset_plugin_discovery_cache`).
- **결과**: 매 호출 3.6~5.3s → **첫 호출 2.1s, 이후 2ms**. picker 클릭 즉시 반응. (부수효과: test-fast 48s→31s)

---

## 2. 로그아웃 UX를 로그인과 대칭으로

- **문제**: 로그인은 staged picker로 잘 구현됐는데 로그아웃은 `/logout <provider>` 단순 입력만.
- **수정**:
  - `slash_commands.py` — `/logout` 단독 시 provider picker, OAuth 제공자는 로컬 계정 비우고 CLI 로그아웃 auth_run 시작, `local` 거부.
  - `command_registry.py` — staged 포맷 + `auth_kind=="oauth"`일 때 logout auth_run.
  - `AuthFlowPanel.tsx` — `run.action`에 따라 "로그인/로그아웃" 라벨 동적화, Codex 프로필 캡처는 login에서만.
- **검증**: 로그아웃 staged/oauth/api 테스트 추가, 전체 그린.

---

## 3. 5가지 사용자 요청

1. **Kimi API 등록했는데 Settings "로그인 필요"** — **표시 버그**. `provider_status_payload()`(auth_runs.py)가 `credentials.toml`만 보고 `accounts.toml`을 무시함. → api/local 제공자는 accounts.toml 기반으로 `has_primary`/`primary_masked` 유도하도록 수정. 로그인 자체는 정상이었음.
2. **정상 로그인 문구** — API 로그인 완료 응답에 `note: "<provider> API 키가 등록되었습니다."` 추가 (Codex OAuth처럼).
3. **Claude 로그인 오류** — `provider_registry.py`의 claude `login_argv`에 있던 `--claudeai`가 설치된 Claude CLI 2.1.50에서 미지원("unknown option"). → 플래그 제거.
4. **/model·/usage·/agents picker** — 비전문가용으로 composer 아래 picker 제공. `slash_commands.py`가 인자 없을 때 choices 반환(`/model`·`/agents`는 멀티선택, `/usage`는 provider 선택), `RoomChat.tsx`에 `commandMultiChoices`(체크박스) UI 추가.
5. **슬래시 결과를 workspace에 출력** — `command_registry.py` `_emit_slash_chat_line()`이 최종 실행 결과를 세션 `chat.jsonl`에 시스템 메시지로 기록(staged 중간 단계는 제외).

> 참고: mypy `src/` 243 errors는 **baseline 그대로**(추가 0). 프로젝트 전반 기존 기술부채로, 이번 범위 밖.

---

## 4. CLI 인증 WebSocket 연결 실패

- **문제**: 로그인 시 "인증 연결 실패: ws://127.0.0.1:**1420**/api/auth/runs/...". Codex는 동작하는데도 실패 메시지가 뜸.
- **원인**: `authRunWsUrl`(client.ts)이 Vite dev 포트(1420)로 ws 연결 — Vite는 ws를 8765로 프록시 안 함. (인증 자체는 별도 CLI 프로세스라 ws만 실패한 것.)
- **수정**: `web/src/api/client.ts` — base 없을 때 `API_ORIGIN`(8765) 기반 ws URL 사용.

---

## 5. Claude "이미 로그인" 처리

- **배경**: Claude CLI 2.1.50은 설계상 **code-paste OAuth**(브라우저 코드 복사→붙여넣기). Codex는 localhost 콜백 자동완료 — CLI 도구 차이라 동일화 불가.
- **수정**: `auth_runs.provider_login_status()` 추가 → 이미 로그인된 OAuth 제공자는 재인증 띄우지 않고 "이미 로그인되어 있습니다" 표시. AuthFlowPanel에 code-paste 안내 문구.
- **메모**: 멀티계정/전환을 위한 `confirm_relogin` 확인단계를 시도했으나, 사용자 요청으로 **이전 동작(이미 로그인 시 스킵)으로 롤백**.

---

## 6. "Error: run failed" + run lock

- **run lock(#1)**: "stale/orphan run lock 해제" 안내는 **의도된 single-flight 가드**. 같은 세션 run.json/chat.jsonl/plan.md 동시 쓰기 방지용. 정상 실패 시 `end_run()`이 finally에서 lock 해제하므로 자동 복구됨(고아 lock 즉시/stale 타임아웃). 제거 대상 아님.
- **run failed(#2)** — **버그 수정**: `room_turn_flow.continue_room_round()`가 `topic.txt`를 **무조건 read** → 파일 없는 stub 세션(`sess-ev` 등 113개 중 3개)에서 `FileNotFoundError`로 런 전체 실패. synthesize 경로(같은 파일)는 `is_file()` 가드가 있었던 비대칭.
- **수정**: `topic.txt` 없으면 이번 턴 메시지를 토픽으로 채택하고 파일을 써서 **self-heal**. 다음 턴부터 정상.

---

## 7. Recovery 알림창 UI 정리

- **문제**: 사이즈가 composer와 안 맞고(전체 폭), 닫기 불가, 영문 라벨로 비통일.
- **수정**:
  - `layout.css` — `.recovery-strip`에 `max-width: var(--composer-max)`(860px) + 가운데 정렬.
  - `RecoveryStrip.tsx` — 헤더 우상단 ✕ 닫기 버튼(`onDismiss`), "Recovery"→"복구".
  - `RoomChat.tsx` — 항목 시그니처 기반 dismiss 상태. 닫으면 숨기되 **새 복구 항목 생기면 재표시**.
- **검증**: 브라우저 실측 — 폭 860px(=composer) 일치, 닫기 버튼 정상.

---

## 변경 파일 (요약)

**백엔드(`src/agent_lab/`)**: `plugin_discovery.py`, `slash_commands.py`, `command_registry.py`, `provider_registry.py`, `credential_store.py`, `auth_runs.py`, `room_turn_flow.py`
**프론트(`web/src/`)**: `api/client.ts`, `components/RoomChat.tsx`, `components/AuthFlowPanel.tsx`, `components/RecoveryStrip.tsx`, `styles/surfaces.css`, `styles/layout.css`
**테스트(`tests/`)**: `test_dynamic_slash_commands.py`, `test_command_registry.py`, `test_auth_runs.py`

## 검증 상태 (세션 종료 시점)

- `make test-fast` 계열: **1242 passed**, 3 failed(기존 kimi/local roster, 무관), 1 skipped
- `mypy src/`: **243 errors == baseline** (추가 0)
- `tsc --noEmit`: clean / `eslint`: error 0 (warning은 기존)

## 후속 거리

- 기존 kimi/local roster 테스트 3건 실패 정리 (이번 작업과 무관, 사전 존재)
- 멀티계정 전환 UX(`confirm_relogin`)를 안전하게 재도입할지 결정
- mypy 243 baseline 점진 감축 (별도 작업)
