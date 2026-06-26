# Room 에이전트 역할

Agent Lab Room에 참여할 수 있는 에이전트와 **discuss / plan** 턴 규칙 요약.  
런타임 프롬프트 SSOT: `src/agent_lab/agents/prompts.py` · payload 조립: `context_bundle.py` · 권한: `agent_permissions.py`.

## 참여 에이전트

| ID | 표시명 | 런타임 | 한 줄 역할 |
|----|--------|--------|------------|
| **cursor** | Cursor | Cursor SDK (로컬 tools) | 레포·파일·UI·패치 — execute 주력 |
| **codex** | Codex | Codex CLI | 분해·순서·검증·완료 기준 |
| **claude** | Claude | Claude Code CLI | 맹점·리스크·설명 · Scribe(기본) |
| **kimi_work** | Kimi Work | daimon Control WS | Work quota peer — 레포 검증·대안·약한 가정 도전 |
| **kimi** | Kimi | Kimi API | API 폴백 (Work bridge 불가 시) |
| **local** | Local | mock / stub | CI·오프라인 대체 |

기본 3자 Room은 `cursor` + `codex` + `claude`. `/model`로 composition 변경 가능. Kimi Work는 Loop·supervisor preset에서 peer로 자주 포함.

## Room preset (Composer)

| Preset | UI | turn_profile | plan 갱신 | consensus |
|--------|-----|--------------|-----------|-----------|
| **fast** | 빠른 | `quick` (리드 1명) | OFF | OFF |
| **supervisor** | 감독 | `loop` | ON | ON |

세부: [USER-GUIDE.md §6.2–6.4](./USER-GUIDE.md).

## Discuss vs plan (Compose mode)

Human이 Work에서 「전송 시 plan 갱신」을 켜면 **plan** 턴, 끄면 **discuss** 턴.

| | discuss | plan |
|---|---------|------|
| Scribe | **안 함** | 턴 후 `plan.md` 갱신 |
| Codex / Claude | read-only overlay (write off) | tools/write per permissions |
| Kimi Work | read-only — 검증·`[PROPOSED:]`만 | 동일 (execute 주장 금지) |
| Cursor | tools 유지 (execute는 별도 gate) | tools 유지 |
| receipt | `discuss_saved` | `plan_updated` |

**에이전트 규칙:** `[고정 constraints]`에 이미 턴 정책이 있다. 답변 첫 줄에 「discuss/plan 모드입니다」처럼 **모드를 선언하지 말고** 바로 내용으로 답한다.

Discuss 턴에서:

- 레포는 **Read/Grep/도구로 검증** 후 주장
- 파일 수정·execute 완료 **주장 금지** — 실행 제안은 `[PROPOSED: …]` 텍스트
- Loop consensus R2+에서는 `agent-envelope` speech act (`ENDORSE`, `CHALLENGE`, …)

## Kimi Work peer

- 세션 `session_folder` ↔ daimon `conversationKey` 매핑 (`kimi_work.json`)
- workspace root는 session binding (`kimi_work_workspace`)
- Human Inbox (`ask_human` / `propose_build`) — 방향·GO gate는 inbox 도구, plain prose fork 금지
- Bridge warm: API startup `warm_bridge`, probe TTL `AGENT_LAB_KIMI_WORK_PROBE_TTL_S`

## Human vs peer

- **Peer끼리** scope·접근·파일·검증 순서는 envelope + `[PROPOSED:]`로 조율
- **Human**에게만: GO gate, 예산, prod 파괴, secrets, 해결 불가 fork
