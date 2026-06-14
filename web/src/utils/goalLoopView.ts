import type { GoalLoopRecord, SessionGoalRecord } from "../api/client";

export type GoalLoopView = {
  goal: SessionGoalRecord;
  loop: GoalLoopRecord;
};

export function buildGoalLoopView(
  run: Record<string, unknown> | undefined,
): GoalLoopView {
  const goal = (run?.session_goal as SessionGoalRecord | undefined) ?? {
    text: "",
  };
  const loop = (run?.goal_loop as GoalLoopRecord | undefined) ?? {};
  return { goal, loop };
}
