"use client";

import { useMemo, useState } from "react";
import { Clock, GitBranch, Plus } from "lucide-react";

type Priority = "low" | "medium" | "high";
type ColumnId = "todo" | "doing" | "review" | "done";

type Task = {
  id: number;
  title: string;
  priority: Priority;
  repo: string;
  assignee: string;
  estimate: string;
  linked?: string[];
  progress?: number;
};

const INITIAL: Record<ColumnId, Task[]> = {
  todo: [
    { id: 1, title: "Add rate limiting to auth endpoints", priority: "high", repo: "kit-fork", assignee: "yuji", estimate: "4h", linked: ["KIT-2104", "PR #847"] },
    { id: 2, title: "Refactor payment service error handling", priority: "low", repo: "kit-fork", assignee: "jin", estimate: "1d", linked: [] },
    { id: 3, title: "Document the queue backpressure model", priority: "medium", repo: "build-pipe-frk", assignee: "yuji", estimate: "2h", linked: [] },
    { id: 4, title: "Migrate stripe webhook to idempotent flow", priority: "high", repo: "kit-fork", assignee: "maya", estimate: "6h", linked: ["PR #851"] },
  ],
  doing: [
    { id: 5, title: "Update API documentation for v2", priority: "medium", repo: "yacs-frk", assignee: "arun", estimate: "3h", linked: ["PR #112"] },
    { id: 6, title: "Investigate CI cache miss in build-pipe", priority: "high", repo: "build-pipe-frk", assignee: "yuji", estimate: "2h", linked: [], progress: 60 },
  ],
  review: [
    { id: 7, title: "PR #847 — clarify retry semantics", priority: "medium", repo: "build-pipe-frk", assignee: "jin", estimate: "1h", linked: ["PR #847"] },
  ],
  done: [
    { id: 8, title: "Fix login redirect loop on Safari", priority: "high", repo: "kit-fork", assignee: "yuji", estimate: "4h", linked: ["PR #844"] },
    { id: 9, title: "Knowledge graph refresh for zapq", priority: "low", repo: "zapq-frk", assignee: "yuji", estimate: "8h", linked: [] },
  ],
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

export default function TasksPage() {
  const [tasks, setTasks] = useState<Record<ColumnId, Task[]>>(INITIAL);
  const [dragId, setDragId] = useState<number | null>(null);
  const [dragFrom, setDragFrom] = useState<ColumnId | null>(null);
  const [hoverCol, setHoverCol] = useState<ColumnId | null>(null);

  const drop = (toCol: ColumnId) => {
    if (dragId == null || dragFrom == null || dragFrom === toCol) {
      setDragId(null);
      setDragFrom(null);
      setHoverCol(null);
      return;
    }
    setTasks((t) => {
      const card = t[dragFrom].find((x) => x.id === dragId);
      if (!card) return t;
      return {
        ...t,
        [dragFrom]: t[dragFrom].filter((x) => x.id !== dragId),
        [toCol]: [card, ...t[toCol]],
      };
    });
    setDragId(null);
    setDragFrom(null);
    setHoverCol(null);
  };

  const totals = useMemo(() => {
    const all = Object.values(tasks).flat();
    return {
      total: all.length,
      yuji: all.filter((t) => t.assignee === "yuji").length,
      doing: tasks.doing.length,
    };
  }, [tasks]);

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
          <div style={{ display: "flex", gap: 4, padding: 3, background: "var(--ink-2)", borderRadius: 6, border: "1px solid var(--line)" }}>
            <button className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 11, background: "var(--ink-3)" }}>Board</button>
            <button className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 11 }} disabled>List</button>
            <button className="btn btn-ghost" style={{ padding: "4px 10px", fontSize: 11 }} disabled>Timeline</button>
          </div>
          <input className="input" placeholder="Filter by repo, person, label…" style={{ width: 240, fontSize: 12 }} />
          <button className="btn btn-primary" disabled>
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
                <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>{tasks[col.id].length}</span>
              </div>
              <button className="btn btn-ghost" style={{ padding: "2px 6px" }} disabled>
                <Plus size={11} />
              </button>
            </div>
            <div style={{ padding: 12, display: "flex", flexDirection: "column", gap: 10, overflowY: "auto", flex: 1 }}>
              {tasks[col.id].map((t) => (
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
                />
              ))}
              {tasks[col.id].length === 0 && (
                <div style={{ padding: "32px 12px", textAlign: "center" }}>
                  <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)" }}>no tasks here</div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TaskCard({
  task,
  dragging,
  onDragStart,
  onDragEnd,
}: {
  task: Task;
  dragging: boolean;
  onDragStart: () => void;
  onDragEnd: () => void;
}) {
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      style={{
        background: "var(--ink-2)",
        border: "1px solid var(--line-strong)",
        borderLeft: `2px solid var(--${PRI_COLOR[task.priority]})`,
        borderRadius: 6,
        padding: 12,
        cursor: "grab",
        opacity: dragging ? 0.4 : 1,
      }}
    >
      <div style={{ fontSize: 13, lineHeight: 1.4, color: "var(--paper-0)", marginBottom: 10 }}>
        {task.title}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 10 }}>
        <span className="tag" style={{ fontSize: 9 }}>
          <GitBranch size={9} /> {task.repo}
        </span>
        {task.linked?.map((l, i) => (
          <span key={i} className="tag tag-sky" style={{ fontSize: 9 }}>{l}</span>
        ))}
      </div>

      {task.progress != null && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
            <span className="font-mono" style={{ fontSize: 9, color: "var(--paper-4)" }}>PROGRESS</span>
            <span className="font-mono" style={{ fontSize: 9, color: "var(--amber)" }}>{task.progress}%</span>
          </div>
          <div style={{ height: 2, background: "var(--ink-3)", borderRadius: 1 }}>
            <div style={{ height: "100%", width: `${task.progress}%`, background: "var(--amber)", borderRadius: 1 }} />
          </div>
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <Avatar name={task.assignee} />
          <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>{task.assignee}</span>
        </div>
        <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)", display: "inline-flex", alignItems: "center", gap: 4 }}>
          <Clock size={9} /> {task.estimate}
        </span>
      </div>
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
