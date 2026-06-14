export type DiffRowKind = "ctx" | "add" | "del" | "meta" | "header" | "pair";

export type SideBySideRow = {
  id: string;
  left: string;
  right: string;
  kind: DiffRowKind;
  hunkId?: string;
};

export type DiffHunkRef = {
  id: string;
  ref: string;
  rowId: string;
};

function lineKind(raw: string): DiffRowKind {
  if (
    raw.startsWith("diff --git ") ||
    raw.startsWith("index ") ||
    raw.startsWith("---") ||
    raw.startsWith("+++") ||
    raw.startsWith("@@")
  ) {
    return raw.startsWith("@@") ? "meta" : "header";
  }
  if (raw.startsWith("+")) return "add";
  if (raw.startsWith("-")) return "del";
  return "ctx";
}

function stripPrefix(line: string): string {
  if (line.startsWith("+") || line.startsWith("-") || line.startsWith(" ")) {
    return line.slice(1);
  }
  return line;
}

export function parseSideBySideDiff(diff: string | undefined): {
  rows: SideBySideRow[];
  hunks: DiffHunkRef[];
} {
  const lines = (diff ?? "").split("\n");
  const rows: SideBySideRow[] = [];
  const hunks: DiffHunkRef[] = [];
  let hunkId: string | undefined;
  let rowIndex = 0;

  const pushRow = (
    left: string,
    right: string,
    kind: DiffRowKind,
    rawLeft = left,
    rawRight = right,
  ) => {
    const id = `row-${rowIndex}`;
    rowIndex += 1;
    rows.push({ id, left: rawLeft, right: rawRight, kind, hunkId });
    if (kind === "meta" && hunkId) {
      const existing = hunks.find((h) => h.id === hunkId);
      if (!existing) {
        hunks.push({ id: hunkId, ref: left || right, rowId: id });
      }
    }
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    const kind = lineKind(line);

    if (line.startsWith("@@")) {
      hunkId = `${i + 1}:${line}`;
      pushRow(line, line, "meta");
      i += 1;
      continue;
    }

    if (kind === "header") {
      pushRow(line, line, "header");
      i += 1;
      continue;
    }

    if (line.startsWith("-")) {
      const dels: string[] = [];
      while (i < lines.length && (lines[i] ?? "").startsWith("-")) {
        dels.push(stripPrefix(lines[i] ?? ""));
        i += 1;
      }
      const adds: string[] = [];
      while (i < lines.length && (lines[i] ?? "").startsWith("+")) {
        adds.push(stripPrefix(lines[i] ?? ""));
        i += 1;
      }
      const pairs = Math.max(dels.length, adds.length, 1);
      for (let j = 0; j < pairs; j += 1) {
        const left = dels[j] ?? "";
        const right = adds[j] ?? "";
        const rowKind: DiffRowKind =
          left && right ? "pair" : left ? "del" : right ? "add" : "ctx";
        pushRow(
          left,
          right,
          rowKind,
          left ? `- ${left}` : "",
          right ? `+ ${right}` : "",
        );
      }
      continue;
    }

    if (line.startsWith("+")) {
      pushRow("", stripPrefix(line), "add", "", line);
      i += 1;
      continue;
    }

    const text = stripPrefix(line);
    pushRow(text, text, "ctx", line, line);
    i += 1;
  }

  return { rows, hunks };
}
