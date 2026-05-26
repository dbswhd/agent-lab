import { Fragment, type ReactNode } from "react";

const INLINE_RE =
  /(\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\))/g;

function renderInline(text: string, keyPrefix: string): ReactNode[] {
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
        <code key={key} className="bubble-inline-code">
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
  | { type: "hr" };

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
      blocks.push({ type: "heading", level, text: line.replace(/^#{1,3}\s+/, "") });
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

    const paraLines: string[] = [line];
    i += 1;
    while (i < lines.length && lines[i].trim() !== "" && !isBlockStart(lines[i])) {
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
    /^\*\*\*+$/.test(line.trim())
  );
}

function renderBlock(block: Block, index: number): ReactNode {
  const key = `b${index}`;
  switch (block.type) {
    case "heading": {
      const Tag = (`h${block.level}` as "h1" | "h2" | "h3");
      return (
        <Tag key={key} className={`bubble-md__h${block.level}`}>
          {renderInline(block.text, key)}
        </Tag>
      );
    }
    case "ul":
      return (
        <ul key={key} className="bubble-md__list">
          {block.items.map((item, j) => (
            <li key={`${key}-${j}`}>{renderInline(item, `${key}-li${j}`)}</li>
          ))}
        </ul>
      );
    case "ol":
      return (
        <ol key={key} className="bubble-md__list">
          {block.items.map((item, j) => (
            <li key={`${key}-${j}`}>{renderInline(item, `${key}-li${j}`)}</li>
          ))}
        </ol>
      );
    case "code":
      return (
        <pre key={key} className="bubble-md__pre">
          <code>{block.text}</code>
        </pre>
      );
    case "quote":
      return (
        <blockquote key={key} className="bubble-md__quote">
          {block.lines.map((ln, j) => (
            <Fragment key={`${key}-q${j}`}>
              {j > 0 && <br />}
              {renderInline(ln, `${key}-q${j}`)}
            </Fragment>
          ))}
        </blockquote>
      );
    case "hr":
      return <hr key={key} className="bubble-md__hr" />;
    case "paragraph":
      return (
        <p key={key} className="bubble-md__p">
          {block.lines.map((ln, j) => (
            <Fragment key={`${key}-p${j}`}>
              {j > 0 && <br />}
              {renderInline(ln, `${key}-p${j}`)}
            </Fragment>
          ))}
        </p>
      );
  }
}

/** Block-aware markdown for chat bubbles. */
export function MessageMarkdown({ text }: { text: string }) {
  const blocks = parseBlocks(text);
  if (blocks.length === 0) return null;
  return <div className="bubble-md">{blocks.map(renderBlock)}</div>;
}
