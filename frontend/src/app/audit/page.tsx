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
        <h1 className="text-lg font-semibold text-[#e4e4e7]">Audit Log</h1>
        <p className="mt-0.5 text-xs text-[#a1a1aa]">Every action the teammate takes is recorded here</p>
      </div>

      <div className="space-y-1 max-w-3xl">
        {logs.map((log: any, i: number) => (
          <div key={i} className="panel flex items-center justify-between px-4 py-2.5">
            <div className="flex items-center gap-3">
              <div className={`flex h-6 w-6 items-center justify-center rounded text-[10px] ${
                log.status === "success" ? "bg-[#142a1d] text-[#4ade80]" :
                log.status === "failed" ? "bg-[#1f1010] text-[#f87171]" :
                "bg-[#262626] text-[#a1a1aa]"
              }`}>
                {log.status === "success" ? "✓" : log.status === "failed" ? "✗" : "·"}
              </div>
              <div>
                <p className="text-xs text-[#e4e4e7]">{log.action}</p>
                <p className="text-[10px] text-[#71717a]">{log.summary}</p>
              </div>
            </div>
            <span className="text-[10px] text-[#71717a]">{log.completed_at ? new Date(log.completed_at).toLocaleTimeString() : ""}</span>
          </div>
        ))}
        {logs.length === 0 && (
          <p className="py-8 text-center text-xs text-[#71717a]">No audit entries yet.</p>
        )}
      </div>
    </div>
  );
}
