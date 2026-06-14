import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelBgTask,
  getBgTaskLog,
  listBgTasks,
  submitBgTask,
  type BgLogLine,
  type BgTask,
  type BgTaskStatus,
} from "../api/client";
import { useLocale } from "../i18n/useLocale";
import type { messages } from "../i18n/messages";

type Props = {
  sessionId: string;
};

type Msg = ReturnType<typeof messages>;

const STATUS_MOD: Record<BgTaskStatus, string> = {
  queued: "queued",
  running: "running",
  done: "done",
  failed: "failed",
  cancelled: "cancelled",
};

function statusLabel(msg: Msg, status: BgTaskStatus): string {
  const map: Record<BgTaskStatus, keyof Msg> = {
    queued: "bgtaskStatusQueued",
    running: "bgtaskStatusRunning",
    done: "bgtaskStatusDone",
    failed: "bgtaskStatusFailed",
    cancelled: "bgtaskStatusCancelled",
  };
  const key = map[status];
  const val = msg[key];
  return typeof val === "string" ? val : String(val);
}

function isActive(status: BgTaskStatus) {
  return status === "queued" || status === "running";
}

function TaskRow({
  task,
  sessionId,
  msg,
  onCancel,
}: {
  task: BgTask;
  sessionId: string;
  msg: Msg;
  onCancel: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState<BgLogLine[]>([]);
  const [logOffset, setLogOffset] = useState(0);
  const logRef = useRef<HTMLPreElement>(null);

  const fetchLog = useCallback(async () => {
    const res = await getBgTaskLog(sessionId, task.task_id, logOffset);
    if (res.lines.length > 0) {
      setLines((prev) => [...prev, ...res.lines]);
      setLogOffset(logOffset + res.lines.length);
    }
  }, [sessionId, task.task_id, logOffset]);

  useEffect(() => {
    if (!open) return;
    void fetchLog();
    if (!isActive(task.status)) return;
    const t = setInterval(() => void fetchLog(), 1000);
    return () => clearInterval(t);
  }, [open, task.status, fetchLog]);

  useEffect(() => {
    if (open && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [lines, open]);

  return (
    <div className={`bgtask-row${open ? " is-open" : ""}`}>
      <div className="bgtask-row__head">
        <button
          type="button"
          className="bgtask-row__toggle"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
        >
          <span className="bgtask-row__chevron">{open ? "▾" : "▸"}</span>
          <span className="bgtask-row__label">{task.label}</span>
          <span
            className={`bgtask-badge bgtask-badge--${STATUS_MOD[task.status]}`}
          >
            {statusLabel(msg, task.status)}
          </span>
          <span className="bgtask-row__cmd">{task.command.join(" ")}</span>
        </button>
        {isActive(task.status) ? (
          <button
            type="button"
            className="btn btn--sm btn--ghost bgtask-row__cancel"
            title={msg.bgtaskCancel}
            onClick={() => onCancel(task.task_id)}
          >
            ✕
          </button>
        ) : task.exit_code != null ? (
          <span className="bgtask-row__exit">exit {task.exit_code}</span>
        ) : null}
      </div>

      {open ? (
        <pre ref={logRef} className="bgtask-log">
          {lines.length === 0
            ? isActive(task.status)
              ? "…"
              : msg.bgtaskNoOutput
            : lines.map((l) => l.text).join("\n")}
        </pre>
      ) : null}
    </div>
  );
}

function NewTaskForm({
  sessionId,
  msg,
  onSubmit,
  onClose,
}: {
  sessionId: string;
  msg: Msg;
  onSubmit: (task: BgTask) => void;
  onClose: () => void;
}) {
  const [label, setLabel] = useState("");
  const [cmd, setCmd] = useState("");
  const [cwd, setCwd] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!cmd.trim()) return;
    setError(null);
    setLoading(true);
    try {
      const parts = cmd.trim().split(/\s+/);
      const task = await submitBgTask(
        sessionId,
        label.trim() || parts[0],
        parts,
        cwd.trim() || undefined,
      );
      onSubmit(task);
      onClose();
    } catch (e) {
      let errMsg = e instanceof Error ? e.message : msg.bgtaskSubmitFailed;
      try {
        const p = JSON.parse(errMsg) as { detail?: string };
        if (p.detail) errMsg = p.detail;
      } catch {
        /* not JSON */
      }
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bgtask-form">
      <div className="bgtask-form__row">
        <input
          className="bgtask-form__input"
          placeholder={msg.bgtaskLabelPlaceholder}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
      </div>
      <div className="bgtask-form__row">
        <input
          className="bgtask-form__input bgtask-form__input--mono"
          placeholder={msg.bgtaskCommandPlaceholder}
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void submit()}
          autoFocus
        />
      </div>
      <div className="bgtask-form__row">
        <input
          className="bgtask-form__input bgtask-form__input--mono"
          placeholder={msg.bgtaskCwdPlaceholder}
          value={cwd}
          onChange={(e) => setCwd(e.target.value)}
        />
      </div>
      {error ? <div className="bgtask-form__error">{error}</div> : null}
      <div className="bgtask-form__actions">
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => void submit()}
          disabled={loading || !cmd.trim()}
        >
          {loading ? msg.bgtaskSubmitting : msg.bgtaskSubmit}
        </button>
        <button
          type="button"
          className="btn btn--sm btn--ghost"
          onClick={onClose}
          disabled={loading}
        >
          {msg.bgtaskCancel}
        </button>
      </div>
    </div>
  );
}

