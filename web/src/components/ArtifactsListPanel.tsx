import type { RoomArtifact } from "../api/client";
import { Avatar } from "./Avatar";
import type { AgentRole } from "../utils/transcript";

type Props = {
  items: RoomArtifact[];
};

function artifactExt(art: RoomArtifact): string {
  const path = art.path ?? "";
  const ext = path.split(".").pop()?.toLowerCase();
  if (ext && ["pdf", "json", "ts", "tsx", "png", "md"].includes(ext)) {
    return ext === "tsx" ? "ts" : ext;
  }
  if (art.kind === "diff") return "json";
  return "file";
}

function artifactName(art: RoomArtifact): string {
  if (art.path) return art.path.split("/").pop() ?? art.path;
  return `${art.producer}-${art.kind}`;
}

function formatMeta(art: RoomArtifact): string {
  const parts: string[] = [];
  if (art.kind) parts.push(art.kind);
  if (art.turn != null) parts.push(`R${art.turn}`);
  if (art.ts) parts.push(art.ts);
  return parts.join(" · ") || art.summary || "—";
}

/** Artifacts tab — prototype `artifacts-list` / `artifact-card`. */
export function ArtifactsListPanel({ items }: Props) {
  return (
    <div className="artifacts-list">
      <div className="artifacts-list__head">
        <svg
          viewBox="0 0 24 24"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth={1.7}
          strokeLinecap="round"
          aria-hidden
        >
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
          <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
        </svg>
        Session artifacts
      </div>

      {items.length === 0 ? (
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden>
            <svg
              viewBox="0 0 24 24"
              width="24"
              height="24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinecap="round"
            >
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
              <path d="M14 2v6h6" />
            </svg>
          </span>
          <span className="empty-state__title">저장된 산출물 없음</span>
          <span className="empty-state__hint">
            실행 중 생성된 PDF, diff, 로그 등이 여기에 모입니다.
          </span>
        </div>
      ) : (
        [...items].reverse().map((art) => {
          const ext = artifactExt(art);
          const producer = art.producer as AgentRole;
          return (
            <div
              key={art.id ?? art.path ?? `${art.producer}-${art.kind}`}
              className="artifact-card"
            >
              <div className={`artifact-card__type artifact-card__type--${ext}`}>
                {ext.toUpperCase()}
              </div>
              <div className="artifact-card__main">
                <span className="artifact-card__name">{artifactName(art)}</span>
                <span className="artifact-card__meta">{formatMeta(art)}</span>
                {art.summary ? (
                  <span className="artifact-card__meta">{art.summary}</span>
                ) : null}
              </div>
              <div className="artifact-card__agent">
                <Avatar role={producer} size={20} />
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
