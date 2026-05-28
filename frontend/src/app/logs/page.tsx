"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FileText, Pause, Play } from "lucide-react";

const LEVELS: Record<string, { color: string; tag: string }> = {
  info: { color: "var(--paper-3)", tag: "INFO" },
  ok: { color: "var(--sage)", tag: " OK " },
  warn: { color: "var(--amber)", tag: "WARN" },
  err: { color: "var(--rust)", tag: "ERR " },
  dbg: { color: "var(--paper-4)", tag: "DBG " },
};

type Row = { t: string; lvl: keyof typeof LEVELS; src: string; msg: string };

function parseLog(line: string): Row {
  // Best-effort parse: pick a level from common patterns, strip ANSI, keep first source-ish token.
  const stripped = line.replace(/\x1b\[[0-9;]*m/g, "");
  const tMatch = stripped.match(/\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b/);
  const t = tMatch ? tMatch[0].slice(0, 12) : "";
  const lower = stripped.toLowerCase();
  let lvl: Row["lvl"] = "info";
  if (/\berror\b|\bfail/.test(lower)) lvl = "err";
  else if (/\bwarn/.test(lower)) lvl = "warn";
  else if (/\bdebug\b|\btrace\b/.test(lower)) lvl = "dbg";
  else if (/\bok\b|\bsuccess\b|\bdone\b/.test(lower)) lvl = "ok";
  const srcMatch = stripped.match(/\b([a-z][\w.]+):/i);
  const src = srcMatch ? srcMatch[1].slice(0, 20) : "";
  return { t, lvl, src, msg: stripped.trim() };
}

const SERVICES = ["api", "worker", "frontend", "postgres", "neo4j"];

export default function LogsPage() {
  const [service, setService] = useState<string>("api");
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState<"all" | keyof typeof LEVELS>("all");
  const [rows, setRows] = useState<Row[]>([]);
  const tailRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`/api/logs/${service}`);
      if (!res.ok) {
        setRows([{ t: "", lvl: "err", src: "fetch", msg: `${res.status} ${res.statusText}` }]);
        return;
      }
      const text = await res.text();
      const lines = text.split(/\r?\n/).filter(Boolean).slice(-200);
      setRows(lines.map(parseLog));
    } catch (e: any) {
      setRows([{ t: "", lvl: "err", src: "fetch", msg: e.message || "error" }]);
    }
  }, [service]);

  useEffect(() => {
    load();
    if (paused) return;
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load, paused]);

  useEffect(() => {
    if (!paused) tailRef.current?.scrollIntoView({ block: "end" });
  }, [rows, paused]);

  const filtered = useMemo(
    () => (filter === "all" ? rows : rows.filter((r) => r.lvl === filter)),
    [rows, filter],
  );

  return (
    <div style={{ padding: 40, display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 20 }}>
        <div>
          <h1 className="page-title">
            Logs<em>.</em>
          </h1>
          <div className="page-sub">
            {service} · {paused ? "paused" : "live"} · {rows.length} entries buffered
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <div style={{ display: "flex", gap: 4, padding: 3, background: "var(--ink-2)", borderRadius: 6, border: "1px solid var(--line)" }}>
            {SERVICES.map((s) => (
              <button
                key={s}
                onClick={() => setService(s)}
                className="btn btn-ghost"
                style={{
                  padding: "4px 10px",
                  fontSize: 11,
                  fontFamily: "var(--mono)",
                  background: service === s ? "var(--ink-3)" : "transparent",
                  color: service === s ? "var(--paper-0)" : "var(--paper-3)",
                }}
              >
                {s}
              </button>
            ))}
          </div>
          <button className="btn" onClick={() => setPaused((p) => !p)}>
            {paused ? <Play size={11} /> : <Pause size={11} />} {paused ? "Resume" : "Pause"}
          </button>
          <button className="btn" disabled>
            <FileText size={13} /> Export
          </button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        {(["all", "info", "ok", "warn", "err", "dbg"] as const).map((l) => {
          const active = filter === l;
          const color = l === "all" ? "var(--paper-0)" : LEVELS[l].color;
          return (
            <button
              key={l}
              onClick={() => setFilter(l)}
              className="btn btn-ghost"
              style={{
                fontSize: 11,
                padding: "3px 9px",
                fontFamily: "var(--mono)",
                background: active ? "var(--ink-3)" : "transparent",
                border: "1px solid " + (active ? "var(--line-strong)" : "transparent"),
                color,
                textTransform: "uppercase",
              }}
            >
              {l}
            </button>
          );
        })}
      </div>

      <div
        style={{
          flex: 1,
          background: "var(--ink-0)",
          border: "1px solid var(--line)",
          borderRadius: 8,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        }}
      >
        <div
          style={{
            padding: "8px 16px",
            background: "var(--ink-2)",
            borderBottom: "1px solid var(--line-strong)",
            display: "flex",
            gap: 14,
            fontFamily: "var(--mono)",
            fontSize: 10,
            color: "var(--paper-3)",
            letterSpacing: "0.1em",
          }}
        >
          <span>
            ● {paused ? "paused" : <span style={{ color: "var(--sage)" }}>streaming</span>}
          </span>
          <span>buffer: {rows.length} / 200</span>
          <span style={{ marginLeft: "auto" }}>tail -f /var/log/teammatex/{service}.log</span>
        </div>
        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "12px 16px",
            fontFamily: "var(--mono)",
            fontSize: 11,
            lineHeight: 1.6,
            minHeight: 0,
          }}
        >
          {filtered.length === 0 ? (
            <div style={{ color: "var(--paper-4)" }}>No log lines yet.</div>
          ) : (
            filtered.map((r, i) => (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "110px 50px 130px 1fr",
                  gap: 12,
                  color: "var(--paper-1)",
                  padding: "1px 0",
                }}
              >
                <span style={{ color: "var(--paper-4)" }}>{r.t}</span>
                <span style={{ color: LEVELS[r.lvl].color, fontWeight: 600 }}>[{LEVELS[r.lvl].tag}]</span>
                <span style={{ color: "var(--sky)" }}>{r.src}</span>
                <span>{r.msg}</span>
              </div>
            ))
          )}
          <div ref={tailRef} />
        </div>
      </div>
    </div>
  );
}
