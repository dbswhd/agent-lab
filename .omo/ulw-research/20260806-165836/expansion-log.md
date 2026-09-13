# Expansion log

## Gate 0

- Opened incremental research run at 2026-08-06 16:58:36 KST.
- Core question: Which additional GitHub open-source repositories, beyond the eight already reviewed, are strong super-samples for Agent Lab, and exactly what should be absorbed or rejected?
- Axes: durable agent runtime; multi-agent orchestration; terminal/IDE protocol adapters; sandbox/worktree security; observability/evaluation; operator UI and approval surfaces; maintenance/release health; adversarial counter-search.
- Awaiting binding format choice before Wave 1.

## Format contract

- User selected: Markdown additional report.
- Template: Korean, linked to the prior synthesis; executive shortlist; comparative matrix; per-repository implementation evidence; absorb/reject boundary; SHA-pinned GitHub permalinks; ranked implementation experiments; methodology and source ledger.
- Target: 12–15 candidates only if they clear implementation, maintenance, and Agent Lab-fit gates.
- PDF/DOCX and visual rendering gates are not part of this user-selected format.

## Wave 1

- Workers: 14 (`runtime_durable`, `coding_harnesses`, `multiagent_frameworks`, `sandbox_security`, `observability`, `eval_frameworks`, `operator_ui`, `ide_terminal_protocols`, `workflow_graphs`, `memory_context`, `permissions_policy`, `git_worktree_merge`, `maintenance_health`, `local_fit`).
- Status: all terminal; 14 observation groups recorded as O2–O15.
- New actionable leads opened for Wave 2: Microsoft Agent Framework checkpoint/approval tests; Cline session-event/approval tests; Overstory merge failure/reconciliation; Inspect+Harbor resource/trajectory contract; OpenInference redaction/projection gap; OpenHands Condensation records; AX/Chidori replay semantics; self-hosted agent sandbox alternatives.
- Leads closed as duplicate: LangGraph, Deep Agents, OpenAI Agents SDK, ACP, AgentGUI, CWC long-running agents, Open SWE, Attractor, A2UI/MCP Apps were covered in the baseline report.
- Leads closed as dead end/reject: AutoGen new adoption (maintenance mode); Swarm new adoption (successor named); Daytona OSS dependency (unmaintained); Netflix Conductor (stale/non-agent-native); AutoGPT absorption (mixed license); Continue as authoritative runtime; generic Temporal/Prefect/DBOS replacement of Room FSM.

## Wave 2

- Workers: 8 targeted expansion lanes plus root GitHub verification.
- Closed: Agent Framework scheduler adoption; Cline approval controller adoption; OpenInference as event SSOT; single-framework eval adoption; AX shortlist; Docker-only sandbox alternatives.
- Promoted: OpenHands Condenser implementation; Chidori as watch candidate; OpenSandbox as self-hosted sandbox control layer; Inspect+Harbor composition; Warren as active successor to archived Overstory.
- Root verification: 19 repository APIs + `git ls-remote` matched pinned HEADs; detected redirects and archived status.
- New lead opened: Warren's backward-compatible absent-origin trust and best-effort teardown need adversarial review.

## Wave 3 — refinement/counter-search

- Workers: 8 (`refine_rank`, `refine_sources`, `refine_security`, `refine_eval`, `refine_cost`, `refine_duplicates`, `refine_governance`, `refine_report`).
- Material corrections: native Room Bench before external eval runtime; Warren conditional rather than unconditional; Cline event/replay only; OpenInference projection only; Chidori watch; Overstory historical; canonical repo corrections for Warren, Harbor, OpenSandbox, Burr and OpenHands SDK.
- Governance reviewer initially matched wrong Warren/Harbor entities; follow-up corrected and explicitly retracted those observations. Only `jayminwest/warren` and `harbor-framework/harbor` enter the synthesis.

## Lead disposition and convergence

| lead | disposition | effect on answer |
|---|---|---|
| Agent Framework checkpoint/approval tests | investigated Wave 2 | shape reference; scheduler rejected |
| Cline event/approval/replay tests | investigated Wave 2 | event/replay retained; approval rejected |
| Overstory rollback/queue/recovery | investigated Wave 2 | historical only; latent dequeue/reconciliation gaps |
| Warren successor | E1 investigated | replaces Overstory for active lifecycle reference |
| Warren absent-origin trust | red-teamed Wave 3 | unresolved security caveat; conditional tier |
| Warren teardown/salvage | red-teamed Wave 3 | require acknowledgment/repair; conditional tier |
| Inspect event/limit schema | investigated Wave 2/3 | native bench schema/export inspiration |
| Harbor resource/result schema | investigated Wave 2/3 | reward vs infra error retained; whole runtime deferred |
| tau2-bench dialogue fixtures | watch/out-of-scope | no top-level change; native five fixtures selected |
| SWE-bench/Terminal-Bench container lane | deferred | separate later adversarial lane |
| OpenInference masking/redaction | investigated Wave 2/3 | safe projection requirement |
| OTel GenAI dedicated schema repo | investigated | schema pin/mapping version requirement |
| OpenHands Condenser source/tests | investigated Wave 2 | active pattern source; SDK identity corrected |
| nested condensation/tool pairing | future conformance test | open implementation risk, not open research lead |
| Letta memory diff / Graphiti temporal memory / Mem0 | watch | useful, but compaction record gives smaller first probe |
| contamination fixtures | folded into future tests | no new repo required |
| AX resume/fork/idempotency | investigated Wave 2 | rejected until resume TODO removed |
| Chidori lease/signal/replay | investigated Wave 2/3 | watch; exactly-once unresolved |
| self-hosted OpenSandbox alternatives | investigated Wave 2 | OpenSandbox selected; weaker Docker-only candidates closed |
| OpenSandbox cleanup/snapshot | unresolved implementation caveat | conditional sandbox tier |
| Firecracker/gVisor | infrastructure primitive reference | not Agent Lab control-layer candidate |
| OpenSandbox trusted-host TOCTOU | security requirement | deny-by-default plus handoff tests; no new candidate |
| Burr action/state tests | source inspected; future local probe | pattern retained |
| Mastra suspend/resume | partial/watch | no stronger evidence than selected candidates |
| DBOS/Hatchet/Temporal/Prefect | generic engine dead end | no Room FSM replacement |
| Pydantic AI/Harness | watch | typed approval useful but no added top-10 value after MAF/Cline |
| OpenCode lineage/event bus | duplicate/narrow reference | Cline source had stronger tested replay path for current question |
| Cloudflare durable approval | watch/out-of-scope | would not change Human Inbox authority |
| Magentic-UI decision model | investigated/red-teamed | UI-only provenance reference |
| content-addressed approval receipt | design consequence | future local test, no external dependency selected |
| Goose/Aider/Continue | narrow pattern/reference | not active top-10 entry |
| AutoGen/Swarm/Daytona/AutoGPT/Conductor | dated reject/historical | primary-source reasons in synthesis |
| metadata-verified subset | resolved | exact 19 + Warren table written to verification artifact |
| source link correctness | sampled + SHA/API verified | no sampled broken link; temporal caveat retained |
| legal/license completeness | explicitly out-of-scope | technical screen only |

Convergence: zero unchecked leads remain. Items marked watch, future conformance test, deferred, or out-of-scope have explicit effects and do not change the final shortlist or experiment order. Three research/refinement waves and one bounded excursion are closed.
