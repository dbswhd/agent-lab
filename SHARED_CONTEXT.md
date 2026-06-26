# agent-lab — 공통 컨텍스트

## 아키텍처
Multi-agent developer console: Room discuss → (optional) plan.md → Human-gated worktree execute, merge, and Oracle verify.

Room preset: **fast** (quick, no plan) · **supervisor** (loop, plan + consensus).  
Optional **Kimi Work** daimon peer for Work-quota turns (`kimi_work` agent id).

## 턴 정책 (에이전트 공통)
- **discuss**: read-only overlay on Codex/Claude/Kimi Work — verify with tools, propose via `[PROPOSED:]`, no patch/execute claims.
- **plan**: Scribe updates `plan.md` after the turn.
- Do not open replies by announcing turn mode; follow `[고정 constraints]`.

## 공통 규칙
- Human gate 유지 (자율 merge 금지)
- 완료는 Oracle/verify 기준으로만 주장
- Shipped status: `docs/EXTERNAL-REFS-TRACEABILITY.md` + code + tests
