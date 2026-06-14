import { useEffect, useMemo, useState } from "react";
import type {
  ResponseContractPreset,
  ResponseContractRecord,
  RuntimeFlagRow,
  SessionDetail,
} from "../api/client";
import { fetchHealthFlags, setSessionResponseContract } from "../api/client";
import {
  communicateMetaRows,
  formatHookMeta,
  HOOK_RESPONSE_FLAG_NAMES,
  isResponseContractPreset,
  parseResponseContract,
  recordBoolean,
  recordNumber,
  recordString,
  RESPONSE_CONTRACT_PRESETS,
} from "../utils/responseContractSettings";
import { SettingsSectionIcon } from "./SettingsSectionIcon";

type HooksResponseSettingsProps = {
  readonly sessionId: string | null;
  readonly session: SessionDetail | null;
};

export function HooksResponseSettings({
  sessionId,
  session,
}: HooksResponseSettingsProps) {
  const [runtimeFlags, setRuntimeFlags] = useState<RuntimeFlagRow[]>([]);
  const [runtimeFlagsError, setRuntimeFlagsError] = useState<string | null>(null);
  const [contract, setContract] = useState<ResponseContractRecord | null>(
    () => parseResponseContract(session?.run?.response_contract),
  );
  const [selectedPreset, setSelectedPreset] = useState<ResponseContractPreset>(
    () => {
      const preset = parseResponseContract(session?.run?.response_contract)?.preset;
      return isResponseContractPreset(preset) ? preset : "concise";
    },
  );
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveHint, setSaveHint] = useState<string | null>(null);

  useEffect(() => {
    const next = parseResponseContract(session?.run?.response_contract);
    setContract(next);
    if (isResponseContractPreset(next?.preset)) setSelectedPreset(next.preset);
  }, [session?.run?.response_contract]);

  useEffect(() => {
    let cancelled = false;
    setRuntimeFlagsError(null);
    void fetchHealthFlags()
      .then((res) => {
        if (!cancelled) setRuntimeFlags(res.flags ?? []);
      })
      .catch((error) => {
        if (!cancelled) {
          setRuntimeFlags([]);
          setRuntimeFlagsError(
            error instanceof Error ? error.message : "flags unavailable",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const hookResponseFlags = useMemo(
    () => runtimeFlags.filter((flag) => HOOK_RESPONSE_FLAG_NAMES.has(flag.name)),
    [runtimeFlags],
  );
  const hookRuns = session?.observability?.hook_runs_tail ?? [];
  const communicateRows = communicateMetaRows(
    session?.observability?.last_communicate_meta,
  );

  const saveContract = async () => {
    if (!sessionId) return;
    setSaveBusy(true);
    setSaveHint(null);
    try {
      const res = await setSessionResponseContract(sessionId, selectedPreset);
      setContract(res.response_contract);
      setSaveHint("저장됨");
    } catch (error) {
      setSaveHint(error instanceof Error ? error.message : "저장 실패");
    } finally {
      setSaveBusy(false);
    }
  };

  return (
    <section className="settings-section">
      <div className="settings-section__head">
        <h2 className="settings-section__title">
          <SettingsSectionIcon name="activity" />
          Hooks & Response
        </h2>
        <span className="settings-section__sub">
          hook 실행 로그 · response contract · envelope flags
        </span>
      </div>

      <div className="settings-contract-presets" role="radiogroup" aria-label="Response contract preset">
        {RESPONSE_CONTRACT_PRESETS.map((preset) => (
          <button
            key={preset.preset}
            type="button"
            role="radio"
            aria-checked={selectedPreset === preset.preset}
            className={selectedPreset === preset.preset ? "is-active" : undefined}
            onClick={() => setSelectedPreset(preset.preset)}
          >
            <span>{preset.label}</span>
            <small>{preset.description}</small>
          </button>
        ))}
      </div>
      <div className="settings-contract-actions">
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={!sessionId || saveBusy}
          onClick={() => void saveContract()}
        >
          {saveBusy ? "저장 중…" : "Contract 저장"}
        </button>
        <span className="settings-hint">
          현재: {contract?.label ?? "기본 정책"} · P1b는 기존 guidance block에 preset hint를
          추가합니다.
        </span>
        {saveHint ? <span className="settings-save-hint">{saveHint}</span> : null}
      </div>

      <div className="settings-observability-grid">
        <div className="settings-observability-panel">
          <div className="settings-section__sub-head">최근 hook runs</div>
          {hookRuns.length > 0 ? (
            <div className="settings-observability-list">
              {hookRuns
                .slice(-6)
                .reverse()
                .map((row, index) => {
                  const eventName = recordString(row, "event") || "hook";
                  const blocked = recordBoolean(row, "blocked");
                  const exitCode = recordNumber(row, "exit_code");
                  const feedback =
                    recordString(row, "feedback") ||
                    recordString(row, "sub_reason") ||
                    recordString(row, "command") ||
                    "no feedback";
                  const status = blocked ? "blocked" : exitCode === 0 ? "ok" : "warn";
                  return (
                    <div
                      key={`${recordString(row, "ts")}-${eventName}-${index}`}
                      className={`settings-observability-row settings-observability-row--${status}`}
                    >
                      <div className="settings-observability-row__head">
                        <span>{eventName}</span>
                        <span className={`badge badge--${blocked ? "danger" : "ok"}`}>
                          {blocked ? "blocked" : exitCode === 0 ? "ok" : "warn"}
                        </span>
                      </div>
                      <p>{feedback}</p>
                      <span className="settings-observability-row__meta">
                        {formatHookMeta(row)}
                      </span>
                    </div>
                  );
                })}
            </div>
          ) : (
            <p className="settings-hint">이 세션에 기록된 hook run이 아직 없습니다.</p>
          )}
        </div>

        <div className="settings-observability-panel">
          <div className="settings-section__sub-head">Response contract meta</div>
          {communicateRows.length > 0 ? (
            <dl className="settings-observability-kv">
              {communicateRows.map((row) => (
                <div key={row.label}>
                  <dt>{row.label}</dt>
                  <dd title={row.value}>{row.value}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="settings-hint">아직 envelope / communicate meta가 없습니다.</p>
          )}

          <div className="settings-section__sub-head">Config paths</div>
          <dl className="settings-observability-kv">
            <div>
              <dt>project</dt>
              <dd>.agent-lab/hooks.toml</dd>
            </div>
            <div>
              <dt>user</dt>
              <dd>~/.agent-lab/hooks.toml</dd>
            </div>
            <div>
              <dt>override</dt>
              <dd>AGENT_LAB_HOOKS_PATH</dd>
            </div>
          </dl>
        </div>
      </div>

      <div className="settings-section__sub-head">Runtime flags</div>
      {runtimeFlagsError ? (
        <p className="settings-hint">{runtimeFlagsError}</p>
      ) : hookResponseFlags.length > 0 ? (
        <div className="settings-flag-grid">
          {hookResponseFlags.map((flag) => (
            <div key={flag.name} className="settings-flag-row">
              <div className="settings-flag-row__main">
                <span className="settings-flag-row__name">{flag.name}</span>
                <span className="settings-flag-row__description">
                  {flag.description ?? "undocumented"}
                </span>
              </div>
              <span
                className={`badge badge--${flag.set ? "ok" : "neutral"}`}
                title={flag.value ?? flag.default ?? undefined}
              >
                {flag.effective ?? flag.default ?? "unset"}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <p className="settings-hint">Hook/contract 관련 flag를 불러오는 중입니다.</p>
      )}
      <p className="settings-hint">
        hooks.toml 편집은 아직 읽기 전용입니다. Response preset은 세션별 agent guidance에만
        반영됩니다.
      </p>
    </section>
  );
}
