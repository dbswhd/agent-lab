import { useCallback, useEffect, useState } from "react";
import { Avatar } from "./Avatar";
import {
  captureCodexOAuth,
  clearCodexOAuthSlot,
  fetchCodexOAuth,
  fetchCredentials,
  probeCodexOAuth,
  putCodexOAuthMeta,
  putCredentials,
  type AgentCredentialRow,
  type CodexOAuthProfileProbe,
  type CodexOAuthResponse,
  type CodexOAuthSlot,
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
  drafts: Record<"cursor", SlotDraft>,
): CredentialsPatch {
  const d = drafts.cursor;
  const patch: CredentialsPatch = {
    cursor: {
      primary_label: d.primary_label,
      fallback_label: d.fallback_label,
    },
  };
  if (d.primaryDirty) patch.cursor!.primary = d.primary;
  if (d.fallbackDirty) patch.cursor!.fallback = d.fallback;
  return patch;
}

function OAuthAgentCard({
  id,
  title,
  loginHint,
}: {
  id: "claude" | "codex";
  title: string;
  loginHint: string;
}) {
  return (
    <fieldset className="agent-settings__card settings-credentials__card settings-credentials__card--oauth">
      <legend className="agent-settings__legend">
        <Avatar role={id as AgentRole} size={18} />
        {title}
        <span className="agent-settings__model">CLI OAuth</span>
      </legend>
      <p className="settings-hint settings-credentials__oauth-hint">
        Room은 API 키 없이 <strong>OAuth만</strong> 사용합니다.{" "}
        <code>{loginHint}</code>
      </p>
    </fieldset>
  );
}

