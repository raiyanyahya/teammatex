"use client";

import { useEffect, useState } from "react";
import { ScrollText, Activity, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";

export default function AuditPage() {
  const [logs, setLogs] = useState<any[]>([]);

  useEffect(() => {
    async function load() {
      try {
        const data = await api.get<any[]>("/knowledge/audit?limit=50");
        setLogs(data);
      } catch {}
    }
    load();
  }, []);

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-lg font-semibold text-[#cccccc]">Audit Log</h1>
        <p className="mt-0.5 text-xs text-[#6a6a6e]">Every action the teammate takes is recorded here</p>
      </div>

      <div className="space-y-1 max-w-3xl">
        {logs.map((log: any, i: number) => (
          <div key={i} className="panel flex items-center justify-between px-4 py-2.5">
            <div className="flex items-center gap-3">
              <div className={`flex h-6 w-6 items-center justify-center rounded text-[10px] ${
                log.status === "success" ? "bg-[#1e2a1e] text-[#6aaa6a]" :
                log.status === "failed" ? "bg-[#2a1515] text-[#e06060]" :
                "bg-[#2a2a30] text-[#6a6a6e]"
              }`}>
                {log.status === "success" ? "✓" : log.status === "failed" ? "✗" : "·"}
              </div>
              <div>
                <p className="text-xs text-[#cccccc]">{log.action}</p>
                <p className="text-[10px] text-[#5a5a5e]">{log.summary}</p>
              </div>
            </div>
            <span className="text-[10px] text-[#5a5a5e]">{log.completed_at ? new Date(log.completed_at).toLocaleTimeString() : ""}</span>
          </div>
        ))}
        {logs.length === 0 && (
          <p className="py-8 text-center text-xs text-[#5a5a5e]">No audit entries yet.</p>
        )}
      </div>
    </div>
  );
}
