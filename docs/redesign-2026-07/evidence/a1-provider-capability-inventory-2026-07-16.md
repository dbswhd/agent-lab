# A1 — Provider capability inventory (2026-07-16)

> [03-agent-runtime-context-memory.md](../03-agent-runtime-context-memory.md) §4 A1의 산출물.
> `agent/health.py::agent_health_row()`가 이미 provider별 health를 계산하고 있지만, provider마다
> if/elif 분기로 서로 다른 필드를 만드는 구조라 A1이 요구하는 "공통 capability vocabulary"는 아직
> 없다. 이 문서가 6개 provider의 실제 현재 매트릭스를 고정한다. **판정을 바꾸지 않는다** — A2(AgentRuntime
> port)를 시작할 근거 문서다.

## 1. 현재 provider 목록과 auth/health 매트릭스

`agent_health_row()`(`agent/health.py`)의 provider별 분기를 그대로 표로 옮긴 것 — 코드가 실제로 하는
일이지 목표 설계가 아니다.

| provider | auth_mode | configured 판정 | bridge probe | ready 판정 | provider 전용 필드 |
| --- | --- | --- | --- | --- | --- |
| `cursor` | API key + SDK | `provider_has_credentials` + `_cursor_sdk_installed()` | `_check_cursor_bridge`(옵션) | `configured and bridge == "ok"` | `bridge`(ok/unknown/실패 사유) |
| `codex` | OAuth | `resolve_codex_bin()` 존재 여부 | 없음 | `codex_oauth_ready()` | `auth_mode="oauth"`, `detail`(bin path) |
| `claude` | OAuth | `resolve_claude_bin()` 존재 여부 | 없음 | `claude_auth_logged_in()` | `auth_mode="oauth"`, `detail`, `remediation` |
| `kimi` | API key | `kimi_provider.is_available()` | 없음 | `= configured` | 없음 |
| `kimi_work` | daimon-share | `kimi_work_provider.is_configured()` | `probe_control()`(옵션) | `bridge == "ok"` | `bridge`, `loop_phase` |
| `local` | 없음(로컬 모델) | 항상 `True` | 없음 | `local_provider.is_available()` | `model`(provider가 직접 override) |

**공통 base 필드**(모든 provider): `id`, `label`, `model`, `configured`, `ready`, `bridge`("n/a" 기본),
`hint`. **공통이 아닌 것**: `auth_mode`는 codex/claude만, `bridge` 실측은 cursor/kimi_work만,
`loop_phase`는 kimi_work만, `remediation`은 claude만 — A1 acceptance criteria "unavailable/degraded/
healthy 의미가 통일된다"가 아직 사실이 아니다. `ready=False`가 "설정 안 됨"과 "설정됐지만 인증 실패"와
"bridge 다운"을 구분 없이 같은 값으로 표현한다.

## 2. Tool capability — 4/6 provider만 등록됨

`room/agent_capabilities.py::_CAPABILITY_AGENTS = ("cursor", "codex", "claude", "kimi_work")` —
`kimi`(plain)와 `local`은 tool capability manifest가 아예 없다. `agent_health_row()`의
`_capability_fields()`가 이 4개에서만 `capabilities`/`capability_label`을 채우고, 나머지 2개는
빈 dict를 병합한다(에러 없이 조용히 누락).

## 3. Stream 지원 — 2/6 provider만 구조화 파싱

`agent/stream_parser.py`가 JSON 이벤트 파서를 갖춘 건 `parse_codex_json_event`/
`parse_claude_json_event` 뿐이다. cursor/kimi/kimi_work/local의 실제 스트리밍 처리 방식(구조화 이벤트
vs 완료 후 일괄 텍스트)은 이번 감사에서 개별 확인하지 않았다 — A2 착수 시 provider별로 직접 코드를
읽어야 한다.

## 4. Cancel/Resume — 정정(2026-07-16 후속 조사, 05 R2와 연계)

**정정:** 처음엔 "이름으로 찾을 수 있는 provider-level cancel 함수 없음"이라고 적었다 — 검색어가
틀렸다. `cancel_open_execution`은 execution(merge 단위) 취소가 맞지만, provider invoke 자체의
mid-stream cancel도 실제로 존재한다 — 이름이 "cancel"이 아니라 `agent_lab.run.control`의
`is_cancelled()`/`register_child_process()`일 뿐이다.

