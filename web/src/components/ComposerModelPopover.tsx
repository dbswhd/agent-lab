import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { SlashCommandRecord } from "../api/client";
import { useDismissOnPointerDownOutside } from "../hooks/useDismissOnPointerDownOutside";
import { agentLogoSrc } from "../utils/agentLogos";
import type { AgentRole } from "../utils/transcript";
import { Avatar } from "./Avatar";
import { ModelEffortSlider } from "./ModelEffortSlider";

export type ModelPopoverAgent = {
  value: string;
  label: string;
  ready?: boolean;
  /** Show preset drill chevron (claude, codex, cursor, kimi). */
  drillable?: boolean;
};

export type ModelPopoverPreset = {
  value: string;
  label: string;
  selected?: boolean;
  available?: boolean;
  comingSoonNote?: string;
};

export type ModelPopoverSidePanel = {
  providerId: string;
  providerLabel: string;
  presets: ModelPopoverPreset[];
  efforts?: string[];
  selectedModel?: string;
  selectedEffort?: string;
};

export type ComposerModelPopoverProps = {
  command: SlashCommandRecord;
  autoEnabled: boolean;
  agents: ModelPopoverAgent[];
  sidePanel: ModelPopoverSidePanel | null;
  selectedAgents: Set<string>;
  onProviderDrill: (providerId: string) => void;
  onSidePresetSelect: (providerId: string, value: string) => void;
  onSideEffortSelect?: (providerId: string, effort: string) => void;
  onSideClose: () => void;
  onAgentToggle: (value: string) => void;
  onAgentsApply: () => void;
  onCancel: () => void;
};

const DRILLABLE_AGENTS = new Set(["claude", "codex", "cursor", "kimi"]);
const SIDE_PANEL_WIDTH = 260;
const SIDE_PANEL_GAP = 8;
const VIEWPORT_MARGIN = 8;

function asAgentRole(id: string): AgentRole {
  return id as AgentRole;
}

