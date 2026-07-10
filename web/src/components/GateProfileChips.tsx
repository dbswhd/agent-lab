import { useLocale } from "../i18n/useLocale";
import type { RuntimeSnapshot } from "../api/client";
import { useSessionRuntime } from "../hooks/useSessionRuntime";

type Props = {
  readonly sessionId: string | null;
  compact?: boolean;
  reloadKey?: number;
  /** Parent-provided runtime — skips local `/runtime` fetch when defined. */
  runtimeSnapshot?: RuntimeSnapshot | null;
  run?: unknown;
};

export function GateProfileChips({
  sessionId,
  compact = false,
  reloadKey = 0,
  runtimeSnapshot,
  run,
}: Props) {
  const { t } = useLocale();
  const ownsRuntimeFetch = runtimeSnapshot === undefined;
  const { runtime: fetchedRuntime } = useSessionRuntime(sessionId, {
    reloadKey,
    run,
    enabled: ownsRuntimeFetch,
  });
  const runtime = ownsRuntimeFetch ? fetchedRuntime : runtimeSnapshot;

  const gates = runtime?.gates;
  if (!gates?.gate_profile) return null;

  const chips: { label: string; cls: string; title?: string }[] = [
    {
      label: gates.gate_profile,
      cls: gates.gate_profile === "assistant" ? "pass" : "progress",
    },
  ];
  if (gates.discuss?.open === false) {
    chips.push({
      label: t("gateDiscussPaused"),
      cls: "warn",
      title: gates.discuss.reason ?? undefined,
    });
  }
  if (gates.plan_clarify?.open === false) {
    chips.push({
      label: t("gatePlanBlocked"),
      cls: "warn",
      title: gates.plan_clarify.reason ?? undefined,
    });
  }
  if (gates.execute?.open === false || gates.execute_blocked) {
    // block_reason is the human-readable explanation (e.g. an open BLOCK
    // objection's text); execute.reason is a terser fallback code — the
    // chip used to show neither, just "Execute blocked" with no way to
    // find out why short of digging through the composer stack.
    chips.push({
      label: t("gateExecuteBlocked"),
      cls: "fail",
      title: gates.block_reason ?? gates.execute?.reason ?? undefined,
    });
  }

  return compact ? (
    <div className="ctx-overview__goal-row gate-profile-chips--compact">
      {chips.map((chip) => (
        <span
          key={chip.label}
          className={`ctx-oracle-badge ctx-oracle-badge--${chip.cls}`}
          title={chip.title}
        >
          {chip.label}
        </span>
      ))}
    </div>
  ) : (
    <section className="ctx-section">
      <div className="ctx-section__label">Gate profile</div>
      <div className="ctx-overview__goal-row">
        {chips.map((chip) => (
          <span
            key={chip.label}
            className={`ctx-oracle-badge ctx-oracle-badge--${chip.cls}`}
            title={chip.title}
          >
            {chip.label}
          </span>
        ))}
      </div>
    </section>
  );
}
