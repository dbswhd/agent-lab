export type DiffRowKind = "ctx" | "add" | "del" | "meta" | "header" | "pair";

export type WordSegment = { text: string; changed: boolean };

export type SideBySideRow = {
  id: string;
  left: string;
  right: string;
  kind: DiffRowKind;
  hunkId?: string;
  /** Word-level diff within a "pair" row (aligned del+add). */
  leftSegments?: WordSegment[];
  rightSegments?: WordSegment[];
};

export type DiffHunkRef = {
  id: string;
  ref: string;
  rowId: string;
};

const MAX_WORD_DIFF_TOKENS = 4000;

function tokenize(text: string): string[] {
  return text.match(/\s+|[^\s\w]+|\w+/g) ?? [];
}

function tokensEqual(a: string, b: string): boolean {
  return a === b;
}

/** Suffix LCS length table: table[i][j] = LCS length of a[i:] and b[j:]. */
function lcsTable(a: string[], b: string[]): number[][] {
  const table: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i][j] = tokensEqual(a[i], b[j])
        ? table[i + 1][j + 1] + 1
        : Math.max(table[i + 1][j], table[i][j + 1]);
    }
  }
  return table;
}

function diffTokenFlags(
  a: string[],
  b: string[],
): { leftFlags: boolean[]; rightFlags: boolean[] } {
  const table = lcsTable(a, b);
  const leftFlags: boolean[] = [];
  const rightFlags: boolean[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (tokensEqual(a[i], b[j])) {
      leftFlags.push(false);
      rightFlags.push(false);
      i += 1;
      j += 1;
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      leftFlags.push(true);
      i += 1;
    } else {
      rightFlags.push(true);
      j += 1;
    }
  }
  while (i < a.length) {
    leftFlags.push(true);
    i += 1;
  }
  while (j < b.length) {
    rightFlags.push(true);
    j += 1;
  }
  return { leftFlags, rightFlags };
}

function toSegments(tokens: string[], flags: boolean[]): WordSegment[] {
  const segments: WordSegment[] = [];
  for (const [index, token] of tokens.entries()) {
    const changed = flags[index] ?? false;
    const last = segments[segments.length - 1];
    if (last && last.changed === changed) {
      last.text += token;
    } else {
      segments.push({ text: token, changed });
    }
  }
  return segments;
}

/** Word-level diff for an aligned del/add pair — highlights only the tokens
 *  that actually changed, not the whole line. */
export function wordDiffSegments(
  left: string,
  right: string,
): { leftSegments: WordSegment[]; rightSegments: WordSegment[] } {
  const leftTokens = tokenize(left);
  const rightTokens = tokenize(right);
  if (leftTokens.length * rightTokens.length > MAX_WORD_DIFF_TOKENS) {
    return {
      leftSegments: [{ text: left, changed: true }],
      rightSegments: [{ text: right, changed: true }],
    };
  }
  const { leftFlags, rightFlags } = diffTokenFlags(leftTokens, rightTokens);
  return {
    leftSegments: toSegments(leftTokens, leftFlags),
    rightSegments: toSegments(rightTokens, rightFlags),
  };
}

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
    segments?: { leftSegments: WordSegment[]; rightSegments: WordSegment[] },
  ) => {
    const id = `row-${rowIndex}`;
    rowIndex += 1;
    rows.push({
      id,
      left: rawLeft,
      right: rawRight,
      kind,
      hunkId,
      ...segments,
    });
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
          rowKind === "pair" ? wordDiffSegments(left, right) : undefined,
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
