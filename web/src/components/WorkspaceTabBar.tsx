import type { WorkspaceTab } from "../utils/workspaceTabs";
import { WORKSPACE_TABS } from "../utils/workspaceTabs";

type Props = {
  active: WorkspaceTab;
  onChange: (tab: WorkspaceTab) => void;
  disabled?: boolean;
  isNew?: boolean;
  trailing?: React.ReactNode;
};

export function WorkspaceTabBar({
  active,
  onChange,
  disabled,
  isNew,
  trailing,
}: Props) {
  if (isNew) {
    return (
      <div className="workspace-tab-bar">
        <span className="workspace-tab-bar__static">Transcript</span>
      </div>
    );
  }

  return (
    <div className="workspace-tab-bar">
      <div
        className="mac-segmented workspace-tab-bar__seg"
        role="tablist"
        aria-label="Workspace"
      >
        {WORKSPACE_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active === tab.id}
            className={active === tab.id ? "active" : ""}
            disabled={disabled}
            title={`${tab.label} (${tab.shortcut})`}
            onClick={() => onChange(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {trailing}
    </div>
  );
}