| provider | cancel 메커니즘 | 실측 |
| --- | --- | --- |
| `claude` | 실제 subprocess, `register_child_process` + `is_cancelled()` 폴링 → `unregister_child_process` | `claude/cli.py` 2개 respond 경로 모두 |
| `codex` | 동일 패턴(subprocess kill) | `codex/cli.py` |
| `cursor` | SDK 호출 — process 없음, `is_cancelled()` 폴링 후 `RoomRunCancelled` raise로 unwind | `cursor/provider.py` |
| `kimi_work` | bridge 호출 — 동일하게 `is_cancelled()` 폴링 + `RoomRunCancelled` | `kimi/control_client.py` |
| `kimi`(plain) | **없음** | `kimi/provider.py`에 `run.control` 참조 없음 |
| `local` | **없음** | `local/provider.py`에 `run.control` 참조 없음 |

cancel이 있는 4개(`claude`/`codex`/`cursor`/`kimi_work`)는 §2의 tool capability 등록 4개와 **정확히
일치**한다 — 우연이 아니라 이 4개가 "완전히 통합된 provider", 나머지 2개(`kimi`/`local`)가 "최소
provider"라는 두 계층이 실제로 존재한다는 뜻이다.

**Resume**은 다른 계층: `agent/thread_resume.py` + `agent/thread_catalog.py::AGENT_IDS = ("cursor",
"codex", "claude")`가 provider CLI thread 재개(예: `claude --resume`)를 담당한다. `kimi_work`는 cancel은
있지만 thread resume은 없다 — 4-provider cancel 그룹과 정확히 겹치지 않는 3-provider resume 그룹이다.

이건 05(R1/R2, `docs/redesign-2026-07/evidence/r1-journey-reliability-matrix-2026-07-16.md`)에서
execution 레벨 cancel(`cancel_open_execution`)에 테스트가 전무했던 걸 발견하고 고친 것과 별개 층위다
— 두 gap 모두 이제 문서화됐고, provider 레벨 cancel은 gap이 아니라 **이미 존재하는데 A1이 못 찾았던
것**이었다.

## 5. 이미 있는 부분 invoke 추상화 — `runtime/adapters/`

A2("AgentRuntime port")를 처음부터 설계할 필요는 없다 — `runtime/adapters/execute.py`가 이미
`invoke_execute(agent_id, req)` / `execute_agent_available(agent_id)` / `ExecuteInvokeRequest`로
execute/repair 경로의 provider 호출을 추상화하고 있고, `runtime/adapters/discuss.py`가 discuss 경로도
비슷하게 감싼다. 이 두 adapter가 서로 다른 코드(activity별로 별도)인 게 A1의 결함("provider-specific
예외가 adapter 내부/외부 중 어디에 속하는지 결정되지 않음")과 정확히 일치하는 사례다.

## 6. A1 acceptance criteria 대조

| 기준 | 상태 |
| --- | --- |
| 모든 provider가 공통 capability vocabulary로 표현 | **아니오** — base 필드 7개는 공통, 나머지는 provider별 ad hoc(§1) |
| provider-specific 예외가 adapter 내부/외부 중 어디에 속하는지 결정 | **부분** — execute/discuss는 `runtime/adapters/`가 이미 분리(§5), 그 외 경로(Room 직접 호출)는 미확인 |
| unavailable/degraded/healthy 의미 통일 | **아니오** — `ready=False`가 여러 다른 실패 원인을 구분 안 함(§1) |
| cancel/resume 지원 매트릭스 | **완료**(§4, 2026-07-16 정정) — cancel 4/6(`claude`/`codex`/`cursor`/`kimi_work`), resume 3/6(`claude`/`codex`/`cursor`) |

`tests/test_provider_capability_inventory.py`가 cancel 4개/resume 3개 provider 집합을 고정한다.

## 7. 다음

A2(AgentRuntime port)는 `runtime/adapters/execute.py`/`discuss.py`를 일반화하는 것부터 시작하면 된다
— cancel/resume 실측이 끝나서(§4) 인터페이스에 뭘 넣을지는 이제 막힘이 없다. 남은 진짜 설계 결정은
capability vocabulary 통일(§1, base 7필드 vs provider별 ad hoc 필드)과 `kimi`/`local`을 4-provider
그룹으로 승격할지(cancel/tool capability 둘 다 없음, §2/§4) 여부다.
