import {
  LAYER_ORDER,
  layerLabel,
  type AgentContextMeta,
  type ContextLayerChars,
} from "../utils/contextMeta";

type Props = {
  layerChars: ContextLayerChars;
  budgetPct?: number;
  trimLevel?: string;
  className?: string;
};

export function ContextLayerBars({
  layerChars,
  budgetPct = 0,
  trimLevel = "ok",
  className,
}: Props) {
  const total = layerChars.total ?? 1;
  const levelClass =
    trimLevel === "critical"
      ? "context-layers--critical"
      : trimLevel === "warn"
        ? "context-layers--warn"
        : "";

  return (
    <div
      className={`context-layers ${levelClass}${className ? ` ${className}` : ""}`}
    >
      <div
        className="context-layers__budget"
        role="meter"
        aria-valuenow={budgetPct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="context-layers__budget-fill"
          style={{ width: `${Math.min(100, budgetPct)}%` }}
        />
      </div>
      <ul className="context-layers__list">
        {LAYER_ORDER.map((key) => {
          const n = layerChars[key];
          if (!n) return null;
          const pct = Math.round((n / total) * 100);
          return (
            <li key={key} className="context-layers__row">
              <span className="context-layers__name">{layerLabel(key)}</span>
              <span className="context-layers__bar-wrap">
                <span
                  className="context-layers__bar"
                  style={{ width: `${Math.max(4, pct)}%` }}
                />
              </span>
              <span className="context-layers__n">{n.toLocaleString()}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function ContextMetaStats({ meta }: { meta: AgentContextMeta }) {
  const parts: string[] = [];
  if (meta.pinned_message_count != null) {
    parts.push(`pin ${meta.pinned_message_count}`);
  }
  if (meta.peer_deduped) parts.push(`dedupe ${meta.peer_deduped}`);
  if (meta.turns_omitted) parts.push(`−${meta.turns_omitted}턴`);
  if (meta.chars_omitted) parts.push(`−${meta.chars_omitted}줄`);
  if (meta.line_range) parts.push(meta.line_range);
  if (meta.numbered_context) parts.push("L번호");
  return (
    <p className="context-preview__stats">
      {parts.length > 0 ? parts.join(" · ") : "—"}
    </p>
  );
}
