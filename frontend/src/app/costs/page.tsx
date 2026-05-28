"use client";

import { useEffect, useState } from "react";
import { BarChart3, Zap, DollarSign } from "lucide-react";
import { api } from "@/lib/api";

export default function CostsPage() {
  const [costs, setCosts] = useState<{ total_tokens: number; total_cost_cents: number; by_provider: any[] }>({
    total_tokens: 0, total_cost_cents: 0, by_provider: [],
  });
  const [logs, setLogs] = useState<any[]>([]);

  useEffect(() => {
    async function load() {
      try {
        const [summary, logData] = await Promise.all([
          api.get<any>("/knowledge/costs/summary"),
          api.get<any[]>("/knowledge/costs/log?limit=20"),
        ]);
        setCosts(summary);
        setLogs(logData);
      } catch {}
    }
    load();
  }, []);

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-lg font-semibold text-[#e4e4e7]">Costs & Usage</h1>
        <p className="mt-0.5 text-xs text-[#a1a1aa]">LLM token usage and spending</p>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-8 max-w-2xl">
        <div className="panel px-4 py-3.5">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="h-3.5 w-3.5 text-[#a1a1aa]" />
            <span className="text-[11px] text-[#a1a1aa] uppercase tracking-wide">Total tokens</span>
          </div>
          <div className="text-xl font-semibold text-[#e4e4e7]">{costs.total_tokens.toLocaleString()}</div>
        </div>
        <div className="panel px-4 py-3.5">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="h-3.5 w-3.5 text-[#a1a1aa]" />
            <span className="text-[11px] text-[#a1a1aa] uppercase tracking-wide">Total cost</span>
          </div>
          <div className="text-xl font-semibold text-[#e4e4e7]">${(costs.total_cost_cents / 100).toFixed(2)}</div>
        </div>
      </div>

      <div className="space-y-1 max-w-2xl">
        {logs.map((log: any, i: number) => (
          <div key={i} className="panel flex items-center justify-between px-4 py-2.5">
            <div className="flex items-center gap-3">
              <span className="text-xs text-[#a1a1aa]">{log.provider}</span>
              <span className="text-xs text-[#71717a]">{log.model}</span>
              <span className="text-[10px] text-[#71717a]">{log.call_type}</span>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-xs text-[#a1a1aa]">{(log.tokens_in + log.tokens_out).toLocaleString()} tokens</span>
              <span className="text-xs text-[#a1a1aa]">${(log.cost_cents / 100).toFixed(4)}</span>
            </div>
          </div>
        ))}
        {logs.length === 0 && (
          <p className="py-8 text-center text-xs text-[#71717a]">No usage data yet. Start using the chat to see costs.</p>
        )}
      </div>
    </div>
  );
}
