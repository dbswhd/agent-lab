import { Fragment, type ReactNode } from "react";

const INLINE_RE =
  /(\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\))/g;

function renderInline(
  text: string,
  keyPrefix: string,
  inlineCodeClass: string,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let i = 0;
  let m: RegExpExecArray | null;

  INLINE_RE.lastIndex = 0;
  while ((m = INLINE_RE.exec(text)) !== null) {
    if (m.index > last) {
      nodes.push(text.slice(last, m.index));
    }
    const key = `${keyPrefix}-${i++}`;
    if (m[2]) {
      nodes.push(<strong key={key}>{m[2]}</strong>);
    } else if (m[3]) {
      nodes.push(<em key={key}>{m[3]}</em>);
    } else if (m[4]) {
      nodes.push(
        <code key={key} className={inlineCodeClass || undefined}>
          {m[4]}
        </code>,
      );
    } else if (m[5] && m[6]) {
      nodes.push(
        <a key={key} href={m[6]} target="_blank" rel="noreferrer noopener">
          {m[5]}
        </a>,
      );
    }
    last = m.index + m[0].length;
  }

  if (last < text.length) {
    nodes.push(text.slice(last));
  }
  return nodes.length ? nodes : [text];
}

type Block =
  | { type: "paragraph"; lines: string[] }
  | { type: "heading"; level: 1 | 2 | 3; text: string }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[] }
  | { type: "code"; text: string }
  | { type: "quote"; lines: string[] }
  | { type: "table"; header: string[]; rows: string[][] }
  | { type: "hr" };

type MarkdownVariant = "bubble" | "transcript";

function mdClasses(variant: MarkdownVariant) {
  if (variant === "transcript") {
    return {
      root: "md",
      p: "",
      h1: "",
      h2: "",
      h3: "",
      list: "",
      pre: "",
      quote: "",
      hr: "",
      inlineCode: "",
    };
  }
  return {
    root: "bubble-md",
    p: "bubble-md__p",
    h1: "bubble-md__h1",
    h2: "bubble-md__h2",
    h3: "bubble-md__h3",
    list: "bubble-md__list",
    pre: "bubble-md__pre",
    quote: "bubble-md__quote",
    hr: "bubble-md__hr",
    inlineCode: "bubble-inline-code",
  };
}

function isTableDivider(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed.includes("|")) return false;
  return trimmed.replace(/\|/g, "").replace(/[\s:-]/g, "") === "";
}

function isTableRow(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed.includes("|")) return false;
  return trimmed.startsWith("|") || /\|.+\|/.test(trimmed);
}

function splitTableCells(line: string): string[] {
  let trimmed = line.trim();
  if (trimmed.startsWith("|")) trimmed = trimmed.slice(1);
  if (trimmed.endsWith("|")) trimmed = trimmed.slice(0, -1);
  return trimmed.split("|").map((cell) => cell.trim());
}

function parseBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      i += 1;
      continue;
    }

    if (/^```/.test(line)) {
      i += 1;
      const codeLines: string[] = [];
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        codeLines.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) i += 1;
      blocks.push({ type: "code", text: codeLines.join("\n") });
      continue;
    }

    if (/^#{1,3}\s/.test(line)) {
      const level = Math.min(3, line.match(/^#+/)![0].length) as 1 | 2 | 3;
      blocks.push({
        type: "heading",
        level,
        text: line.replace(/^#{1,3}\s+/, ""),
      });
      i += 1;
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^[-*]\s+/, ""));
        i += 1;
      }
      blocks.push({ type: "ul", items });
      continue;
    }

    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s+/, ""));
        i += 1;
      }
      blocks.push({ type: "ol", items });
      continue;
    }

    if (/^>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        quoteLines.push(lines[i].replace(/^>\s?/, ""));
        i += 1;
      }
      blocks.push({ type: "quote", lines: quoteLines });
      continue;
    }

    if (/^---+$/.test(line.trim()) || /^\*\*\*+$/.test(line.trim())) {
      blocks.push({ type: "hr" });
      i += 1;
      continue;
    }

    if (isTableRow(line) && !isTableDivider(line)) {
      const header = splitTableCells(line);
      i += 1;
      if (i < lines.length && isTableDivider(lines[i])) {
        i += 1;
      }
      const rows: string[][] = [];
      while (
        i < lines.length &&
        isTableRow(lines[i]) &&
        !isTableDivider(lines[i])
      ) {
        rows.push(splitTableCells(lines[i]));
        i += 1;
      }
      blocks.push({ type: "table", header, rows });
      continue;
    }

    const paraLines: string[] = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !isBlockStart(lines[i])
    ) {
      paraLines.push(lines[i]);
      i += 1;
    }
    blocks.push({ type: "paragraph", lines: paraLines });
  }

  return blocks;
}

function isBlockStart(line: string): boolean {
  return (
    /^```/.test(line) ||
    /^#{1,3}\s/.test(line) ||
    /^[-*]\s+/.test(line) ||
    /^\d+\.\s+/.test(line) ||
    /^>\s?/.test(line) ||
    /^---+$/.test(line.trim()) ||
    /^\*\*\*+$/.test(line.trim()) ||
    isTableRow(line)
  );
}

