import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
};

/** Tasks > human gate wrapper. Existing gate components remain the source of behavior. */
export function HumanGatePanel({ children }: Props) {
  return <section className="human-gate-panel">{children}</section>;
}
