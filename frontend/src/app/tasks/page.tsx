"use client";

import { useState } from "react";
import { Plus, CheckCircle2 } from "lucide-react";

const COLUMNS = [
  { key: "todo", label: "To Do" },
  { key: "in_progress", label: "In Progress" },
  { key: "done", label: "Done" },
];

export default function TasksPage() {
  const [tasks, setTasks] = useState([
    { id: "1", title: "Add rate limiting to auth endpoints", status: "todo", priority: "high" },
    { id: "2", title: "Update API documentation for v2", status: "in_progress", priority: "medium" },
    { id: "3", title: "Fix login redirect loop on Safari", status: "done", priority: "high" },
    { id: "4", title: "Refactor payment service error handling", status: "todo", priority: "low" },
  ]);
  const [input, setInput] = useState("");

  function addTask() {
    if (!input.trim()) return;
    setTasks([...tasks, { id: String(Date.now()), title: input.trim(), status: "todo", priority: "medium" }]);
    setInput("");
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-lg font-semibold text-[#cccccc]">Tasks</h1>
        <p className="mt-0.5 text-xs text-[#6a6a6e]">Track work across your team</p>
      </div>

      <div className="mb-6 flex gap-2">
        <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addTask()} placeholder="New task..." className="input flex-1" />
        <button onClick={addTask} className="btn-primary"><Plus className="h-3.5 w-3.5" /> Add</button>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {COLUMNS.map((col) => {
          const items = tasks.filter((t) => t.status === col.key);
          return (
            <div key={col.key} className="panel">
              <div className="flex items-center gap-2 border-b border-[#2a2a2e] px-4 py-2.5">
                <span className="text-xs font-semibold text-[#8a8a8e] uppercase tracking-wide">{col.label}</span>
                <span className="text-[10px] text-[#5a5a5e] ml-auto">{items.length}</span>
              </div>
              <div className="p-2 space-y-1">
                {items.map((task) => (
                  <div key={task.id} className="rounded border border-[#2a2a2e] bg-[#25252b] px-3 py-2.5 cursor-pointer hover:border-[#3a3a3e] transition-colors">
                    <p className="text-sm text-[#cccccc]">{task.title}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                        task.priority === "high" ? "bg-[#4a2020] text-[#e06060]" :
                        task.priority === "medium" ? "bg-[#3a3010] text-[#c0a040]" :
                        "bg-[#2a2a30] text-[#6a6a6e]"
                      }`}>
                        {task.priority}
                      </span>
                    </div>
                  </div>
                ))}
                {items.length === 0 && (
                  <p className="py-6 text-center text-xs text-[#5a5a5e]">No tasks</p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
