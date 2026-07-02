import { describe, expect, it } from "vitest";
import {
  formatSlashDividerLabel,
  parseSlashDividerParts,
} from "./formatSlashDividerLabel";

describe("formatSlashDividerLabel", () => {
  it("formats transcript [slash] lines", () => {
    expect(
      formatSlashDividerLabel(
        "[slash] /model: Room 구성을 claude, kimi_work로 변경했습니다 (이 세션 동안 유지).",
      ),
    ).toBe(
      "/model · Room 구성을 claude, kimi_work로 변경했습니다 (이 세션 동안 유지).",
    );
  });

  it("parses slash command parts", () => {
    expect(
      parseSlashDividerParts("/logout codex: Successfully logged out"),
    ).toEqual({
      command: "/logout codex",
      message: "Successfully logged out",
    });
  });

  it("formats auth summaries", () => {
    expect(
      formatSlashDividerLabel("/logout codex: Successfully logged out"),
    ).toBe("/logout codex · Successfully logged out");
  });

  it("passes through plain prose", () => {
    expect(
      formatSlashDividerLabel("이 세션 동안 claude, kimi_work 에이전트를 사용합니다."),
    ).toBe("이 세션 동안 claude, kimi_work 에이전트를 사용합니다.");
  });
});
