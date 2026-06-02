import { MessageMarkdown } from "../utils/messageMarkdown";

type Props = {
  text: string;
  className?: string;
};

/** Agent dry-run / execute summary — readable markdown instead of raw pre. */
export function PlanAgentResponse({ text, className }: Props) {
  const trimmed = text.trim();
  if (!trimmed) return null;

  return (
    <div className={["plan-agent-response", className].filter(Boolean).join(" ")}>
      <MessageMarkdown text={trimmed} />
    </div>
  );
}
