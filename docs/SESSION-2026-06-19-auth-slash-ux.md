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
**서버(`app/server/`)**: `main.py`
**프론트(`web/src/`)**: `api/client.ts`, `components/RoomChat.tsx`, `components/AuthFlowPanel.tsx`, `components/RecoveryStrip.tsx`, `styles/surfaces.css`, `styles/layout.css`
**테스트(`tests/`)**: `test_dynamic_slash_commands.py`, `test_command_registry.py`, `test_auth_runs.py`, `conftest.py`

## 검증 상태 (세션 종료 시점)

- `make test-fast` 계열: **1247 passed**, 1 skipped (이전 1242 passed / 3 failed → 전부 해결)
- `mypy src/`: **243 errors == baseline** (추가 0)
- `tsc --noEmit`: clean / `eslint`: error 0 (warning은 기존)
- `make lint`: clean

## 후속 거리

- 기존 kimi/local roster 테스트 3건 실패 — **해결** (원인: `app.server.main` import 시점 `apply_default_room_models_to_env()` 누수 + `AGENT_LAB_ROOM_MODELS` 테스트 간 누수)
- 멀티계정 전환 UX(`confirm_relogin`)를 안전하게 재도입할지 결정
- mypy 243 baseline 점진 감축 (별도 작업)
---

## 8. "극초반 구현 누락" 의심 — 진단 및 해결

- **사용자 질문**: "극초반 거는 구현이 안 됐네 컨텍스트 요약으로 날아갔나?"
- **결론**: **코드 유실은 없었음**. 모든 초기 산출물(`plugin_discovery` 캐시, Pipeline G006, Dynamic Room, `/login` picker, dead-code 제거)이 코드에 그대로 존재.
- **실제 원인 1 — 테스트 누수**: `app/server/main.py`가 **import 시점**에 `apply_default_room_models_to_env()`를 호출해 사용자의 실제 `~/.agent-lab/room_models` 파일을 `AGENT_LAB_ROOM_MODELS`로 프로세스 전역에 적용. 이로 인해 테스트가 `app.server.main`을 import하면 사용자의 dogfooding 설정이 로스터 테스트로 누수되어 codex 기대값이 깨지고, 실행 순서에 따라 다른 실패가 나타나 플레이크로 보임.
- **실제 원인 2 — 사용자 환경 설정**: `~/.agent-lab/room_models` 내용이 `cursor,claude,kimi`로 저장되어 있어 codex가 기본 room composition에서 빠진 상태였음. 이는 `/model` picker로 적용 시 `persist_default_room_models()`에 의해 저장된 것으로 보임.
- **수정**:
  - `app/server/main.py`: `apply_default_room_models_to_env()` 호출을 `_api_startup()` (lifespan)으로 이동. import 시점에는 환경 오염 없음.
  - `tests/conftest.py`: `_isolate_room_model_env` autouse 픽스처 추가 — 매 테스트 전 `AGENT_LAB_ROOM_MODELS` / `AGENT_LAB_ROOM_SUBSTITUTION`을 비우고 테스트 후 복원.
- **검증**:
  - `make test-fast`: **1247 passed**, 1 skipped (이전 1242 passed / 3 failed → 전부 해결)
  - 두 번 연속 전체 스위트 실행: 동일한 1247 passed / 1 skipped (결정적)
  - `mypy src/`: 243 errors == baseline
  - `make lint`: clean
- **사용자 안내**: codex를 기본 room에 다시 포함하려면 `/model` picker에서 `cursor,codex,claude`를 선택해 적용하거나, `~/.agent-lab/room_models` 파일을 직접 수정하면 됨.
