import type { AgentHealthRow, PlanExecutionRecord } from "../api/client";
import type { ConsensusDryRunProposal } from "../components/ConsensusDryRunGateBar";

export const DEMO_EXEC_PENDING: PlanExecutionRecord = {
  id: "demo-exec-pending",
  action_key: "demo-merge-quant",
  action_what: "Merge quant-pipeline v3 changes",
  status: "pending_approval",
  needs_artifact_review: true,
  verification_artifacts: {
    ok: true,
    pdf_path: "reports/sprint-d-verification.pdf",
    pdf_page_count: 12,
  },
};

export const DEMO_EXEC_PENDING_BLOCKED: PlanExecutionRecord = {
  id: "demo-exec-blocked",
  action_key: "demo-update-fixtures",
  action_what: "Execute: update-backtesting-fixtures",
  status: "pending_approval",
  needs_artifact_review: true,
  verification_artifacts: {
    ok: false,
    pdf_path: null,
    pdf_page_count: null,
  },
};

export const DEMO_CONSENSUS_PROPOSAL: ConsensusDryRunProposal = {
  notice: "♾️ 합의 완료 — plan을 dry-run으로 검증하세요.",
  recommended: {
    action_key: "demo-quant-fix",
    what: "Apply quant-control regression fix",
  } as ConsensusDryRunProposal["recommended"],
  has_executable: true,
  action_key: "demo-quant-fix",
};

export const DEMO_OBJECTION_NOTICE = {
  message: "Claude BLOCK — Math.ceil alone isn't safe for zero-height content.",
  objectionId: "demo-obj-1",
  actionIndex: 2,
};

export const DEMO_PREFLIGHT_AGENTS: AgentHealthRow[] = [
  {
    id: "cursor",
    label: "Cursor",
    ready: false,
    configured: true,
    bridge: "error",
    reason: "Bridge offline (demo)",
    hint: "make tauri-dev 또는 bridge 확인",
  },
];

export const DEMO_PLAN_STALE_NOTICE =
  "plan이 토론보다 뒤처짐 — Work 탭에서 plan을 갱신하세요.";
