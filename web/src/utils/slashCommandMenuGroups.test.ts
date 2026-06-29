import { describe, expect, it } from "vitest";
import type { SlashCommandRecord } from "../api/client";
import {
  buildSlashMenuSections,
  filterSlashCommands,
  groupSlashMenuCommands,
  slashMenuGroupKey,
} from "./slashCommandMenuGroups";

const skill: SlashCommandRecord = {
  id: "skill:loop",
  slash: "/loop",
  label: "Loop",
  description: "Run a loop skill",
  kind: "agent_invoke",
  source: "skill",
};

const plugin: SlashCommandRecord = {
  id: "plugin:review",
  slash: "/code-review",
  label: "Code review",
  description: "Review changes",
  kind: "plugin",
};

const mode: SlashCommandRecord = {
  id: "plan",
  slash: "/plan",
  label: "Plan",
  description: "Enter plan mode",
  kind: "server",
};

describe("slashCommandMenuGroups", () => {
  it("groups skills, commands, and modes", () => {
    expect(slashMenuGroupKey(skill)).toBe("skills");
    expect(slashMenuGroupKey(plugin)).toBe("commands");
    expect(slashMenuGroupKey(mode)).toBe("modes");
  });

  it("caps visible rows until expanded", () => {
    const commands = Array.from({ length: 5 }, (_, i) => ({
      ...plugin,
      id: `plugin:${i}`,
      slash: `/cmd-${i}`,
      label: `Cmd ${i}`,
    }));
    const sections = buildSlashMenuSections(commands, "", {
      skills: true,
      commands: false,
      modes: true,
    });
    expect(sections).toHaveLength(1);
    expect(sections[0]?.items).toHaveLength(3);
    expect(sections[0]?.hiddenCount).toBe(2);
  });

  it("shows all matches while filtering", () => {
    const commands = [skill, plugin, mode];
    expect(filterSlashCommands(commands, "plan")).toEqual([mode]);
    const sections = buildSlashMenuSections(commands, "plan", {
      skills: false,
      commands: false,
      modes: false,
    });
    expect(sections[0]?.items).toEqual([mode]);
    expect(sections[0]?.hiddenCount).toBe(0);
  });

  it("sorts grouped commands by display name", () => {
    const groups = groupSlashMenuCommands([
      { ...plugin, slash: "/zebra", label: "Zebra", kind: "plugin" },
      { ...plugin, id: "b", slash: "/alpha", label: "Alpha", kind: "plugin" },
    ]);
    expect(groups.commands.map((row) => row.slash)).toEqual(["/alpha", "/zebra"]);
  });
});
