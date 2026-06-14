import { useState } from "react";
import {
  resolveSessionObjection,
  type RoomObjection,
  type RoomTask,
} from "../api/client";
import { Avatar } from "./Avatar";
import { useLocale } from "../i18n/useLocale";
import type { AgentRole } from "../utils/transcript";

type Props = {
  sessionId: string;
  tasks: RoomTask[];
  objections: RoomObjection[];
  disabled?: boolean;
  onChanged?: () => void;
  onFocusTask?: (taskId: string) => void;
  onFocusObjection?: (id: string, actionIndex?: number) => void;
};

/** Context sidebar — Tasks tab (prototype `ContextSidebar` tasks section). */
export function ContextTasksPanel({
  sessionId,
  tasks,
  objections,
  disabled,
  onChanged,
  onFocusTask,
  onFocusObjection,
}: Props) {
  const { locale, msg } = useLocale();
  const [resolving, setResolving] = useState<string | null>(null);
  const ko = locale === "ko";

  const open = objections.filter((o) => o.status === "open");
  const resolved = objections.filter((o) => o.status !== "open");

  async function handleResolve(
    objectionId: string,
    resolution: "accepted" | "wontfix",
  ) {
    setResolving(objectionId);
    try {
      await resolveSessionObjection(sessionId, objectionId, resolution);
      onChanged?.();
    } finally {
      setResolving(null);
    }
  }

  function dotStatus(status: RoomTask["status"]) {
    if (status === "pending") return "pending";
    return status;
  }

  return (
    <>
      {objections.length > 0 ? (
        <section className="ctx-section">
          <div className="ctx-section__label ctx-section__label--danger">
            <AlertIcon />
            {msg.ctxObjections}
          </div>

          {open.map((obj) => (
            <div key={obj.id} className="ctx-objection">
              <div className="ctx-objection__head">
                <Avatar role={obj.from as AgentRole} size={20} />
                <span
                  className={`ctx-objection__act ctx-objection__act--${obj.act.toLowerCase()}`}
                >
                  {obj.act}
                </span>
                <span className="ctx-objection__time">{obj.ts ?? ""}</span>
              </div>
              <p className="ctx-objection__body">{obj.body}</p>
              <div className="ctx-objection__actions">
                {onFocusObjection ? (
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={() =>
                      onFocusObjection(obj.id, obj.plan_action_index)
                    }
                  >
                    {ko ? "본문에서 보기" : "Open"}
                  </button>
                ) : null}
                <button
                  type="button"
                  className="btn btn--sm btn--ok"
                  disabled={disabled || resolving === obj.id}
                  onClick={() => void handleResolve(obj.id, "accepted")}
                >
                  Accept
                </button>
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={disabled || resolving === obj.id}
                  onClick={() => void handleResolve(obj.id, "wontfix")}
                >
                  Won&apos;t fix
                </button>
              </div>
            </div>
          ))}

          {resolved.map((obj) => (
            <div key={obj.id} className="ctx-objection ctx-objection--resolved">
              <div className="ctx-objection__head">
                <Avatar role={obj.from as AgentRole} size={20} />
                <span
                  className={`ctx-objection__act ctx-objection__act--${obj.act.toLowerCase()}`}
                >
                  {obj.act}
                </span>
                <span className="ctx-objection__time">{obj.ts ?? ""}</span>
                <span
                  className="badge badge--ok"
                  style={{ marginLeft: "auto" }}
                >
                  {ko ? "해결됨" : "resolved"}
                </span>
              </div>
              <p className="ctx-objection__body">{obj.body}</p>
            </div>
          ))}
        </section>
      ) : null}

      <section className="ctx-section">
        <div className="ctx-section__label">{msg.ctxTasks}</div>
        <p className="ctx-section__hint">
          {ko
            ? "상세 TaskBar는 Transcript/Work 본문에 고정됩니다. 여기서는 필요한 항목으로 바로 이동합니다."
            : "The full taskbar stays docked in Transcript/Work. Use this queue to jump to the right item."}
        </p>
        {tasks.length === 0 ? (
          <div className="ctx-empty">{msg.ctxTasksEmpty}</div>
        ) : null}
        {tasks.map((task) => (
          <button
            type="button"
            key={task.id}
            className={[
              "task-row",
              "task-row--button",
              task.status === "blocked" ? "task-row--blocked" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            data-task-id={task.id}
            onClick={() => onFocusTask?.(task.id)}
            disabled={!onFocusTask}
          >
            <span
              className={`task-row__dot task-row__dot--${dotStatus(task.status)}`}
            />
            <span className="task-row__title">{task.title}</span>
            {task.owner_agent ? (
              <Avatar role={task.owner_agent as AgentRole} size={20} />
            ) : null}
          </button>
        ))}
      </section>
    </>
  );
}

function AlertIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M8 3v5M8 11v1" />
      <path d="M8 1 1 14h14L8 1z" />
    </svg>
  );
}
