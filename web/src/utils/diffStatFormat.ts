export type DiffStatFileRow = {
  path: string;
  adds: number;
  dels: number;
};

export type ParsedDiffStat = {
  files: DiffStatFileRow[];
  summary: string | null;
};

/** Per-file: `path | 19 + 7 -` (legacy) or `path | +19 -7` */
const FILE_LINE = /^ (.+?) \| (?:(?:\d+\s+\+\s*\d+\s+-)|(?:\+\d+\s+-\d+))$/;

function parseFileLine(line: string): DiffStatFileRow | null {
  const trimmed = line.trimEnd();
  const legacy = trimmed.match(/^(.+?) \| (\d+)\s+\+\s*(\d+)\s+-$/);
  if (legacy) {
    return {
      path: legacy[1].trim(),
      adds: Number(legacy[2]),
      dels: Number(legacy[3]),
    };
  }
  const compact = trimmed.match(/^(.+?) \| \+(\d+) -(\d+)$/);
  if (compact) {
    return {
      path: compact[1].trim(),
      adds: Number(compact[2]),
      dels: Number(compact[3]),
    };
  }
  return null;
}

export function parseDiffStat(text: string): ParsedDiffStat | null {
  const raw = text.trim();
  if (!raw) return null;

  const lines = raw.split("\n").map((line) => line.trimEnd());
  const files: DiffStatFileRow[] = [];
  let summary: string | null = null;

  for (const line of lines) {
    if (!line.trim()) continue;
    if (/files?(\(s\))? changed/i.test(line)) {
      summary = line.trim();
      continue;
    }
    if (FILE_LINE.test(line) || line.includes(" | ")) {
      const row = parseFileLine(line.trim());
      if (row) files.push(row);
    }
  }

  if (!files.length && !summary) return null;
  return { files, summary };
}
