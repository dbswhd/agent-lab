# M6 precheck — three questions (2026-07-14)

> **판정:** M6 hard retire **아직 NO-GO**. 아래 3항은 soft authority 증거 + 삭제 불가 이유를 고정한다.

## 1) 실제 worktree execute → merge → Oracle dogfood

**방법:** `/tmp` route cohort + Slice 1–3 authority flags  
`scripts/mission_dual_write_route_cohort.py`  
Artifacts: `/tmp/agent-lab-dw-m6-precheck-20260714/` · sessions `/tmp/dw-route-auth-sessions`

| Route | Result |
| --- | --- |
| execute/resolve approve (real worktree merge) ×2 | 200 · mirrored · `VERIFYING` · merge_committed |
| execute/merge/confirm | 200 · mirrored · `VERIFYING` |
| execute/reverify Oracle pass | 200 · mirrored · `SUCCEEDED` · verdict pass |
| fail→repair→pass | 200 · mirrored · `SUCCEEDED` |
| crash recovery | recovered |
| rollback (DUAL_WRITE off) | PASS |

**Verdict:** Soft-authority 하에서 **실 worktree 경로 dogfood PASS**.  
**한계:** Cursor dry-run(에이전트 패치) 풀 루프는 아님 — cohort는 worktree를 seed 후 resolve/merge/reverify. UI Room 풀 dogfood는 별개.

## 2) UI / execute gate가 Mission 없이 깨지지 않는지

**결론:** 지금도 UI·execute gate는 **`run.json` legacy만 읽는다**. Mission read-model은 프로덕션 UI에 연결되어 있지 않다.

| Consumer | Reads | Mission journal? |
| --- | --- | --- |
| `ensure_plan_workflow_approved` | `plan_workflow.phase` + hash | No — projection만 필요 |
| Objection BLOCK→409 | `run.objections` | No |
| Plan UI / SSE | `session.run.plan_workflow` | No `/mission/read-model` in web |
| HumanInboxPanel | `human_inbox[]` full rows | Gate id만으로는 UI 불가 |
| Mission loop / work status | `mission_loop` | No Mission→loop projection |

**Implication:** Soft slices keep gates/UI OK **because writers still fill `run.json`** (or Mission projects plan phase).  
Deleting writers **without** richer projection / journal-first UI → **inbox + mission_loop + orchestration break**. Plan execute gate alone could survive if `_project_plan` stays.

## 3) Retire 범위 초안 (projection vs delete)

| Surface | Soft now | M6 candidate | Must stay until… |
| --- | --- | --- | --- |
| Plan phase write | Mission first + `_project_plan` | Delete secondary phase writer in `approve_plan` | UI stays on `plan_workflow` **or** journal-first plan API |
| Inbox rows | Mission gate + legacy row write | **Cannot delete row writer** until Decision/inbox read-model rebuilds prompt/options | HumanInboxPanel rewritten |
| Inbox gates | Mission authority | Keep journal gates | — |
| Execute side effects | Legacy first + fail-closed Mission commit | Side effects stay in plan/execute*; only delete *duplicate FSM updates* if any | Never delete worktree/merge/Oracle runners in M6 name of “retire” |
| `mission_loop` | Still legacy writer | Delete only after Mission operational status + UI consume it | Work status / mission API |
| Dual-write bridges / flags | Required | Delete last, after single authority proven | Rollback story gone |
| Objection BLOCK | Untouched | Out of M6 | Product invariant |

**Recommended M6 order (when Human re-approves):**

1. Journal-first **read** adapters for plan phase + operational status (UI still may show projected `plan_workflow`).
2. Inbox decision store rich enough for UI (or keep `human_inbox` as forever-projection written only from Mission).
3. Stop legacy **lifecycle** patches that duplicate Mission state (`plan_workflow.phase` re-write when already projected; `mission_loop.phase` if replaced).
4. Remove dual-write fail-open mirrors / authority flags.
5. Dead-code scan + import boundary tests.

**Not in first M6 PR:** deleting `create_inbox_item` payload writer, deleting execute/merge/Oracle implementers, flipping UI solely to raw journal.

## Bottom line

| Question | Answer |
| --- | --- |
| Full-path dogfood enough for soft? | **Yes** (route cohort PASS under authority) |
| UI/gates survive Mission-only writes today? | **Only via run.json projection/legacy writes** — not pure journal |
| M6 delete now? | **No** — Wave A design+API shipped ([journal-first](./journal-first-read-projection-design-2026-07-14.md)); need Wave B UI dogfood + explicit Human gate |

**2026-07-16 update:** Human 승인으로 재검토를 착수했다 — 판정은 바뀌지 않았다. See
[m6-ui-read-model-dogfood-2026-07-16.md](./m6-ui-read-model-dogfood-2026-07-16.md): (1) inbox row
writer는 오늘도 정량적으로 필요함이 재확인됐고, (2) UI Room 풀 dogfood(비-mock)를 처음 실행해
HumanInboxPanel이 read-model만으로 렌더링됨을 확인했다.