function CodexOAuthCard() {
  const [meta, setMeta] = useState<CodexOAuthResponse | null>(null);
  const [primaryLabel, setPrimaryLabel] = useState("메인");
  const [fallbackLabel, setFallbackLabel] = useState("서브");
  const [busy, setBusy] = useState<CodexOAuthSlot | "meta" | "probe" | null>(
    null,
  );
  const [probes, setProbes] = useState<CodexOAuthProfileProbe[] | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchCodexOAuth();
      setMeta(res);
      setPrimaryLabel(res.primary_label || "메인");
      setFallbackLabel(res.fallback_label || "서브");
    } catch (e) {
      setError(e instanceof Error ? e.message : "불러오기 실패");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const saveLabels = async () => {
    setBusy("meta");
    setHint(null);
    try {
      const res = await putCodexOAuthMeta({
        primary_label: primaryLabel,
        fallback_label: fallbackLabel,
      });
      setMeta(res);
      setHint("라벨 저장됨 ✓");
    } catch (e) {
      setHint(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setBusy(null);
    }
  };

  const capture = async (slot: CodexOAuthSlot) => {
    setBusy(slot);
    setHint(null);
    try {
      const label = slot === "primary" ? primaryLabel : fallbackLabel;
      const res = await captureCodexOAuth(slot, label);
      setMeta(res);
      setHint(
        slot === "primary"
          ? "메인 Codex OAuth 캡처됨 ✓"
          : "서브 Codex OAuth 캡처됨 ✓",
      );
    } catch (e) {
      setHint(e instanceof Error ? e.message : "캡처 실패");
    } finally {
      setBusy(null);
    }
  };

  const probe = async () => {
    setBusy("probe");
    setHint(null);
    try {
      const res = await probeCodexOAuth();
      setMeta(res);
      setProbes(res.profiles ?? []);
      setHint(
        res.probe_ok
          ? "Codex OAuth 프로필 검증 ✓"
          : "일부 프로필 검증 실패 — codex login 후 재캡처",
      );
    } catch (e) {
      setHint(e instanceof Error ? e.message : "검증 실패");
    } finally {
      setBusy(null);
    }
  };

  const clear = async (slot: CodexOAuthSlot) => {
    setBusy(slot);
    setHint(null);
    try {
      const res = await clearCodexOAuthSlot(slot);
      setMeta(res);
      setHint(`${slot === "primary" ? "메인" : "서브"} 프로필 삭제됨`);
    } catch (e) {
      setHint(e instanceof Error ? e.message : "삭제 실패");
    } finally {
      setBusy(null);
    }
  };

  return (
    <fieldset className="agent-settings__card settings-credentials__card settings-credentials__card--oauth">
      <legend className="agent-settings__legend">
        <Avatar role="codex" size={18} />
        Codex
        <span className="agent-settings__model">ChatGPT OAuth ×2</span>
      </legend>

      <p className="settings-hint settings-credentials__oauth-hint">
        1) 터미널 <code>codex login</code> (계정 A) → <strong>메인 캡처</strong>
        <br />
        2) <code>codex logout</code> 후 다른 계정으로 <code>codex login</code> →{" "}
        <strong>서브 캡처</strong>
        <br />
        Room에서 메인 한도/인증 오류 시 서브로 자동 전환합니다.
      </p>

      {error ? <p className="settings-hint">{error}</p> : null}

      <div className="settings-credentials__oauth-status">
        <span>
          live: {meta?.live_logged_in ? "✓" : "—"}{" "}
          {meta?.live_detail ? `(${meta.live_detail})` : ""}
        </span>
        <span>메인: {meta?.has_primary ? "✓ 캡처됨" : "—"}</span>
        <span>서브: {meta?.has_fallback ? "✓ 캡처됨" : "—"}</span>
      </div>

      {probes?.length ? (
        <ul className="settings-credentials__oauth-probes">
          {probes.map((p) => (
            <li key={p.slot}>
              {p.label ?? p.slot}: {p.ok ? "✓" : "✗"}{" "}
              {p.detail ? <span>({p.detail})</span> : null}
            </li>
          ))}
        </ul>
      ) : null}

      <label className="agent-settings__field">
        <span>메인 라벨</span>
        <input
          className="settings-credentials__input"
          type="text"
          value={primaryLabel}
          onChange={(e) => setPrimaryLabel(e.target.value)}
        />
      </label>
      <label className="agent-settings__field">
        <span>서브 라벨</span>
        <input
          className="settings-credentials__input"
          type="text"
          value={fallbackLabel}
          onChange={(e) => setFallbackLabel(e.target.value)}
        />
      </label>

      <div className="settings-credentials__oauth-actions">
        <button
          type="button"
          className="btn btn--sm"
          disabled={busy !== null}
          onClick={() => void saveLabels()}
        >
          {busy === "meta" ? "저장 중…" : "라벨 저장"}
        </button>
        <button
          type="button"
          className="btn btn--sm"
          disabled={busy !== null || !meta?.has_primary}
          onClick={() => void probe()}
        >
          {busy === "probe" ? "검증 중…" : "프로필 검증"}
        </button>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={busy !== null}
          onClick={() => void capture("primary")}
        >
          {busy === "primary" ? "캡처 중…" : "현재 로그인 → 메인"}
        </button>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={busy !== null}
          onClick={() => void capture("fallback")}
        >
          {busy === "fallback" ? "캡처 중…" : "현재 로그인 → 서브"}
        </button>
        {meta?.has_primary ? (
          <button
            type="button"
            className="btn btn--sm"
            disabled={busy !== null}
            onClick={() => void clear("primary")}
          >
            메인 삭제
          </button>
        ) : null}
        {meta?.has_fallback ? (
          <button
            type="button"
            className="btn btn--sm"
            disabled={busy !== null}
            onClick={() => void clear("fallback")}
          >
            서브 삭제
          </button>
        ) : null}
      </div>
      {hint ? <p className="settings-save-hint">{hint}</p> : null}
      {meta?.path ? (
        <p
          className="settings-hint settings-credentials__path"
          title={meta.path}
        >
          OAuth 저장: <code>{meta.path}</code>
        </p>
      ) : null}
    </fieldset>
  );
}