function computeSidePanelPosition(
  mainRect: DOMRect,
  rowRect: DOMRect,
): { top: number; left: number } {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const maxHeight = Math.min(vh * 0.7, 520);

  let left = mainRect.right + SIDE_PANEL_GAP;
  if (left + SIDE_PANEL_WIDTH > vw - VIEWPORT_MARGIN) {
    left = mainRect.left - SIDE_PANEL_WIDTH - SIDE_PANEL_GAP;
  }

  let top = Math.max(rowRect.top, mainRect.top);
  if (top + maxHeight > vh - VIEWPORT_MARGIN) {
    top = Math.max(VIEWPORT_MARGIN, vh - maxHeight - VIEWPORT_MARGIN);
  }

  return { top, left };
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

function CheckIcon() {
  return (
    <svg
      className="composer-model-popover__check"
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

export function ComposerModelPopover({
  autoEnabled,
  agents,
  sidePanel,
  selectedAgents,
  onProviderDrill,
  onSidePresetSelect,
  onSideEffortSelect,
  onSideClose,
  onAgentToggle,
  onAgentsApply,
  onCancel,
}: ComposerModelPopoverProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const mainRef = useRef<HTMLDivElement>(null);
  const sidePanelRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [sidePosition, setSidePosition] = useState<{
    top: number;
    left: number;
  } | null>(null);
  useDismissOnPointerDownOutside(true, onCancel, rootRef, undefined, [
    sidePanelRef,
  ]);

  useLayoutEffect(() => {
    if (!sidePanel) {
      setSidePosition(null);
      return;
    }

    const providerId = sidePanel.providerId;

    function updatePosition() {
      const row = rowRefs.current[providerId];
      const main = mainRef.current;
      if (!row || !main) return;
      setSidePosition(
        computeSidePanelPosition(
          main.getBoundingClientRect(),
          row.getBoundingClientRect(),
        ),
      );
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [sidePanel, agents.length]);

  const sidePanelNode =
    sidePanel && sidePosition
      ? createPortal(
          <div
            ref={sidePanelRef}
            className="composer-model-popover composer-model-popover--side composer-model-popover--side-fixed"
            style={{ top: sidePosition.top, left: sidePosition.left }}
            data-testid="composer-model-popover-side"
          >
            <div className="composer-model-popover__side-head">
              <ProviderGlyph providerId={sidePanel.providerId} />
              <span>{sidePanel.providerLabel}</span>
            </div>
            <div className="composer-model-popover__divider" role="separator" />
            <div
              className="composer-model-popover__list"
              role="listbox"
              aria-label={`${sidePanel.providerLabel} models`}
            >
              {sidePanel.presets.map((preset) => {
                const unavailable = preset.available === false;
                return (
                  <button
                    key={preset.value}
                    type="button"
                    role="option"
                    aria-selected={preset.selected}
                    disabled={unavailable}
                    className={[
                      "composer-model-popover__preset",
                      preset.selected ? "is-selected" : "",
                      unavailable ? "is-disabled" : "",
                    ]
                      .filter(Boolean)
                      .join(" ")}
                    title={preset.comingSoonNote ?? undefined}
                    onClick={() => {
                      if (unavailable) return;
                      onSidePresetSelect(sidePanel.providerId, preset.value);
                    }}
                  >
                    <span>
                      {preset.label}
                      {preset.comingSoonNote ? (
                        <span className="composer-model-popover__soon">
                          {preset.comingSoonNote}
                        </span>
                      ) : null}
                    </span>
                    {preset.selected ? <CheckIcon /> : null}
                  </button>
                );
              })}
            </div>
            {sidePanel.efforts && sidePanel.efforts.length > 0 ? (
              <>
                <div
                  className="composer-model-popover__divider"
                  role="separator"
                />
                <ModelEffortSlider
                  efforts={sidePanel.efforts}
                  value={
                    sidePanel.selectedEffort ??
                    sidePanel.efforts[sidePanel.efforts.length - 1] ??
                    "high"
                  }
                  onChange={(effort) =>
                    onSideEffortSelect?.(sidePanel.providerId, effort)
                  }
                />
              </>
            ) : null}
          </div>,
          document.body,
        )
      : null;

  return (
    <>
      <div ref={rootRef} className="composer-model-popover-root">
        <div
          ref={mainRef}
          className="composer-model-popover composer-model-popover--main"
          data-testid="composer-model-popover"
        >
          <div className="composer-model-popover__auto">
            <div className="composer-model-popover__auto-row">
              <span className="composer-model-popover__auto-label">Auto</span>
              <button
                type="button"
                role="switch"
                aria-checked={autoEnabled}
                aria-disabled
                disabled
                className={[
                  "composer-model-popover__toggle",
                  "composer-model-popover__toggle--disabled",
                  autoEnabled ? "is-on" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                title="준비 중"
              >
                <span
                  className="composer-model-popover__toggle-thumb"
                  aria-hidden
                />
              </button>
            </div>
            <p className="composer-model-popover__auto-hint">
              Use multiple models
            </p>
          </div>
          <div className="composer-model-popover__divider" role="separator" />
          <div className="composer-model-popover__compose-head">
            <strong>Room 에이전트</strong>
            <span>복수 선택</span>
          </div>
          <div
            className="composer-model-popover__list"
            role="listbox"
            aria-label="Room agents"
          >
            {agents.map((agent) => {
              const active = sidePanel?.providerId === agent.value;
              const selected = selectedAgents.has(agent.value);
              const unavailable = agent.ready === false;
              const drillable =
                agent.drillable !== false &&
                DRILLABLE_AGENTS.has(agent.value.toLowerCase());
              return (
                <div
                  key={agent.value}
                  ref={(el) => {
                    rowRefs.current[agent.value] = el;
                  }}
                  className={[
                    "composer-model-popover__provider-row",
                    active ? "is-active" : "",
                    selected ? "is-selected" : "",
                    unavailable ? "is-disabled" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  <button
                    type="button"
                    className="composer-model-popover__agent-select"
                    disabled={unavailable}
                    aria-pressed={selected}
                    onClick={() => {
                      if (unavailable) return;
                      onAgentToggle(agent.value);
                    }}
                  >
                    <ProviderGlyph providerId={agent.value} />
                    <span className="composer-model-popover__provider-name">
                      {agent.label}
                    </span>
                    {selected ? <CheckIcon /> : null}
                  </button>
                  <button
                    type="button"
                    className="composer-model-popover__chevron-btn"
                    aria-label={`${agent.label} 모델 선택`}
                    aria-expanded={active}
                    disabled={unavailable || !drillable}
                    onClick={(event) => {
                      event.stopPropagation();
                      if (!drillable) return;
                      if (active) {
                        onSideClose();
                        return;
                      }
                      onProviderDrill(agent.value);
                    }}
                  >
                    <ChevronIcon />
                  </button>
                </div>
              );
            })}
          </div>
          <div className="composer-model-popover__divider" role="separator" />
          <div className="composer-model-popover__footer">
            <button
              type="button"
              className="composer-model-popover__action composer-model-popover__action--primary"
              onClick={onAgentsApply}
            >
              적용
            </button>
            <button
              type="button"
              className="composer-model-popover__action"
              onClick={onCancel}
            >
              취소
            </button>
          </div>
        </div>
      </div>
      {sidePanelNode}
    </>
  );
}
