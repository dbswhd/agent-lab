// SSE discriminated union for Room run events.
// SseFallbackEvent at the end catches any undocumented types.
//
// Usage: the callback in consumeSse/runRoom takes SseRawData (backward-compatible
// Record access). Use SseEvent discriminated union when adding type-safe handler
// maps (see D-2 in the redesign plan).

/** Backward-compatible callback type: accessible as Record but with typed type field. */
export type SseRawData = { type: string } & Record<string, unknown>;

export type SseStartEvent = {
  type: "start";
  session_id: string;
  attachments?: string[];
  send_receipt?: string;
};

export type SseAgentRoundEvent = {
  type: "agent_round_start";
  round: number;
};

export type SseAgentStartEvent = {
  type: "agent_start";
  agent: string;
  round: number;
};

export type SseAgentTokenEvent = {
  type: "agent_token";
  agent: string;
  text: string;
  round?: number;
};

export type SseAgentDoneEvent = {
  type: "agent_done";
  agent: string;
  round: number;
  content?: string;
  envelope?: unknown;
  envelope_parse_error?: boolean;
};

export type SseAgentErrorEvent = {
  type: "agent_error";
  agent: string;
  error: string;
  round?: number;
};

export type SseToolStartEvent = {
  type: "tool_start";
  agent: string;
  tool: string;
  input?: unknown;
};

export type SseToolOutputEvent = {
  type: "tool_output";
  agent: string;
  tool: string;
  output: string;
};

export type SseToolDoneEvent = {
  type: "tool_done";
  agent: string;
  tool: string;
  output?: unknown;
};

export type SseTurnFailedEvent = {
  type: "turn_failed";
  reason?: string;
};

export type SseDispatchStartEvent = {
  type: "dispatch_start";
  [k: string]: unknown;
};

export type SseDispatchDoneEvent = {
  type: "dispatch_done";
  [k: string]: unknown;
};

export type SseHookEvent = {
  type: "hook_event";
  [k: string]: unknown;
};

export type SseInboxPauseEvent = {
  type: "inbox_pause";
  [k: string]: unknown;
};

export type SseConsensusPlanSyncedEvent = {
  type: "consensus_plan_synced";
  excerpt?: string;
  plan_sync_summary?: string;
  [k: string]: unknown;
};

export type SseConsensusPlanSyncFailedEvent = {
  type: "consensus_plan_sync_failed";
  excerpt?: string;
  [k: string]: unknown;
};

export type SseConsensusIncompleteEvent = {
  type: "consensus_incomplete";
  [k: string]: unknown;
};

export type SseConsensusDryRunProposalEvent = {
  type: "consensus_dry_run_proposal";
  proposal?: unknown;
  [k: string]: unknown;
};

export type SseVerifiedPlanSyncedEvent = {
  type: "verified_plan_synced";
  [k: string]: unknown;
};

export type SseVerifiedPlanSyncFailedEvent = {
  type: "verified_plan_sync_failed";
  [k: string]: unknown;
};

export type SseClarifierPromptEvent = {
  type: "clarifier_prompt";
  questions?: unknown[];
  [k: string]: unknown;
};

export type SsePlanWorkflowPendingEvent = {
  type: "plan_workflow_pending";
  [k: string]: unknown;
};

export type SsePlanWorkflowPhaseEvent = {
  type: "plan_workflow_phase";
  [k: string]: unknown;
};

export type SseBlockEvent = {
  type: "BLOCK";
  reason?: string;
  [k: string]: unknown;
};

export type SseRunCancelledEvent = {
  type: "run_cancelled";
  [k: string]: unknown;
};

export type SseRunFailedEvent = {
  type: "run_failed";
  reason?: string;
  [k: string]: unknown;
};

export type SseCompleteEvent = {
  type: "complete";
  session_id?: string;
  [k: string]: unknown;
};

export type SseErrorEvent = {
  type: "error";
  message?: string;
  [k: string]: unknown;
};

export type SseDisconnectedEvent = {
  type: "sse_disconnected";
  [k: string]: unknown;
};

export type SseFallbackEvent = { type: string } & Record<string, unknown>;

export type SseEvent =
  | SseStartEvent
  | SseAgentRoundEvent
  | SseAgentStartEvent
  | SseAgentTokenEvent
  | SseAgentDoneEvent
  | SseAgentErrorEvent
  | SseToolStartEvent
  | SseToolOutputEvent
  | SseToolDoneEvent
  | SseTurnFailedEvent
  | SseDispatchStartEvent
  | SseDispatchDoneEvent
  | SseHookEvent
  | SseInboxPauseEvent
  | SseConsensusPlanSyncedEvent
  | SseConsensusPlanSyncFailedEvent
  | SseConsensusIncompleteEvent
  | SseConsensusDryRunProposalEvent
  | SseVerifiedPlanSyncedEvent
  | SseVerifiedPlanSyncFailedEvent
  | SseClarifierPromptEvent
  | SsePlanWorkflowPendingEvent
  | SsePlanWorkflowPhaseEvent
  | SseBlockEvent
  | SseRunCancelledEvent
  | SseRunFailedEvent
  | SseCompleteEvent
  | SseErrorEvent
  | SseDisconnectedEvent
  | SseFallbackEvent;
