import type { ToolPanelTab } from "../utils/workspaceTabs";
import { messages } from "../i18n/messages";
import type { Locale } from "../i18n/locale";

const TOOL_TABS: readonly ToolPanelTab[] = [
  "plan",
  "background",
  "diff",
  "files",
  "preview",
  "terminal",
];

type Props = {
  readonly active: ToolPanelTab;
  readonly onChange: (tab: ToolPanelTab) => void;
  readonly locale: Locale;
};

export function ToolPanelTabs({ active, onChange, locale }: Props) {
  const msg = messages(locale);

  return (
    <div className="tool-panel-tabs" role="tablist" aria-label="Tools">
      {TOOL_TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          role="tab"
          aria-selected={active === tab}
          className={active === tab ? "is-active" : ""}
          onClick={() => onChange(tab)}
        >
          {msg[tab]}
        </button>
      ))}
    </div>
  );
}
