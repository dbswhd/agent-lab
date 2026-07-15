# M6 재검토 착수 — UI read-model 실측 dogfood (2026-07-16)

> **범위:** Human이 승인한 것은 "M6 hard delete 실행"이 아니라 **"재검토 착수"** —
> [m6-precheck-retire-scope-2026-07-14.md](./m6-precheck-retire-scope-2026-07-14.md)가 남긴
> 두 미해결 질문(inbox row writer 삭제 가능 여부, UI Room 풀 dogfood)에 실측 근거를 대는
> 작업이다. 이 문서는 **판정을 바꾸지 않는다** — NO-GO는 그대로 유지된다.

## 1. Inbox row writer 삭제 가능 여부 — 정량 재확인

`scripts/mission_ui_read_model_cohort.py` (신규, `mission_dual_write_route_cohort.py`와 동일하게
production HTTP route를 TestClient로 호출) — production `/plan/approve`, `/inbox/{id}/resolve`
경로로 실제 lifecycle을 밟은 뒤 `/mission/read-model`의 `inbox_items[]`를 검사.

실행: `.venv/bin/python scripts/mission_ui_read_model_cohort.py --sessions <scratch>`

| 시나리오 | 결과 |
| --- | --- |
| plan approve → gate open (legacy row 있음) → resolve | `mission_gate_status=open_gate` → `unrelated`, `prompt`/`options` 정상, `decision_version` 포함 — UI ready |
| plan approve → `OpenExecutionGate` 직접 dispatch, **legacy row 없음** | `mission_gate_status=missing_row`, `prompt="Human inbox item unavailable"`, `options=[]` — **UI에 노출 불가능한 placeholder** |

`finding_legacy_row_writer_still_required: true`.

**결론:** m6-precheck의 "Inbox rows: Cannot delete row writer until Decision/inbox read-model
rebuilds prompt/options" 판정은 **오늘도 그대로 유효**하다 — journal만으로는 아직
prompt/options를 복원할 수 없다. 이 항목은 M6 order 2단계("Inbox decision store rich enough
for UI")가 실제로 구현되기 전까지 NO-GO다.

## 2. UI Room 풀 dogfood — 최초 실측 (Playwright mock이 아닌 실 dev server)

`web/e2e/wave-b-journey.spec.ts`(4/4)는 API를 전부 mocking한다. m6-precheck item 2가 요구한
"UI Room 풀 dogfood는 별개"를 오늘 처음으로 실 `uvicorn` + 실 Vite dev server + 브라우저로
수행했다.

**환경:** `AGENT_LAB_MISSION_UI_READ_MODEL=1` · `AGENT_LAB_MISSION_DUAL_WRITE=1` ·
`AGENT_LAB_MISSION_DUAL_WRITE_SESSIONS=browser-dogfood-01` · `AGENT_LAB_MOCK_AGENTS=1`,
scratch `AGENT_LAB_SESSIONS_DIR`에 실제 production route(TestClient 아님, 진짜 HTTP)로
plan approve + `OpenExecutionGate`+legacy row 병행 seed.

| 단계 | 실측 |
| --- | --- |
| 세션 목록 진입 | `browser-dogfood-01`이라는 세션 id가 우연히 앱의 `isDogfoodSession()` 이름 휴리스틱과 충돌해 **Dogfood 탭**으로 분류됨 — 버그 아님, 세션 네이밍 우연 (`web/src/utils/dogfoodSessions.ts`) |
| HumanInboxPanel 렌더 | "위젯 롤아웃을 진행할까요?" + Go/Hold 옵션이 **`/mission/read-model` 폴링 응답**으로부터 정확히 렌더 — network 로그에 `GET .../mission/read-model` 반복 확인, `AGENT_LAB_MISSION_UI_READ_MODEL=1`이 실제로 이 경로를 태움 |
| "Go" 선택 → Submit 클릭 | 브라우저에서 `POST /inbox/{id}/resolve`가 정상 발신됨(network 로그 기록) |
| resolve 완료 확인 | **브라우저 확장 프로그램 자체가 이후 hang**(`javascript_exec`/`navigate` 30–300s 타임아웃) — 미검증. 동일 route를 curl로 직접 재현: `POST /inbox/{id}/resolve {"decision":"go"}` → `200 OK`, 9ms, `mission_dual_write.mirrored=true`, Mission `AWAITING_HUMAN`(v4) → `READY_TO_EXECUTE`(v6), read-model이 즉시 반영 |

**결론:** HumanInboxPanel이 Mission read-model(journal-first projection)만으로 실제 dev
서버에서 렌더링되는 것을 처음으로 육안 확인했다 — Wave A/B UI 계약(§7, §7.3)이 mock이
아닌 실 환경에서도 성립한다. Submit 클릭의 브라우저 측 완료는 도구 장애로 직접 관찰하지
못했으나, 동일 production route가 즉시(9ms) 정상 동작함을 별도로 확인했으므로 **경로
자체의 결함은 아니다**.

## 3. 판정 — 바뀌지 않음

| 질문 | 답 |
| --- | --- |
| Inbox row writer 지금 지워도 되는가? | **아니오** — §1에서 정량 재확인 |
| UI가 Mission-only read로 실제로 그려지는가? | **예**, 처음 실측 확인 (§2) — 단, 이건 "UI가 읽을 수 있다"는 확인이지 "legacy writer를 지워도 된다"는 확인이 아님 |
| M6 hard delete 지금 실행? | **아니오** — `docs/NOW.md`의 안전 경계(execute side effect는 legacy-first, M6 hard delete 금지)는 그대로 유지 |

다음 실행 단계는 m6-precheck의 recommended order 2단계(Inbox decision store가 prompt/options를
journal만으로 복원하도록 재구현)이며, 이는 별도의 설계 결정이 필요한 항목이다.
