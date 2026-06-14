import { useEffect, useState } from "react";
import { fetchSessionRuntime, type RuntimeSnapshot } from "../api/client";
import { useLocale } from "../i18n/useLocale";

type Props = {
  readonly sessionId: string | null;
};

export function GateProfileChips({ sessionId }: Props) {
  const { t } = useLocale();
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setRuntime(null);
      return;
    }
    let cancelled = false;
    void fetchSessionRuntime(sessionId)
      .then((snap) => {
        if (!cancelled) setRuntime(snap);
      })
      .catch(() => {
        if (!cancelled) setRuntime(null);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const gates = runtime?.gates;
  if (!gates?.gate_profile) return null;

  const chips: { label: string; cls: string }[] = [
    {
      label: gates.gate_profile,
      cls: gates.gate_profile === "assistant" ? "pass" : "progress",
    },
  ];
  if (gates.discuss?.open === false) {
    chips.push({ label: t("gateDiscussPaused"), cls: "warn" });
  }
  if (gates.plan_clarify?.open === false) {
    chips.push({ label: t("gatePlanBlocked"), cls: "warn" });
  }
  if (gates.execute?.open === false || gates.execute_blocked) {
    chips.push({ label: t("gateExecuteBlocked"), cls: "fail" });
  }

  return (
    <section className="ctx-section">
      <div className="ctx-section__label">Gate profile</div>
      <div className="ctx-overview__goal-row">
        {chips.map((chip) => (
          <span
            key={chip.label}
            className={`ctx-oracle-badge ctx-oracle-badge--${chip.cls}`}
          >
            {chip.label}
          </span>
        ))}
      </div>
    </section>
  );
}
