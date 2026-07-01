import { useEffect, useMemo } from "react";
import { filterAgentMentions } from "../utils/composerAgentMention";

type AgentRow = {
  id: string;
  label: string;
};

export type MentionMenuOption = {
  key: string;
  section: "agents" | "files";
  title: string;
  description: string;
  token: string;
};

type Props = {
  query: string;
  paths: string[];
  agents?: readonly AgentRow[];
  loading?: boolean;
  onPickPath: (path: string) => void;
  onPickAgent: (agentId: string) => void;
  highlightedIndex?: number;
  onHighlightChange?: (index: number) => void;
  onOptionsChange?: (options: MentionMenuOption[]) => void;
};

const SECTION_LABELS = {
  agents: "Agents",
  files: "Files",
} as const;

export function ComposerMentionMenu({
  query,
  paths,
  agents = [],
  loading = false,
  onPickPath,
  onPickAgent,
  highlightedIndex = 0,
  onHighlightChange,
  onOptionsChange,
}: Props) {
  const q = query.toLowerCase();
  const agentRows = filterAgentMentions(query, agents);
  const filteredPaths = paths
    .filter((p) => !q || p.toLowerCase().includes(q))
    .slice(0, 8);

  const sections = useMemo(() => {
    const agentsSection: MentionMenuOption[] = agentRows.map((agent) => ({
      key: `agent:${agent.id}`,
      section: "agents",
      title: `@${agent.id}`,
      description: `이 턴은 ${agent.label}만 응답합니다.`,
      token: agent.id,
    }));
    const filesSection: MentionMenuOption[] = filteredPaths.map((path) => ({
      key: `file:${path}`,
      section: "files",
      title: `@${path}`,
      description: "파일 경로를 메시지에 포함합니다.",
      token: path,
    }));
    const out: Array<{ key: "agents" | "files"; items: MentionMenuOption[] }> =
      [];
    if (agentsSection.length > 0) {
      out.push({ key: "agents", items: agentsSection });
    }
    if (filesSection.length > 0 || loading) {
      out.push({ key: "files", items: filesSection });
    }
    return out;
  }, [agentRows, filteredPaths, loading]);

  const flatOptions = useMemo(
    () => sections.flatMap((section) => section.items),
    [sections],
  );

  useEffect(() => {
    onOptionsChange?.(flatOptions);
  }, [flatOptions, onOptionsChange]);

  useEffect(() => {
    if (highlightedIndex >= flatOptions.length && flatOptions.length > 0) {
      onHighlightChange?.(flatOptions.length - 1);
    }
  }, [flatOptions.length, highlightedIndex, onHighlightChange]);

  if (sections.length === 0) return null;

  let flatIndex = 0;

  return (
    <div
      className="slash-command-menu composer-mention-menu"
      role="listbox"
      aria-label="Mentions"
      data-testid="composer-mention-menu"
    >
      <div className="slash-command-menu__main">
        <div className="slash-command-menu__scroll">
          {sections.map((section) => (
            <section
              key={section.key}
              className="slash-command-menu__section"
              aria-label={SECTION_LABELS[section.key]}
            >
              <header className="slash-command-menu__section-label">
                {SECTION_LABELS[section.key]}
              </header>
              <ul className="slash-command-menu__list">
                {section.items.map((option) => {
                  const index = flatIndex;
                  flatIndex += 1;
                  return (
                    <li key={option.key}>
                      <button
                        type="button"
                        className={[
                          "slash-command-menu__item",
                          index === highlightedIndex ? "is-active" : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        role="option"
                        aria-selected={index === highlightedIndex}
                        onMouseEnter={() => onHighlightChange?.(index)}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => {
                          if (option.section === "agents") {
                            onPickAgent(option.token);
                          } else {
                            onPickPath(option.token);
                          }
                        }}
                      >
                        <span className="slash-command-menu__name">
                          {option.title}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
              {section.key === "files" &&
              loading &&
              section.items.length === 0 ? (
                <p className="slash-command-menu__empty">Loading files…</p>
              ) : null}
            </section>
          ))}
          {!loading && flatOptions.length === 0 ? (
            <p className="slash-command-menu__empty">일치하는 항목 없음</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
