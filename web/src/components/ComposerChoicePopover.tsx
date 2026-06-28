import type { SlashCommandRecord } from "../api/client";
import { useDismissOnPointerDownOutside } from "../hooks/useDismissOnPointerDownOutside";
import { agentLogoSrc, hasAgentLogo } from "../utils/agentLogos";

export type ComposerChoiceOption = {
  value: string;
  label: string;
  ready?: boolean;
};

type BaseProps = {
  command: SlashCommandRecord;
  prompt?: string;
  options: ComposerChoiceOption[];
  onCancel: () => void;
};

type SingleProps = BaseProps & {
  variant: "single";
  highlightedIndex: number;
  onHighlight: (index: number) => void;
  onSelect: (value: string) => void;
};

type MultiProps = BaseProps & {
  variant: "multi";
  selected: Set<string>;
  onToggle: (value: string) => void;
  onApply: () => void;
};

type ScopeProps = BaseProps & {
  variant: "scope";
  onSelect: (value: string) => void;
};

export type ComposerChoicePopoverProps = SingleProps | MultiProps | ScopeProps;

function sectionTitle(
  commandId: string,
  variant: ComposerChoicePopoverProps["variant"],
) {
  if (commandId === "model") {
    return variant === "scope" ? "적용 범위" : "모델";
  }
  if (commandId === "login") return "로그인";
  if (commandId === "logout") return "로그아웃";
  return "선택";
}

function ProviderGlyph({ providerId }: { providerId: string }) {
  const src = agentLogoSrc(providerId);
  if (!src) return null;
  return (
    <img
      className="composer-choice-popover__glyph"
      src={src}
      alt=""
      aria-hidden
    />
  );
}

function CheckIcon() {
  return (
    <svg
      className="composer-choice-popover__check"
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m3.5 8.5 3 3 6-6" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg
      className="composer-choice-popover__chevron"
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

const PROVIDER_GLYPH_IDS = new Set([
  "cursor",
  "codex",
  "claude",
  "kimi",
  "kimi_work",
]);

function hasProviderGlyph(value: string) {
  return PROVIDER_GLYPH_IDS.has(value.toLowerCase()) || hasAgentLogo(value);
}

export function ComposerChoicePopover(props: ComposerChoicePopoverProps) {
  const { command, prompt, options, onCancel, variant } = props;
  const title = prompt || sectionTitle(command.id, variant);
  const showChevrons =
    variant === "single" && (command.id === "login" || command.id === "logout");
  const popoverRef = useDismissOnPointerDownOutside(true, onCancel);

  return (
    <div
      ref={popoverRef}
      className="composer-choice-popover"
      role={variant === "multi" ? "group" : "listbox"}
      aria-label={title}
      data-testid="composer-choice-popover"
      data-command={command.id}
      data-variant={variant}
    >
      <div className="composer-choice-popover__section">
        <div className="composer-choice-popover__heading">{title}</div>
        {options.map((opt, index) => {
          const unavailable = opt.ready === false;
          if (variant === "multi") {
            const checked = props.selected.has(opt.value);
            return (
              <button
                key={opt.value}
                type="button"
                className={[
                  "composer-choice-popover__item",
                  checked ? "is-selected" : "",
                  unavailable ? "is-disabled" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                disabled={unavailable}
                onClick={() => {
                  if (unavailable) return;
                  props.onToggle(opt.value);
                }}
              >
                <span className="composer-choice-popover__item-main">
                  {hasProviderGlyph(opt.value) ? (
                    <ProviderGlyph providerId={opt.value} />
                  ) : null}
                  <span className="composer-choice-popover__label">
                    {opt.label}
                  </span>
                </span>
                <span className="composer-choice-popover__meta">
                  {unavailable ? (
                    <span className="composer-choice-popover__badge">
                      사용 불가
                    </span>
                  ) : checked ? (
                    <CheckIcon />
                  ) : index < 9 ? (
                    <span className="composer-choice-popover__shortcut">
                      {index + 1}
                    </span>
                  ) : null}
                </span>
              </button>
            );
          }

          const highlighted =
            variant === "single" && index === props.highlightedIndex;
          return (
            <button
              key={opt.value}
              type="button"
              role="option"
              aria-selected={highlighted}
              className={[
                "composer-choice-popover__item",
                highlighted ? "is-active" : "",
                unavailable ? "is-disabled" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              disabled={unavailable}
              onMouseEnter={() => {
                if (variant === "single") props.onHighlight(index);
              }}
              onClick={() => {
                if (unavailable) return;
                props.onSelect(opt.value);
              }}
            >
              <span className="composer-choice-popover__item-main">
                {hasProviderGlyph(opt.value) ? (
                  <ProviderGlyph providerId={opt.value} />
                ) : null}
                <span className="composer-choice-popover__label">
                  {opt.label}
                </span>
              </span>
              <span className="composer-choice-popover__meta">
                {unavailable ? (
                  <span className="composer-choice-popover__badge">
                    사용 불가
                  </span>
                ) : showChevrons ? (
                  <ChevronIcon />
                ) : index < 9 ? (
                  <span className="composer-choice-popover__shortcut">
                    {index + 1}
                  </span>
                ) : null}
              </span>
            </button>
          );
        })}
      </div>

      {variant === "multi" ? (
        <>
          <div className="composer-choice-popover__divider" role="separator" />
          <div className="composer-choice-popover__footer">
            <button
              type="button"
              className="composer-choice-popover__action composer-choice-popover__action--primary"
              onClick={props.onApply}
            >
              적용
            </button>
            <button
              type="button"
              className="composer-choice-popover__action"
              onClick={onCancel}
            >
              취소
            </button>
          </div>
        </>
      ) : variant === "scope" ? (
        <>
          <div className="composer-choice-popover__divider" role="separator" />
          <div className="composer-choice-popover__footer">
            <button
              type="button"
              className="composer-choice-popover__action"
              onClick={onCancel}
            >
              취소 (Esc)
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="composer-choice-popover__divider" role="separator" />
          <button
            type="button"
            className="composer-choice-popover__cancel"
            onClick={onCancel}
          >
            취소 (Esc)
          </button>
        </>
      )}
    </div>
  );
}
