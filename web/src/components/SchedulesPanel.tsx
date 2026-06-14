import { useCallback, useEffect, useState } from "react";
import {
  approveSessionSchedule,
  fetchMissionTemplates,
  fetchSessionSchedules,
  patchSessionSchedules,
  type MissionScheduleEntry,
  type MissionTemplateSummary,
} from "../api/client";
import { useLocale } from "../i18n/useLocale";

type SchedulesPanelProps = {
  readonly sessionId: string;
};

function emptySchedule(): MissionScheduleEntry {
  return {
    id: `sched-${Date.now()}`,
    cron: "0 9 * * 1-5",
    tz: "UTC",
    gate_profile: "assistant",
    sandbox: true,
    enabled: true,
    notify: { on_start: true },
  };
}

export function SchedulesPanel({ sessionId }: SchedulesPanelProps) {
  const { t } = useLocale();
  const [schedules, setSchedules] = useState<MissionScheduleEntry[]>([]);
  const [templates, setTemplates] = useState<MissionTemplateSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);

  const load = useCallback(() => {
    void fetchSessionSchedules(sessionId).then((res) => setSchedules(res.schedules ?? []));
    void fetchMissionTemplates().then((res) => setTemplates(res.templates ?? []));
  }, [sessionId]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setBusy(true);
    setHint(null);
    try {
      const res = await patchSessionSchedules(sessionId, schedules);
      setSchedules(res.schedules);
      setHint(t("saved"));
    } catch (err) {
      setHint(err instanceof Error ? err.message : "save failed");
    } finally {
      setBusy(false);
    }
  };

  const approve = async (scheduleId: string) => {
    setBusy(true);
    try {
      const res = await approveSessionSchedule(sessionId, scheduleId);
      setSchedules(res.schedules);
      setHint(t("missionOsScheduleApproved"));
    } catch (err) {
      setHint(err instanceof Error ? err.message : "approve failed");
    } finally {
      setBusy(false);
    }
  };

  const updateRow = (index: number, patch: Partial<MissionScheduleEntry>) => {
    setSchedules((rows) =>
      rows.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  };

  return (
    <div className="mission-os-schedules">
      <div className="settings-section__sub-head">{t("missionOsSchedules")}</div>
      {schedules.length === 0 ? (
        <p className="settings-hint">{t("missionOsNoSchedules")}</p>
      ) : null}
      {schedules.map((row, index) => (
        <div key={row.id} className="mission-os-schedule-row">
          <label className="settings-field">
            <span>ID</span>
            <input
              className="settings-input"
              value={row.id}
              onChange={(e) => updateRow(index, { id: e.target.value })}
            />
          </label>
          <label className="settings-field">
            <span>cron</span>
            <input
              className="settings-input"
              value={row.cron}
              onChange={(e) => updateRow(index, { cron: e.target.value })}
            />
          </label>
          <label className="settings-field">
            <span>{t("missionOsGateProfile")}</span>
            <select
              className="settings-input"
              value={row.gate_profile ?? "assistant"}
              onChange={(e) =>
                updateRow(index, {
                  gate_profile: e.target.value as "dev" | "assistant",
                })
              }
            >
              <option value="dev">dev</option>
              <option value="assistant">assistant</option>
            </select>
          </label>
          <label className="settings-field">
            <span>{t("missionOsTemplate")}</span>
            <select
              className="settings-input"
              value={row.template_id ?? ""}
              onChange={(e) =>
                updateRow(index, { template_id: e.target.value || null })
              }
            >
              <option value="">—</option>
              {templates.map((tpl) => (
                <option key={tpl.id} value={tpl.id}>
                  {tpl.id}
                  {tpl.hash_match ? " ✓" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="settings-field settings-field--inline">
            <input
              type="checkbox"
              checked={row.sandbox !== false}
              onChange={(e) => updateRow(index, { sandbox: e.target.checked })}
            />
            <span>{t("missionOsSandbox")}</span>
          </label>
          <div className="mission-os-schedule-meta">
            {row.pre_approved_at ? (
              <span className="ctx-oracle-badge ctx-oracle-badge--pass">
                {t("missionOsPreApproved")}
              </span>
            ) : (
              <button
                type="button"
                className="settings-btn settings-btn--ghost"
                disabled={busy}
                onClick={() => void approve(row.id)}
              >
                {t("missionOsApproveSchedule")}
              </button>
            )}
            {row.last_run_status ? (
              <span className="settings-hint">
                last: {row.last_run_status}
                {row.last_run_at ? ` @ ${row.last_run_at}` : ""}
              </span>
            ) : null}
          </div>
        </div>
      ))}
      <div className="settings-actions">
        <button
          type="button"
          className="settings-btn settings-btn--ghost"
          disabled={busy}
          onClick={() => setSchedules((rows) => [...rows, emptySchedule()])}
        >
          {t("missionOsAddSchedule")}
        </button>
        <button type="button" className="settings-btn" disabled={busy} onClick={() => void save()}>
          {t("save")}
        </button>
      </div>
      {hint ? <p className="settings-hint">{hint}</p> : null}
    </div>
  );
}
