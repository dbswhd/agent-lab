import { describe, expect, it } from "vitest";
import {
  SLASH_PAGE_SIZE,
  cancelMentionAtCursor,
  cancelSlashDraft,
  cycleMenuIndex,
  pageSlashHighlight,
  resolveActiveComposerMenu,
  resolveComposerMenuKeyDown,
  slashTokenOnly,
} from "./composerMenuKeyboard";

describe("slashTokenOnly", () => {
  it("matches slash-only drafts", () => {
    expect(slashTokenOnly("/")).toBe(true);
    expect(slashTokenOnly("/login")).toBe(true);
    expect(slashTokenOnly("/login hello")).toBe(false);
  });
});

describe("resolveActiveComposerMenu", () => {
  it("prefers mention over slash when both could apply", () => {
    expect(
      resolveActiveComposerMenu({
        mentionQuery: "src",
        mentionOptionCount: 2,
        value: "/login @src",
        slashOptionCount: 3,
      }),
    ).toBe("mention");
  });

  it("opens slash when value starts with slash and mention is inactive", () => {
    expect(
      resolveActiveComposerMenu({
        mentionQuery: null,
        mentionOptionCount: 0,
        value: "/log",
        slashOptionCount: 2,
      }),
    ).toBe("slash");
  });
});

describe("cycleMenuIndex", () => {
  it("wraps in both directions", () => {
    expect(cycleMenuIndex(0, 3, -1)).toBe(2);
    expect(cycleMenuIndex(2, 3, 1)).toBe(0);
  });
});

describe("pageSlashHighlight", () => {
  it("jumps by page size within bounds", () => {
    expect(pageSlashHighlight(0, 20, SLASH_PAGE_SIZE, "down")).toBe(
      SLASH_PAGE_SIZE,
    );
    expect(pageSlashHighlight(15, 20, SLASH_PAGE_SIZE, "down")).toBe(19);
    expect(pageSlashHighlight(15, 20, SLASH_PAGE_SIZE, "up")).toBe(5);
  });
});

describe("cancelSlashDraft", () => {
  it("removes only the slash token", () => {
    expect(cancelSlashDraft("/login")).toBe("");
    expect(cancelSlashDraft("/login hello")).toBe("hello");
    expect(cancelSlashDraft("hello")).toBe("hello");
  });
});

describe("cancelMentionAtCursor", () => {
  it("removes incomplete mention token at cursor", () => {
    expect(cancelMentionAtCursor("hello @fi", 9)).toEqual({
      value: "hello ",
      cursor: 6,
    });
    expect(cancelMentionAtCursor("@fi", 3)).toEqual({
      value: "",
      cursor: 0,
    });
  });
});

describe("resolveComposerMenuKeyDown", () => {
  const base = {
    shiftKey: false,
    value: "/login",
    mentionQuery: null as string | null,
    mentionOptionCount: 0,
    slashOptionCount: 3,
    cursor: 6,
  };

  it("cycles slash highlight on arrows and pages", () => {
    const down = resolveComposerMenuKeyDown({ ...base, key: "ArrowDown" });
    expect(down.handled).toBe(true);
    if (down.handled) {
      expect(down.action).toEqual({ type: "cycleSlashHighlight", delta: 1 });
    }
    const page = resolveComposerMenuKeyDown({ ...base, key: "PageDown" });
    expect(page.handled).toBe(true);
    if (page.handled) {
      expect(page.action).toEqual({
        type: "pageSlashHighlight",
        direction: "down",
      });
    }
  });

  it("picks slash on Enter when token-only", () => {
    const resolution = resolveComposerMenuKeyDown({ ...base, key: "Enter" });
    expect(resolution.handled).toBe(true);
    if (resolution.handled) {
      expect(resolution.action).toEqual({ type: "pickSlash" });
    }
  });

  it("sends on Enter when slash menu is open but body exists", () => {
    const resolution = resolveComposerMenuKeyDown({
      ...base,
      value: "/login hello",
      key: "Enter",
    });
    expect(resolution.handled).toBe(true);
    if (resolution.handled) {
      expect(resolution.action).toEqual({ type: "send" });
    }
  });

  it("cancels slash token on Escape without clearing body", () => {
    const resolution = resolveComposerMenuKeyDown({
      ...base,
      value: "/login hello",
      key: "Escape",
    });
    expect(resolution.handled).toBe(true);
    if (resolution.handled) {
      expect(resolution.action).toEqual({ type: "cancelSlash" });
    }
  });

  it("handles mention pick and cancel", () => {
    const pick = resolveComposerMenuKeyDown({
      ...base,
      value: "see @src",
      mentionQuery: "src",
      mentionOptionCount: 2,
      slashOptionCount: 0,
      key: "Enter",
    });
    expect(pick.handled).toBe(true);
    if (pick.handled) {
      expect(pick.action).toEqual({ type: "pickMention" });
    }
    const cancel = resolveComposerMenuKeyDown({
      ...base,
      value: "see @src",
      mentionQuery: "src",
      mentionOptionCount: 2,
      slashOptionCount: 0,
      cursor: 7,
      key: "Escape",
    });
    expect(cancel.handled).toBe(true);
    if (cancel.handled) {
      expect(cancel.action).toEqual({ type: "cancelMention" });
    }
  });

  it("allows Shift+Enter newline while mention menu is open", () => {
    expect(
      resolveComposerMenuKeyDown({
        ...base,
        value: "see @src",
        mentionQuery: "src",
        mentionOptionCount: 2,
        slashOptionCount: 0,
        shiftKey: true,
        key: "Enter",
      }).handled,
    ).toBe(false);
  });

  it("sends when no menu is open", () => {
    const resolution = resolveComposerMenuKeyDown({
      ...base,
      value: "hello",
      slashOptionCount: 0,
      key: "Enter",
    });
    expect(resolution.handled).toBe(true);
    if (resolution.handled) {
      expect(resolution.action).toEqual({ type: "send" });
    }
  });

  it("ignores Escape when no menu is open", () => {
    expect(
      resolveComposerMenuKeyDown({
        ...base,
        value: "hello",
        slashOptionCount: 0,
        key: "Escape",
      }).handled,
    ).toBe(false);
  });
});
