import { useDismissOnPointerDownOutside } from "../hooks/useDismissOnPointerDownOutside";
import { agentLogoSrc } from "../utils/agentLogos";
import type { AgentRole } from "../utils/transcript";
import { Avatar } from "./Avatar";

export type AuthPickerOption = {
  value: string;
  label: string;
  ready?: boolean;
};

type Props = {
  action: "login" | "logout";
  title: string;
  options: AuthPickerOption[];
  highlightedIndex: number;
  onHighlight: (index: number) => void;
  onSelect: (value: string) => void;
  onCancel: () => void;
  /** Provider step shows agent avatars; auth-method step is plain labels. */
  variant?: "agents" | "methods";
};

const AGENT_IDS = new Set(["claude", "codex", "cursor", "kimi", "kimi_work"]);

function asAgentRole(id: string): AgentRole {
  return id as AgentRole;
}

function ProviderGlyph({ providerId }: { providerId: string }) {
  const src = agentLogoSrc(providerId);
  if (!src) {
    return (
      <Avatar
        role={asAgentRole(providerId)}
        label={providerId}
        size={22}
        variant="orb"
      />
    );
  }
  return (
    <img
      className="composer-model-popover__glyph"
      src={src}
      alt=""
      aria-hidden
    />
  );
}

function ChevronIcon() {
  return (
    <svg
      className="composer-model-popover__chevron"
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m6 4 4 4-4 4" />
    </svg>
  );
}

/** Agent/method picker for `/login` and `/logout` — same shell as model popover. */
export function ComposerAuthPickerPopover({
  action,
  title,
  options,
  highlightedIndex,
  onHighlight,
  onSelect,
  onCancel,
  variant = "agents",
}: Props) {
  const rootRef = useDismissOnPointerDownOutside(true, onCancel);
  const actionLabel = action === "logout" ? "로그아웃" : "로그인";

  return (
    <div ref={rootRef} className="composer-model-popover-root">
      <div
        className="composer-model-popover composer-model-popover--main composer-auth-picker-popover"
        role="listbox"
        aria-label={title}
        data-testid="composer-auth-picker-popover"
        data-action={action}
        data-variant={variant}
      >
        <div className="composer-model-popover__compose-head">
          <strong>{actionLabel}</strong>
          <span>{title}</span>
        </div>
        <div className="composer-model-popover__divider" role="separator" />
        <div className="composer-model-popover__list">
          {options.map((opt, index) => {
            const unavailable = opt.ready === false;
            const highlighted = index === highlightedIndex;
            const showGlyph =
              variant === "agents" && AGENT_IDS.has(opt.value.toLowerCase());
            return (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={highlighted}
                disabled={unavailable}
                className={[
                  "composer-model-popover__provider composer-auth-picker-popover__row",
                  highlighted ? "is-active" : "",
                  unavailable ? "is-disabled" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                onMouseEnter={() => onHighlight(index)}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  if (unavailable) return;
                  onSelect(opt.value);
                }}
              >
                <span className="composer-model-popover__provider-main">
                  {showGlyph ? <ProviderGlyph providerId={opt.value} /> : null}
                  <span className="composer-model-popover__provider-name">
                    {opt.label}
                  </span>
                </span>
                {variant === "methods" ? <ChevronIcon /> : null}
              </button>
            );
          })}
        </div>
        <div className="composer-model-popover__divider" role="separator" />
        <div className="composer-model-popover__footer">
          <button
            type="button"
            className="composer-model-popover__action"
            onClick={onCancel}
          >
            취소 (Esc)
          </button>
        </div>
      </div>
    </div>
  );
}
