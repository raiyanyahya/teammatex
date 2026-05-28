"use client";

import { useCallback, useEffect, useState } from "react";
import { Terminal, RefreshCw, Loader2 } from "lucide-react";

export default function LogsPage() {
  const [logs, setLogs] = useState("");
  const [loading, setLoading] = useState(true);
  const [service, setService] = useState("api");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/logs/${service}`);
      if (res.ok) setLogs(await res.text());
      else setLogs("Failed to load logs");
    } catch (e: any) {
      setLogs(e.message || "Error");
    }
    setLoading(false);
  }, [service]);

  useEffect(() => { load(); const i = setInterval(load, 5000); return () => clearInterval(i); }, [load]);

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#e4e4e7]">Logs</h1>
          <p className="mt-0.5 text-xs text-[#a1a1aa]">Live container logs</p>
        </div>
        <div className="flex items-center gap-2">
          {["api", "worker", "frontend", "postgres", "neo4j"].map((s) => (
            <button key={s} onClick={() => setService(s)}
              className={`rounded px-2 py-1 text-[11px] ${service === s ? "bg-[#3b82f6] text-white" : "text-[#a1a1aa] hover:text-[#e4e4e7]"}`}>
              {s}
            </button>
          ))}
          <button onClick={load} className="p-1 text-[#a1a1aa] hover:text-[#e4e4e7]"><RefreshCw className="h-3.5 w-3.5" /></button>
          <button onClick={() => { setLogs(""); setService(""); setTimeout(() => setService("api"), 100); }} className="p-1 text-[#a1a1aa] hover:text-[#e4e4e7] text-[10px]">Clear</button>
        </div>
      </div>

      <div className="panel p-4">
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-[#a1a1aa]"><Loader2 className="h-3 w-3 animate-spin" /> Loading...</div>
        ) : (
          <pre className="text-[11px] text-[#a1a1aa] font-mono whitespace-pre-wrap leading-relaxed max-h-[70vh] overflow-y-auto">{logs || "No logs"}</pre>
        )}
      </div>
    </div>
  );
}
