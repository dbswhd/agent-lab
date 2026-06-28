import { useState } from "react";
import { MessageMarkdown } from "../utils/messageMarkdown";
import {
  getDraftOpenPref,
  setDraftOpenPref,
} from "../utils/draftResponsePrefs";

type Props = {
  messageId: string;
  body: string;
  defaultOpen: boolean;
};

export function DraftResponseDetails({ messageId, body, defaultOpen }: Props) {
  const [open, setOpen] = useState(
    () => getDraftOpenPref(messageId) ?? defaultOpen,
  );

  return (
    <details
      className="turn-step turn-step--draft"
      open={open}
      onToggle={(event) => {
        const next = event.currentTarget.open;
        setDraftOpenPref(messageId, next);
        setOpen(next);
      }}
    >
      <summary>Draft response</summary>
      <div className="turn-step__body turn-step__body--prose turn-step__body--draft">
        <MessageMarkdown text={body} variant="transcript" />
      </div>
    </details>
  );
}
