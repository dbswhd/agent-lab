# Room transcript

**Topic:** envelope 스모크: TypeScript vs JavaScript 중 하나만 고르고 한 줄 근거만. 120자 이내. consensus R2+에는 agent-envelope fence 사용.


## Human

envelope 스모크: TypeScript vs JavaScript 중 하나만 고르고 한 줄 근거만. 120자 이내. consensus R2+에는 agent-envelope fence 사용.

## Cursor

**TypeScript** — `web/src/utils/transcript.ts`에 `AgentEnvelope` 타입·`chatLineToMessage`가 이미 있어 fence JSON과 UI 스모크를 한 경로로 맞출 수 있음.

R2+부터는 응답 맨 위에 `agent-envelope` fence(JSON) 넣고, 본문은 그 아래만 쓰면 됩니다. 파서·프롬프트는 `src/agent_lab/agent_envelope.py`, 검증은 `tests/test_agent_envelope.py` + `scripts/smoke_envelope_run.py`의 `agent_done.envelope` 체크로 이미 연결돼 있습니다.

다음 수정은 레포 기준으로 두 가지면 충분합니다. (1) Cursor/Codex/Claude 시스템 프롬프트에 R2+ fence 필수 한 줄 추가. (2) 스모크 실패 시 `sessions/.../chat.jsonl`에서 fence 누락 라인 번호를 stderr에 찍도록 `smoke_envelope_run.py`만 소폭 보강. JS 쪽 envelope 파일은 없어서 이번 스모크 범위에는 넣지 않는 게 맞습니다.

## Codex

```agent-envelope
TypeScript — 계약/경계 오류를 컴파일 시점에 잡아 envelope 스모크에 더 적합.
```

## Claude

**TypeScript**. 타입 안전성이 멀티 에이전트 메시지 스키마처럼 구조가 고정된 envelope에서 런타임 오류를 컴파일 타임에 잡아줘서.

## Cursor

[이번 턴 · 동료 발화] Claude TS 선택에 동의합니다. 한 줄 근거: **web이 이미 TS**(`transcript.ts`에 `AgentEnvelope` 있음)라 스모크 주제와 UI 파싱이 한 스택에서 맞물립니다.

다음 수정은 이렇게 잡으면 됩니다. `transcript.ts`의 `act: string`을 Python `ActType` union으로 좁히고, fence 파서는 `web/src/utils/agentEnvelope.ts`로 빼서 `ChatBubble`/`RoomChat`이 공유하게 합니다. 검증은 `scripts/smoke_envelope_run.py`가 chat.jsonl의 `envelope` 필드까지 assert하면 R2+ fence 회귀를 한 번에 잡을 수 있습니다.

## Codex

이의 없습니다

## Claude

이의 없습니다.