export function AgentCredentialsPanel() {
  const [cursorRow, setCursorRow] = useState<AgentCredentialRow | null>(null);
  const [draft, setDraft] = useState<SlotDraft | null>(null);
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
      const row = res.agents?.find((a) => a.id === "cursor") ?? null;
      setCursorRow(row);
      setPath(res.path ?? null);
      setDraft(row ? draftFromRow(row) : emptyDraft());
    } catch (e) {
      setError(e instanceof Error ? e.message : "불러오기 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const updateDraft = (patch: Partial<SlotDraft>) => {
    setDraft((prev) => (prev ? { ...prev, ...patch } : prev));
    setSaveHint(null);
  };

  const save = async () => {
    if (!draft) return;
    setSaveBusy(true);
    setSaveHint(null);
    setError(null);
    try {
      const res = await putCredentials(patchFromDrafts({ cursor: draft }));
      const row = res.agents?.find((a) => a.id === "cursor") ?? null;
      setCursorRow(row);
      setPath(res.path ?? null);
      setDraft(row ? draftFromRow(row) : emptyDraft());
      setSaveHint("Cursor API 키 저장됨 ✓");
    } catch (e) {
      setSaveHint(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaveBusy(false);
    }
  };

  if (loading && !draft) {
    return <p className="settings-hint">인증 설정 불러오는 중…</p>;
  }

  if (error && !draft) {
    return (
      <div className="settings-credentials__error">
        <p className="settings-hint">{error}</p>
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => void load()}
        >
          다시 시도
        </button>
      </div>
    );
  }

  if (!draft || !cursorRow) return null;

  return (
    <div className="settings-credentials">
      <p className="settings-hint">
        <strong>Cursor</strong>만 API 키(메인/서브)를 사용합니다.{" "}
        <strong>Claude·Codex</strong>는 CLI OAuth 전용입니다.
      </p>

      <div className="agent-settings__grid">
        <OAuthAgentCard
          id="claude"
          title="Claude"
          loginHint="claude auth login --claudeai"
        />
        <CodexOAuthCard />
        <fieldset
          className={[
            "agent-settings__card",
            "settings-credentials__card",
            cursorRow.has_primary || cursorRow.has_fallback
              ? undefined
              : "agent-settings__card--dim",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          <legend className="agent-settings__legend">
            <Avatar role="cursor" size={18} />
            Cursor
            <span className="agent-settings__model">
              {cursorRow.env_primary}
            </span>
          </legend>

          <label className="agent-settings__field">
            <span>메인 라벨</span>
            <input
              className="settings-credentials__input"
              type="text"
              value={draft.primary_label}
              placeholder="메인"
              onChange={(e) => updateDraft({ primary_label: e.target.value })}
            />
          </label>

          <label className="agent-settings__field">
            <span>메인 API 키</span>
            <input
              className="settings-credentials__input"
              type="password"
              autoComplete="off"
              placeholder={
                cursorRow.primary_masked
                  ? `등록됨 ${cursorRow.primary_masked}`
                  : `${cursorRow.env_primary} (미설정)`
              }
              value={draft.primary}
              onChange={(e) =>
                updateDraft({ primary: e.target.value, primaryDirty: true })
              }
            />
          </label>

          <label className="agent-settings__field">
            <span>서브 라벨</span>
            <input
              className="settings-credentials__input"
              type="text"
              value={draft.fallback_label}
              placeholder="서브"
              onChange={(e) => updateDraft({ fallback_label: e.target.value })}
            />
          </label>

          <label className="agent-settings__field">
            <span>서브 API 키 (fallback)</span>
            <input
              className="settings-credentials__input"
              type="password"
              autoComplete="off"
              placeholder={
                cursorRow.fallback_masked
                  ? `등록됨 ${cursorRow.fallback_masked}`
                  : `${cursorRow.env_fallback} (선택)`
              }
              value={draft.fallback}
              onChange={(e) =>
                updateDraft({ fallback: e.target.value, fallbackDirty: true })
              }
            />
          </label>

          <div className="agent-settings__toolbar">
            <button
              type="button"
              className="btn btn--primary btn--sm"
              disabled={saveBusy}
              onClick={() => void save()}
            >
              {saveBusy ? "저장 중…" : "Cursor API 키 저장"}
            </button>
            {saveHint ? <p className="settings-save-hint">{saveHint}</p> : null}
          </div>
        </fieldset>
      </div>

      {path ? (
        <p className="settings-hint settings-credentials__path" title={path}>
          API 키 저장: <code>{path}</code>
        </p>
      ) : null}
    </div>
  );
}
