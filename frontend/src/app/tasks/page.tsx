"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Plus, RefreshCw, X } from "lucide-react";

type Priority = "low" | "medium" | "high";
type ColumnId = "todo" | "doing" | "review" | "done";

type Task = {
  id: string;
  title: string;
  status: ColumnId;
  priority?: Priority | null;
  assignee?: string | null;
};

const COLUMNS: { id: ColumnId; label: string; accent: string }[] = [
  { id: "todo", label: "To do", accent: "paper-3" },
  { id: "doing", label: "In progress", accent: "amber" },
  { id: "review", label: "In review", accent: "sky" },
  { id: "done", label: "Done", accent: "sage" },
];

const PRI_COLOR: Record<Priority, string> = {
  high: "rust",
  medium: "amber",
  low: "paper-3",
};

const COLUMN_IDS: ColumnId[] = ["todo", "doing", "review", "done"];

function groupByColumn(tasks: Task[]): Record<ColumnId, Task[]> {
  const out: Record<ColumnId, Task[]> = { todo: [], doing: [], review: [], done: [] };
  for (const t of tasks) {
    const col = COLUMN_IDS.includes(t.status) ? t.status : "todo";
    out[col].push(t);
  }
  return out;
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [dragId, setDragId] = useState<string | null>(null);
  const [dragFrom, setDragFrom] = useState<ColumnId | null>(null);
  const [hoverCol, setHoverCol] = useState<ColumnId | null>(null);
  const [composing, setComposing] = useState<ColumnId | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/tasks");
      const data = await r.json();
      setTasks(Array.isArray(data) ? data : []);
    } catch {}
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const board = useMemo(() => groupByColumn(tasks), [tasks]);

  const moveTask = async (id: string, toCol: ColumnId) => {
    const prev = tasks;
    setTasks((ts) => ts.map((t) => (t.id === id ? { ...t, status: toCol } : t)));
    try {
      const r = await fetch(`/api/tasks/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: toCol }),
      });
      if (!r.ok) throw new Error();
    } catch {
      setTasks(prev); // revert on failure
    }
  };

  const drop = (toCol: ColumnId) => {
    const id = dragId;
    const from = dragFrom;
    setDragId(null);
    setDragFrom(null);
    setHoverCol(null);
    if (id == null || from == null || from === toCol) return;
    moveTask(id, toCol);
  };

  const createTask = async (status: ColumnId, title: string) => {
    const clean = title.trim();
    if (!clean) return;
    try {
      const r = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: clean, status }),
      });
      if (r.ok) {
        const created = await r.json();
        setTasks((ts) => [created, ...ts]);
      }
    } catch {}
  };

  const removeTask = async (id: string) => {
    const prev = tasks;
    setTasks((ts) => ts.filter((t) => t.id !== id));
    try {
      const r = await fetch(`/api/tasks/${id}`, { method: "DELETE" });
      if (!r.ok) throw new Error();
    } catch {
      setTasks(prev);
    }
  };

  const totals = useMemo(
    () => ({
      total: tasks.length,
      yuji: tasks.filter((t) => t.assignee === "yuji").length,
      doing: board.doing.length,
    }),
    [tasks, board]
  );

  return (
    <div style={{ padding: 40, display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 24 }}>
        <div>
          <h1 className="page-title">
            Tasks<em>.</em>
          </h1>
          <div className="page-sub">
            {totals.total} active · Yuji owns {totals.yuji} · {totals.doing} in flight
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button className="btn" onClick={load} disabled={loading}>
            <RefreshCw size={13} /> Refresh
          </button>
          <button className="btn btn-primary" onClick={() => setComposing("todo")}>
            <Plus size={12} /> New task
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, flex: 1, minHeight: 0 }}>
        {COLUMNS.map((col) => (
          <div
            key={col.id}
            onDragOver={(e) => {
              e.preventDefault();
              setHoverCol(col.id);
            }}
            onDragLeave={() => setHoverCol(null)}
            onDrop={() => drop(col.id)}
            style={{
              background: "var(--ink-1)",
              border: "1px solid " + (hoverCol === col.id ? "var(--amber-dim)" : "var(--line)"),
              borderRadius: 8,
              display: "flex",
              flexDirection: "column",
              minHeight: 0,
            }}
          >
            <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: `var(--${col.accent})` }} />
                <span className="font-mono" style={{ fontSize: 11, color: "var(--paper-0)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
                  {col.label}
                </span>
                <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>{board[col.id].length}</span>
              </div>
              <button className="btn btn-ghost" style={{ padding: "2px 6px" }} onClick={() => setComposing(col.id)}>
                <Plus size={11} />
              </button>
            </div>
            <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 10, overflowY: "auto", flex: 1 }}>
              {composing === col.id && (
                <Composer
                  onCancel={() => setComposing(null)}
                  onSubmit={(title) => {
                    createTask(col.id, title);
                    setComposing(null);
                  }}
                />
              )}
              {board[col.id].map((t) => (
                <TaskCard
                  key={t.id}
                  task={t}
                  dragging={dragId === t.id}
                  onDragStart={() => {
                    setDragId(t.id);
                    setDragFrom(col.id);
                  }}
                  onDragEnd={() => {
                    setDragId(null);
                    setDragFrom(null);
                    setHoverCol(null);
                  }}
                  onDelete={() => removeTask(t.id)}
                />
              ))}
              {board[col.id].length === 0 && composing !== col.id && (
                <div style={{ padding: "32px 12px", textAlign: "center" }}>
                  <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)" }}>
                    {loading ? "loading…" : "no tasks here"}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Composer({ onSubmit, onCancel }: { onSubmit: (title: string) => void; onCancel: () => void }) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  return (
    <div style={{ background: "var(--ink-2)", border: "1px solid var(--line-strong)", borderRadius: 6, padding: 10 }}>
      <input
        ref={ref}
        className="input"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") onSubmit(value);
          if (e.key === "Escape") onCancel();
        }}
        placeholder="Task title…"
        style={{ width: "100%", fontSize: 12, marginBottom: 8 }}
      />
      <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
        <button className="btn btn-ghost" style={{ padding: "3px 8px", fontSize: 11 }} onClick={onCancel}>
          Cancel
        </button>
        <button className="btn btn-primary" style={{ padding: "3px 8px", fontSize: 11 }} onClick={() => onSubmit(value)}>
          Add
        </button>
      </div>
    </div>
  );
}

function TaskCard({
  task,
  dragging,
  onDragStart,
  onDragEnd,
  onDelete,
}: {
  task: Task;
  dragging: boolean;
  onDragStart: () => void;
  onDragEnd: () => void;
  onDelete: () => void;
}) {
  const [hover, setHover] = useState(false);
  const priColor = task.priority ? PRI_COLOR[task.priority] : "line-strong";
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: "var(--ink-2)",
        border: "1px solid var(--line-strong)",
        borderLeft: `2px solid var(--${priColor})`,
        borderRadius: 6,
        padding: 12,
        cursor: "grab",
        opacity: dragging ? 0.4 : 1,
        position: "relative",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: task.assignee || task.priority ? 10 : 0 }}>
        <div style={{ fontSize: 13, lineHeight: 1.4, color: "var(--paper-0)" }}>{task.title}</div>
        {hover && (
          <button
            className="btn btn-ghost"
            style={{ padding: 2, height: 18, flexShrink: 0 }}
            onClick={onDelete}
            title="Delete task"
          >
            <X size={11} />
          </button>
        )}
      </div>

      {(task.assignee || task.priority) && (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          {task.assignee ? (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Avatar name={task.assignee} />
              <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>{task.assignee}</span>
            </div>
          ) : (
            <span />
          )}
          {task.priority && (
            <span className={`tag tag-${task.priority === "high" ? "rust" : task.priority === "medium" ? "amber" : ""}`} style={{ fontSize: 9 }}>
              {task.priority}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function Avatar({ name }: { name: string }) {
  if (name === "yuji") {
    return (
      <span
        style={{
          width: 18,
          height: 18,
          borderRadius: "50%",
          background: "radial-gradient(circle at 30% 30%, var(--amber), var(--amber-dim) 60%, var(--ink-3))",
          display: "inline-block",
        }}
      />
    );
  }
  return (
    <span
      style={{
        width: 18,
        height: 18,
        borderRadius: "50%",
        background: "var(--ink-3)",
        border: "1px solid var(--line-strong)",
        display: "grid",
        placeItems: "center",
        fontFamily: "var(--serif)",
        fontSize: 10,
        color: "var(--paper-1)",
      }}
    >
      {name.charAt(0).toUpperCase()}
    </span>
  );
}