export function BackgroundTasksPanel({ sessionId }: Props) {
  const { msg } = useLocale();
  const [tasks, setTasks] = useState<BgTask[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await listBgTasks(sessionId);
      setTasks(res.tasks);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const hasActive = tasks.some((t) => isActive(t.status));
    if (!hasActive) return;
    const t = setInterval(() => void refresh(), 2000);
    return () => clearInterval(t);
  }, [tasks, refresh]);

  const handleCancel = useCallback(
    async (taskId: string) => {
      await cancelBgTask(sessionId, taskId);
      void refresh();
    },
    [sessionId, refresh],
  );

  const handleSubmit = useCallback((task: BgTask) => {
    setTasks((prev) => [task, ...prev]);
  }, []);

  const activeCount = tasks.filter((t) => isActive(t.status)).length;

  return (
    <div className="bgtask-panel">
      <div className="bgtask-panel__head">
        <svg
          viewBox="0 0 24 24"
          width={14}
          height={14}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.7}
          strokeLinecap="round"
          aria-hidden
        >
          <circle cx="12" cy="12" r="10" />
          <polyline points="12 6 12 12 16 14" />
        </svg>
        {msg.bgtaskTitle}
        {activeCount > 0 ? (
          <span className="bgtask-panel__count">{activeCount}</span>
        ) : null}
        <button
          type="button"
          className="btn btn--sm btn--ghost bgtask-panel__new"
          onClick={() => setShowForm((s) => !s)}
          title={msg.bgtaskNewTitle}
        >
          {showForm ? "–" : "+"}
        </button>
      </div>

      {showForm ? (
        <NewTaskForm
          sessionId={sessionId}
          msg={msg}
          onSubmit={handleSubmit}
          onClose={() => setShowForm(false)}
        />
      ) : null}

      {loading ? (
        <div className="bgtask-panel__hint">{msg.bgtaskLoading}</div>
      ) : tasks.length === 0 ? (
        <div className="bgtask-panel__hint">{msg.bgtaskEmpty}</div>
      ) : (
        tasks.map((t) => (
          <TaskRow
            key={t.task_id}
            task={t}
            sessionId={sessionId}
            msg={msg}
            onCancel={(id) => void handleCancel(id)}
          />
        ))
      )}
    </div>
  );
}
