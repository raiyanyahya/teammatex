"use client";

import { useEffect, useState } from "react";
import { Terminal, RefreshCw, Loader2 } from "lucide-react";

export default function LogsPage() {
  const [logs, setLogs] = useState("");
  const [loading, setLoading] = useState(true);
  const [service, setService] = useState("api");

  async function load() {
    setLoading(true);
    try {
      const res = await fetch(`/api/logs/${service}`);
      if (res.ok) setLogs(await res.text());
      else setLogs("Failed to load logs");
    } catch (e: any) {
      setLogs(e.message || "Error");
    }
    setLoading(false);
  }

  useEffect(() => { load(); const i = setInterval(load, 5000); return () => clearInterval(i); }, [service]);

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#cccccc]">Logs</h1>
          <p className="mt-0.5 text-xs text-[#6a6a6e]">Live container logs</p>
        </div>
        <div className="flex items-center gap-2">
          {["api", "worker", "frontend", "postgres", "neo4j"].map((s) => (
            <button key={s} onClick={() => setService(s)}
              className={`rounded px-2 py-1 text-[11px] ${service === s ? "bg-[#264f78] text-white" : "text-[#6a6a6e] hover:text-[#cccccc]"}`}>
              {s}
            </button>
          ))}
          <button onClick={load} className="p-1 text-[#6a6a6e] hover:text-[#cccccc]"><RefreshCw className="h-3.5 w-3.5" /></button>
          <button onClick={() => { setLogs(""); setService(""); setTimeout(() => setService("api"), 100); }} className="p-1 text-[#6a6a6e] hover:text-[#cccccc] text-[10px]">Clear</button>
        </div>
      </div>

      <div className="panel p-4">
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-[#6a6a6e]"><Loader2 className="h-3 w-3 animate-spin" /> Loading...</div>
        ) : (
          <pre className="text-[11px] text-[#aaaaaa] font-mono whitespace-pre-wrap leading-relaxed max-h-[70vh] overflow-y-auto">{logs || "No logs"}</pre>
        )}
      </div>
    </div>
  );
}
