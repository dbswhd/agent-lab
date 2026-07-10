/** CSS classes for work-status stepper items (WorkStatusBar, GjcPipelineBar). */
export function workStepStatusClass(
  stepIndex: number,
  activeIndex: number,
  options?: { markAllDone?: boolean },
): string {
  if (options?.markAllDone) return "is-done";
  if (stepIndex === activeIndex) return "is-active";
  if (stepIndex < activeIndex) return "is-done";
  return "";
}
