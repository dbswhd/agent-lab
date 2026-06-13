import { useMemo } from "react";
import { workspaceFileRawUrl, type WorkspaceFileContent } from "../api/client";
import { MessageMarkdown } from "../utils/messageMarkdown";

type Props = {
  sessionId: string;
  rootId: string;
  path: string;
  /** Text payload (from readWorkspaceFile). Not needed for images. */
  content: WorkspaceFileContent | null;
};

const IMAGE_EXTS = new Set([
  "png",
  "jpg",
  "jpeg",
  "gif",
  "webp",
  "svg",
  "bmp",
  "ico",
  "avif",
]);

function extOf(path: string): string {
  return path.split(".").pop()?.toLowerCase() ?? "";
}

/** Colorize a unified-diff blob by line prefix. */
function DiffView({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="files-diff">
      {lines.map((line, i) => {
        let cls = "files-diff__ctx";
        if (line.startsWith("+") && !line.startsWith("+++")) cls = "files-diff__add";
        else if (line.startsWith("-") && !line.startsWith("---")) cls = "files-diff__del";
        else if (line.startsWith("@@")) cls = "files-diff__hunk";
        else if (
          line.startsWith("diff ") ||
          line.startsWith("+++") ||
          line.startsWith("---") ||
          line.startsWith("index ")
        )
          cls = "files-diff__meta";
        return (
          <div key={i} className={`files-diff__line ${cls}`}>
            {line || " "}
          </div>
        );
      })}
    </div>
  );
}

/** Renders a file by type: image / markdown / diff / html / plain text. */
export function FilePreview({ sessionId, rootId, path, content }: Props) {
  const ext = useMemo(() => extOf(path), [path]);

  // Images don't need the text payload — point straight at the raw endpoint.
  if (IMAGE_EXTS.has(ext)) {
    return (
      <div className="files-preview files-preview--image">
        <img
          className="files-img"
          src={workspaceFileRawUrl(sessionId, rootId, path)}
          alt={path}
        />
      </div>
    );
  }

  if (content == null) {
    return <div className="files-hint">loading…</div>;
  }
  if (content.kind !== "text") {
    return (
      <div className="files-hint">
        {content.kind === "large" ? "Too large to preview" : "Binary file"} (
        {content.size.toLocaleString()} bytes)
      </div>
    );
  }

  const text = content.content ?? "";

  if (ext === "md" || ext === "markdown") {
    return (
      <div className="files-preview files-preview--md">
        <MessageMarkdown text={text} />
      </div>
    );
  }
  if (ext === "diff" || ext === "patch") {
    return <DiffView text={text} />;
  }
  if (ext === "html" || ext === "htm") {
    return (
      <iframe
        className="files-preview files-preview--html"
        title={path}
        sandbox=""
        srcDoc={text}
      />
    );
  }
  return <pre className="files-pre">{text}</pre>;
}
