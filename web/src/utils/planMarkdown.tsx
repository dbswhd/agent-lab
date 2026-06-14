import type { ReactNode } from "react";
import { PlanActionCard, PlanGateLine } from "../components/PlanActionCard";
import { PlanMarkdownBody } from "./planMarkdownBody";
import { extractChatLineRefs, stripPlanRefAnnotations } from "./planTextFormat";

type RefSplit = { body: string; refs: number[] };

export type PlanBlock =
  | { type: "h2"; text: string }
  | { type: "h3"; text: string }
  | { type: "p"; text: string; refs: number[] }
  | { type: "item"; text: string; refs: number[] }
  | { type: "agent"; name: string; text: string; refs: number[] }
  | {
      type: "action";
      n: number;
      what?: string;
      where?: string;
      verify?: string;
      refs: number[];
    }
  | { type: "gate"; n: number; text: string; refs: number[] };

function splitRefs(raw: string): RefSplit {
  return {
    body: stripPlanRefAnnotations(raw),
    refs: extractChatLineRefs(raw),
  };
}

function isCommentLine(line: string): boolean {
  const t = line.trim();
  return t.startsWith("<!--") || t === "-->" || t.endsWith("-->");
}

function skipCommentBlock(lines: string[], start: number): number {
  let i = start;
  while (i < lines.length) {
    if (lines[i].includes("-->")) return i + 1;
    i += 1;
  }
  return i;
}

const FIELD_LINE = /^\s*-\s*(무엇을|어디서|검증):\s*(.*)$/;
const AGENT_LINE = /^-\s*(?:\*\*)?(Cursor|Codex|Claude)(?:\*\*)?:\s*(.+)$/i;
const GATE_LINE = /^(\d+)\.\s+(.+)$/;

export function parsePlanMarkdown(text: string): PlanBlock[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: PlanBlock[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "" || isCommentLine(line)) {
      if (isCommentLine(line) && !line.includes("-->")) {
        i = skipCommentBlock(lines, i);
      } else {
        i += 1;
      }
      continue;
    }

    if (/^##\s+/.test(line) && !/^###\s+/.test(line)) {
      blocks.push({ type: "h2", text: line.replace(/^##\s+/, "").trim() });
      i += 1;
      continue;
    }

    if (/^###\s+/.test(line)) {
      blocks.push({ type: "h3", text: line.replace(/^###\s+/, "").trim() });
      i += 1;
      continue;
    }

    if (/^\d+\.$/.test(line.trim())) {
      const n = Number(line.trim().replace(".", ""));
      i += 1;
      let what: string | undefined;
      let where: string | undefined;
      let verify: string | undefined;
      const refs: number[] = [];
      while (i < lines.length && FIELD_LINE.test(lines[i])) {
        const m = lines[i].match(FIELD_LINE)!;
        const part = splitRefs(m[2]);
        refs.push(...part.refs);
        if (m[1] === "무엇을") what = part.body;
        if (m[1] === "어디서") where = part.body;
        if (m[1] === "검증") verify = part.body;
        i += 1;
      }
      blocks.push({
        type: "action",
        n,
        what,
        where,
        verify,
        refs: [...new Set(refs)].sort((a, b) => a - b),
      });
      continue;
    }

    const gate = line.match(GATE_LINE);
    if (gate && !line.match(/^\d+\.$/)) {
      const part = splitRefs(gate[2]);
      blocks.push({
        type: "gate",
        n: Number(gate[1]),
        text: part.body,
        refs: part.refs,
      });
      i += 1;
      continue;
    }

    const agent = line.match(AGENT_LINE);
    if (agent) {
      const part = splitRefs(agent[2]);
      blocks.push({
        type: "agent",
        name: agent[1],
        text: part.body,
        refs: part.refs,
      });
      i += 1;
      continue;
    }

    if (/^-\s+/.test(line)) {
      const part = splitRefs(line.replace(/^-\s+/, ""));
      blocks.push({ type: "item", text: part.body, refs: part.refs });
      i += 1;
      continue;
    }

    const paraLines: string[] = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^##\s+/.test(lines[i]) &&
      !/^###\s+/.test(lines[i]) &&
      !/^-\s+/.test(lines[i]) &&
      !/^\d+\./.test(lines[i]) &&
      !isCommentLine(lines[i])
    ) {
      paraLines.push(lines[i]);
      i += 1;
    }
    const joined = paraLines.join(" ").trim();
    const part = splitRefs(joined);
    if (part.body) {
      blocks.push({ type: "p", text: part.body, refs: part.refs });
    }
  }

  return blocks;
}

/** Hidden in plan tab when PlanExecutePanel shows the same sections (new format). */
const EXECUTE_SECTION_HEADERS = new Set(["지금 실행"]);

function isExecuteRoadmapSection(title: string): boolean {
  return title === "실행 순서 (이후)" || title.startsWith("실행 순서");
}

export function filterExecuteSections(blocks: PlanBlock[]): PlanBlock[] {
  let skip = false;
  const out: PlanBlock[] = [];
  for (const block of blocks) {
    if (block.type === "h2") {
      skip =
        EXECUTE_SECTION_HEADERS.has(block.text) ||
        isExecuteRoadmapSection(block.text);
      if (!skip) out.push(block);
      continue;
    }
    if (!skip) out.push(block);
  }
  return out;
}

export type PlanMarkdownOptions = {
  skipExecuteSections?: boolean;
};

export function renderPlanMarkdown(
  text: string,
  onRefClick?: (line: number) => void,
  options?: PlanMarkdownOptions,
): ReactNode {
  let blocks = parsePlanMarkdown(text);
  if (options?.skipExecuteSections) {
    blocks = filterExecuteSections(blocks);
  }
  let section = "";

  return (
    <article className="plan-doc">
      {blocks.map((block, index) => {
        const key = `plan-${index}`;
        switch (block.type) {
          case "h2":
            section = block.text;
            return (
              <h2 key={key} className="plan-doc__h2">
                {block.text}
              </h2>
            );
          case "h3":
            return (
              <h3 key={key} className="plan-doc__h3">
                {block.text}
              </h3>
            );
          case "p":
            return (
              <p key={key} className="plan-doc__p">
                <PlanMarkdownBody
                  text={block.text}
                  refs={block.refs}
                  onRefClick={onRefClick}
                />
              </p>
            );
          case "item":
            return (
              <p key={key} className="plan-doc__item">
                <PlanMarkdownBody
                  text={block.text}
                  refs={block.refs}
                  onRefClick={onRefClick}
                />
              </p>
            );
          case "agent":
            return (
              <div key={key} className="plan-doc__agent">
                <span className="plan-doc__agent-name">{block.name}</span>
                <span className="plan-doc__agent-body">
                  <PlanMarkdownBody
                    text={block.text}
                    refs={block.refs}
                    onRefClick={onRefClick}
                  />
                </span>
              </div>
            );
          case "gate":
            return (
              <PlanGateLine
                key={key}
                n={block.n}
                text={block.text}
                onRefClick={onRefClick}
                variant={section.includes("지금 실행") ? "now" : "default"}
              />
            );
          case "action":
            return (
              <PlanActionCard
                key={key}
                n={block.n}
                what={block.what}
                where={block.where}
                verify={block.verify}
                refs={block.refs}
                onRefClick={onRefClick}
                variant={section.includes("지금 실행") ? "now" : "default"}
              />
            );
          default:
            return null;
        }
      })}
    </article>
  );
}
