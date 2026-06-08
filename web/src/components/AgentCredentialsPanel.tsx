import { useCallback, useEffect, useState } from "react";
import { Avatar } from "./Avatar";
import {
  fetchCredentials,
  putCredentials,
  type AgentCredentialRow,
  type CredentialProviderId,
  type CredentialsPatch,
} from "../api/client";
import type { AgentRole } from "../utils/transcript";

type SlotDraft = {
  primary: string;
  fallback: string;
  primary_label: string;
  fallback_label: string;
  primaryDirty: boolean;
  fallbackDirty: boolean;
};

const PROVIDER_ORDER: CredentialProviderId[] = ["cursor", "claude", "codex"];

function emptyDraft(): SlotDraft {
  return {
    primary: "",
    fallback: "",
    primary_label: "메인",
    fallback_label: "서브",
    primaryDirty: false,
    fallbackDirty: false,
  };
}

function draftFromRow(row: AgentCredentialRow): SlotDraft {
  return {
    primary: "",
    fallback: "",
    primary_label: row.primary_label || "메인",
    fallback_label: row.fallback_label || "서브",
    primaryDirty: false,
    fallbackDirty: false,
  };
}

function patchFromDrafts(
  drafts: Record<CredentialProviderId, SlotDraft>,
): CredentialsPatch {
  const patch: CredentialsPatch = {};
  for (const id of PROVIDER_ORDER) {
    const d = drafts[id];
    const slot: CredentialsPatch[CredentialProviderId] = {
      primary_label: d.primary_label,
      fallback_label: d.fallback_label,
    };
    if (d.primaryDirty) slot.primary = d.primary;
    if (d.fallbackDirty) slot.fallback = d.fallback;
    patch[id] = slot;
  }
  return patch;
}

export function AgentCredentialsPanel() {
  const [rows, setRows] = useState<AgentCredentialRow[]>([]);
  const [drafts, setDrafts] = useState<Record<
    CredentialProviderId,
    SlotDraft
  > | null>(null);
  const [path, setPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveHint, setSaveHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchCredentials();
      setRows(res.agents ?? []);
      setPath(res.path ?? null);
      const next: Record<CredentialProviderId, SlotDraft> = {
        cursor: emptyDraft(),
        claude: emptyDraft(),
        codex: emptyDraft(),
      };
      for (const row of res.agents ?? []) {
        next[row.id] = draftFromRow(row);
      }
      setDrafts(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "불러오기 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const updateDraft = (
    id: CredentialProviderId,
    patch: Partial<SlotDraft>,
  ) => {
    setDrafts((prev) => {
      if (!prev) return prev;
      return { ...prev, [id]: { ...prev[id], ...patch } };
    });
    setSaveHint(null);
  };

  const save = async () => {
    if (!drafts) return;
    setSaveBusy(true);
    setSaveHint(null);
    setError(null);
    try {
      const res = await putCredentials(patchFromDrafts(drafts));
      setRows(res.agents ?? []);
      setPath(res.path ?? null);
      const next: Record<CredentialProviderId, SlotDraft> = {
        cursor: emptyDraft(),
        claude: emptyDraft(),
        codex: emptyDraft(),
      };
      for (const row of res.agents ?? []) {
        next[row.id] = draftFromRow(row);
      }
      setDrafts(next);
      setSaveHint("저장됨 ✓ — 메인 실패 시 서브 키로 자동 전환");
    } catch (e) {
      setSaveHint(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaveBusy(false);
    }
  };

  if (loading && !drafts) {
    return <p className="settings-hint">API 키 불러오는 중…</p>;
  }

  if (error && !drafts) {
    return (
      <div className="settings-credentials__error">
        <p className="settings-hint">{error}</p>
        <button type="button" className="btn btn--sm" onClick={() => void load()}>
          다시 시도
        </button>
      </div>
    );
  }

  if (!drafts) return null;

  return (
    <div className="settings-credentials">
      <p className="settings-hint">
        메인 계정 API 키를 먼저 사용합니다. 인증·한도 오류 시 서브 키로 자동
        전환됩니다. Claude/Codex는 CLI OAuth 로그인도 그대로 사용할 수 있습니다.
      </p>

      <div className="agent-settings__toolbar">
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={saveBusy}
          onClick={() => void save()}
        >
          {saveBusy ? "저장 중…" : "API 키 저장"}
        </button>
        {saveHint ? <p className="settings-save-hint">{saveHint}</p> : null}
      </div>

      <div className="agent-settings__grid">
        {PROVIDER_ORDER.map((id) => {
          const row = rows.find((r) => r.id === id);
          const d = drafts[id];
          if (!row || !d) return null;
          const hasAny = row.has_primary || row.has_fallback;
          return (
            <fieldset
              key={id}
              className={[
                "agent-settings__card",
                "settings-credentials__card",
                hasAny ? undefined : "agent-settings__card--dim",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <legend className="agent-settings__legend">
                <Avatar role={id as AgentRole} size={18} />
                {row.label}
                <span className="agent-settings__model">
                  {row.env_primary}
                  {row.has_fallback ? ` · ${row.env_fallback}` : ""}
                </span>
              </legend>

              <label className="agent-settings__field">
                <span>메인 라벨</span>
                <input
                  className="settings-credentials__input"
                  type="text"
                  value={d.primary_label}
                  placeholder="메인"
                  onChange={(e) =>
                    updateDraft(id, { primary_label: e.target.value })
                  }
                />
              </label>

              <label className="agent-settings__field">
                <span>메인 API 키</span>
                <input
                  className="settings-credentials__input"
                  type="password"
                  autoComplete="off"
                  placeholder={
                    row.primary_masked
                      ? `등록됨 ${row.primary_masked}`
                      : `${row.env_primary} (미설정)`
                  }
                  value={d.primary}
                  onChange={(e) =>
                    updateDraft(id, {
                      primary: e.target.value,
                      primaryDirty: true,
                    })
                  }
                />
                {row.has_primary && !d.primaryDirty ? (
                  <span className="settings-credentials__masked">
                    {row.primary_masked ?? "설정됨"}
                  </span>
                ) : null}
              </label>

              <label className="agent-settings__field">
                <span>서브 라벨</span>
                <input
                  className="settings-credentials__input"
                  type="text"
                  value={d.fallback_label}
                  placeholder="서브"
                  onChange={(e) =>
                    updateDraft(id, { fallback_label: e.target.value })
                  }
                />
              </label>

              <label className="agent-settings__field">
                <span>서브 API 키 (fallback)</span>
                <input
                  className="settings-credentials__input"
                  type="password"
                  autoComplete="off"
                  placeholder={
                    row.fallback_masked
                      ? `등록됨 ${row.fallback_masked}`
                      : `${row.env_fallback} (선택)`
                  }
                  value={d.fallback}
                  onChange={(e) =>
                    updateDraft(id, {
                      fallback: e.target.value,
                      fallbackDirty: true,
                    })
                  }
                />
                {row.has_fallback && !d.fallbackDirty ? (
                  <span className="settings-credentials__masked">
                    {row.fallback_masked ?? "설정됨"}
                  </span>
                ) : null}
              </label>
            </fieldset>
          );
        })}
      </div>

      {path ? (
        <p className="settings-hint settings-credentials__path" title={path}>
          저장 위치: <code>{path}</code>
        </p>
      ) : null}
    </div>
  );
}
