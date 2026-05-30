"use client";

import { useEffect, useMemo, useState } from "react";
import { Settings } from "lucide-react";
import { api } from "@/lib/api";

type Summary = {
  total_tokens: number;
  total_cost_cents: number;
  by_provider: { provider: string; cost_cents: number }[];
};

type LogRow = {
  provider: string;
  model: string;
  call_type: string;
  tokens_in: number;
  tokens_out: number;
  cost_cents: number;
  date: string;
};

const CAT_COLORS: Record<string, string> = {
  chat: "var(--amber)",
  review: "var(--sky)",
  indexing: "var(--plum)",
  standup: "var(--sage)",
  embedding: "var(--plum)",
  completion: "var(--amber)",
};

function colorFor(call_type: string): string {
  return CAT_COLORS[call_type] || "var(--paper-3)";
}

function formatTokens(n: number): { val: string; unit: string } {
  if (n >= 1_000_000) return { val: (n / 1_000_000).toFixed(1), unit: "M" };
  if (n >= 1_000) return { val: (n / 1_000).toFixed(1), unit: "K" };
  return { val: String(n), unit: "" };
}

export default function CostsPage() {
  const [summary, setSummary] = useState<Summary>({ total_tokens: 0, total_cost_cents: 0, by_provider: [] });
  const [log, setLog] = useState<LogRow[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const [s, l] = await Promise.all([
          api.get<Summary>("/knowledge/costs/summary"),
          api.get<LogRow[]>("/knowledge/costs/log?limit=50"),
        ]);
        setSummary(s);
        setLog(Array.isArray(l) ? l : []);
      } catch {}
    })();
  }, []);

  // Drivers grouped by call_type.
  const drivers = useMemo(() => {
    const totalCents = summary.total_cost_cents || 1;
    const byType: Record<string, { cents: number; tokens: number }> = {};
    for (const r of log) {
      const key = r.call_type || "other";
      const cur = byType[key] || { cents: 0, tokens: 0 };
      cur.cents += r.cost_cents;
      cur.tokens += r.tokens_in + r.tokens_out;
      byType[key] = cur;
    }
    return Object.entries(byType)
      .map(([cat, v]) => ({ cat, cost: v.cents / 100, pct: (v.cents / totalCents) * 100, tokens: v.tokens }))
      .sort((a, b) => b.cost - a.cost)
      .slice(0, 6);
  }, [log, summary]);

  // Per-day rollup for the bars (last 14 days).
  const days = 14;
  const dayBars = useMemo(() => {
    const buckets: Record<string, number> = {};
    for (const r of log) {
      const d = (r.date || "").slice(0, 10);
      if (!d) continue;
      buckets[d] = (buckets[d] || 0) + r.cost_cents;
    }
    const sorted = Object.entries(buckets).sort(([a], [b]) => (a < b ? -1 : 1));
    const last = sorted.slice(-days);
    const max = Math.max(1, ...last.map(([, v]) => v));
    return { entries: last, max };
  }, [log]);

  const tokens = formatTokens(summary.total_tokens);
  // Sub-cent precision when the spend is tiny (cheap models), 2 decimals otherwise.
  const usd = (cents: number) => {
    const d = cents / 100;
    return d > 0 && d < 0.01 ? d.toFixed(4) : d.toFixed(2);
  };
  const spend = usd(summary.total_cost_cents);
  const avg = log.length ? (summary.total_cost_cents / 100 / log.length).toFixed(4) : "0";

  return (
    <div style={{ padding: 40 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 28 }}>
        <div>
          <h1 className="page-title">
            Costs<em>.</em>
          </h1>
          <div className="page-sub">
            self-hosted on your infra · {log.length} calls in window
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, padding: 3, background: "var(--ink-2)", borderRadius: 6, border: "1px solid var(--line)" }}>
          {(["24h", "7d", "30d", "90d"] as const).map((p) => (
            <button
              key={p}
              className="btn btn-ghost"
              style={{
                padding: "4px 10px",
                fontSize: 11,
                background: p === "30d" ? "var(--ink-3)" : "transparent",
              }}
              disabled
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 24 }}>
        <div className="card" style={{ padding: 20 }}>
          <div className="stat-val">
            ${spend}
          </div>
          <div className="stat-label">total spend</div>
        </div>
        <div className="card" style={{ padding: 20 }}>
          <div className="stat-val">
            {tokens.val}
            {tokens.unit && <span className="unit">{tokens.unit}</span>}
          </div>
          <div className="stat-label">tokens consumed</div>
        </div>
        <div className="card" style={{ padding: 20 }}>
          <div className="stat-val">${avg}</div>
          <div className="stat-label">avg cost / call</div>
        </div>
        <div className="card" style={{ padding: 20 }}>
          <div className="stat-val">{summary.by_provider.length}</div>
          <div className="stat-label">providers</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-head">
          <div className="card-title">Spend by day</div>
          <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>last {days}d</span>
        </div>
        <div style={{ padding: "24px 28px 16px" }}>
          {dayBars.entries.length === 0 ? (
            <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)" }}>
              No usage logged yet.
            </div>
          ) : (
            <svg width="100%" height="180" viewBox={`0 0 ${days * 32} 180`} preserveAspectRatio="none" style={{ display: "block" }}>
              {[0, 0.25, 0.5, 0.75, 1].map((y) => (
                <line key={y} x1="0" x2={days * 32} y1={y * 150 + 10} y2={y * 150 + 10} stroke="var(--line)" strokeWidth="1" />
              ))}
              {dayBars.entries.map(([d, v], i) => {
                const h = (v / dayBars.max) * 150;
                return (
                  <g key={d}>
                    <rect
                      x={i * 32 + 6}
                      y={160 - h}
                      width={20}
                      height={h}
                      fill="var(--amber)"
                      opacity="0.85"
                    />
                  </g>
                );
              })}
              {dayBars.entries.map(([d], i) =>
                i % 2 === 0 ? (
                  <text
                    key={`x-${d}`}
                    x={i * 32 + 16}
                    y={176}
                    fontFamily="var(--mono)"
                    fontSize="9"
                    fill="var(--paper-4)"
                    textAnchor="middle"
                  >
                    {d.slice(5)}
                  </text>
                ) : null,
              )}
            </svg>
          )}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 20 }}>
        <div className="card">
          <div className="card-head">
            <div className="card-title">Top cost drivers</div>
            <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>by call_type</span>
          </div>
          <div>
            {drivers.length === 0 ? (
              <div style={{ padding: "20px 24px" }} className="font-mono">
                <span style={{ fontSize: 11, color: "var(--paper-4)" }}>No usage logged yet.</span>
              </div>
            ) : (
              drivers.map((row) => {
                const color = colorFor(row.cat);
                return (
                  <div key={row.cat} style={{ padding: "14px 20px", borderBottom: "1px solid var(--line)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ width: 8, height: 8, borderRadius: 2, background: color, display: "inline-block" }} />
                        <span style={{ fontSize: 13, color: "var(--paper-0)" }}>{row.cat}</span>
                      </div>
                      <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
                        <span className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)" }}>
                          {formatTokens(row.tokens).val}
                          {formatTokens(row.tokens).unit}
                        </span>
                        <span className="font-mono" style={{ fontSize: 13, color: "var(--paper-0)", minWidth: 60, textAlign: "right" }}>
                          ${row.cost.toFixed(2)}
                        </span>
                      </div>
                    </div>
                    <div style={{ height: 2, background: "var(--ink-3)", borderRadius: 1, marginLeft: 18 }}>
                      <div style={{ height: "100%", width: `${Math.min(100, row.pct)}%`, background: color, borderRadius: 1 }} />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">By provider</div>
          </div>
          <div style={{ padding: 20 }}>
            {summary.by_provider.length === 0 ? (
              <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)" }}>
                No provider data yet.
              </div>
            ) : (
              summary.by_provider.map((p) => {
                const pct = summary.total_cost_cents
                  ? (p.cost_cents / summary.total_cost_cents) * 100
                  : 0;
                return (
                  <div key={p.provider} style={{ marginBottom: 12 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
                      <span className="font-mono" style={{ color: "var(--paper-3)" }}>{p.provider}</span>
                      <span className="font-mono" style={{ color: "var(--paper-0)" }}>${(p.cost_cents / 100).toFixed(2)}</span>
                    </div>
                    <div style={{ height: 2, background: "var(--ink-3)", borderRadius: 1, marginTop: 5 }}>
                      <div style={{ height: "100%", width: `${pct}%`, background: "var(--sky)", borderRadius: 1 }} />
                    </div>
                  </div>
                );
              })
            )}
            <button className="btn" style={{ marginTop: 12, width: "100%", justifyContent: "center" }} disabled>
              <Settings size={12} /> Adjust limits
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