function renderBlock(
  block: Block,
  index: number,
  variant: MarkdownVariant,
): ReactNode {
  const key = `b${index}`;
  const c = mdClasses(variant);
  const inline = (text: string, prefix: string) =>
    renderInline(text, prefix, c.inlineCode);

  switch (block.type) {
    case "heading": {
      const Tag = `h${block.level}` as "h1" | "h2" | "h3";
      const headingClass =
        block.level === 1 ? c.h1 : block.level === 2 ? c.h2 : c.h3;
      return (
        <Tag key={key} className={headingClass || undefined}>
          {inline(block.text, key)}
        </Tag>
      );
    }
    case "ul":
      return (
        <ul key={key} className={c.list || undefined}>
          {block.items.map((item, j) => (
            <li key={`${key}-${j}`}>{inline(item, `${key}-li${j}`)}</li>
          ))}
        </ul>
      );
    case "ol":
      return (
        <ol key={key} className={c.list || undefined}>
          {block.items.map((item, j) => (
            <li key={`${key}-${j}`}>{inline(item, `${key}-li${j}`)}</li>
          ))}
        </ol>
      );
    case "code":
      return (
        <pre key={key} className={c.pre || undefined}>
          <code>{block.text}</code>
        </pre>
      );
    case "quote":
      return (
        <blockquote key={key} className={c.quote || undefined}>
          {block.lines.map((ln, j) => (
            <Fragment key={`${key}-q${j}`}>
              {j > 0 && <br />}
              {inline(ln, `${key}-q${j}`)}
            </Fragment>
          ))}
        </blockquote>
      );
    case "hr":
      return <hr key={key} className={c.hr || undefined} />;
    case "table":
      return (
        <div key={key} className="md-table-wrap">
          <table className="md-table">
            <thead>
              <tr>
                {block.header.map((cell, j) => (
                  <th key={`${key}-h${j}`}>{inline(cell, `${key}-h${j}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, rowIndex) => (
                <tr key={`${key}-r${rowIndex}`}>
                  {row.map((cell, cellIndex) => (
                    <td key={`${key}-r${rowIndex}c${cellIndex}`}>
                      {inline(cell, `${key}-r${rowIndex}c${cellIndex}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "paragraph":
      return (
        <p key={key} className={c.p || undefined}>
          {block.lines.map((ln, j) => (
            <Fragment key={`${key}-p${j}`}>
              {j > 0 && <br />}
              {inline(ln, `${key}-p${j}`)}
            </Fragment>
          ))}
        </p>
      );
  }
}

/** Block-aware markdown for chat bubbles and console transcript. */
export function MessageMarkdown({
  text,
  variant = "bubble",
}: {
  text: string;
  variant?: MarkdownVariant;
}) {
  const blocks = parseBlocks(text);
  if (blocks.length === 0) return null;
  const rootClass = mdClasses(variant).root;
  return (
    <div className={rootClass}>
      {blocks.map((block, i) => renderBlock(block, i, variant))}
    </div>
  );
}
