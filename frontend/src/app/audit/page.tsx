"use client";

import { useEffect, useMemo, useState } from "react";
import {
  FileText,
  Shield,
  GitPullRequest,
  GitCommit,
  MessageSquare,
  CheckCircle2,
  Database,
  Settings,
  AlertCircle,
} from "lucide-react";
import { api } from "@/lib/api";

type Audit = {
  action: string;
  entity_type?: string | null;
  entity_id?: string | null;
  summary?: string | null;
  status?: string | null;
  completed_at?: string | null;
};

type Cat = "pr" | "commit" | "chat" | "kg" | "config" | "auth" | "system";

const CAT_META: Record<Cat, { color: string; Icon: any }> = {
  pr: { color: "sky", Icon: GitPullRequest },
  commit: { color: "plum", Icon: GitCommit },
  chat: { color: "amber", Icon: MessageSquare },
  kg: { color: "plum", Icon: Database },
  config: { color: "rust", Icon: Settings },
  auth: { color: "rust", Icon: Shield },
  system: { color: "paper-3", Icon: CheckCircle2 },
};

function categorize(a: Audit): Cat {
  const s = (a.action || "").toLowerCase();
  if (/pr|pull/.test(s)) return "pr";
  if (/commit/.test(s)) return "commit";
  if (/chat|message|answer|query/.test(s)) return "chat";
  if (/knowledge|graph|concept|embed|index/.test(s)) return "kg";
  if (/config|persona|setting/.test(s)) return "config";
  if (/auth|token|login/.test(s)) return "auth";
  return "system";
}

function riskOf(a: Audit): "low" | "medium" | "high" {
  if (a.status === "failed" || a.status === "error") return "high";
  if (a.status === "running" || a.status === "pending") return "medium";
  return "low";
}

const FILTERS: { id: "all" | Cat; label: string }[] = [
  { id: "all", label: "All" },
  { id: "pr", label: "PRs" },
  { id: "commit", label: "Commits" },
  { id: "chat", label: "Chat" },
  { id: "config", label: "Config" },
  { id: "auth", label: "Auth" },
  { id: "kg", label: "Knowledge" },
];

export default function AuditPage() {
  const [logs, setLogs] = useState<Audit[]>([]);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["id"]>("all");

  useEffect(() => {
    (async () => {
      try {
        const data = await api.get<Audit[]>("/knowledge/audit?limit=50");
        setLogs(Array.isArray(data) ? data : []);
      } catch {}
    })();
  }, []);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: logs.length };
    for (const e of logs) {
      const k = categorize(e);
      c[k] = (c[k] || 0) + 1;
    }
    return c;
  }, [logs]);

  const filtered = filter === "all" ? logs : logs.filter((e) => categorize(e) === filter);

  return (
    <div style={{ padding: 40 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 28 }}>
        <div>
          <h1 className="page-title">
            Audit<em>.</em>
          </h1>
          <div className="page-sub">
            Every action, traceable · {logs.length} {logs.length === 1 ? "entry" : "entries"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" disabled>
            <FileText size={13} /> Export CSV
          </button>
          <button className="btn" disabled>
            <Shield size={13} /> SOC2 report
          </button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap" }}>
        {FILTERS.map((f) => {
          const active = filter === f.id;
          return (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              className="btn btn-ghost"
              style={{
                fontSize: 11,
                padding: "4px 10px",
                background: active ? "var(--ink-3)" : "transparent",
                border: "1px solid " + (active ? "var(--line-strong)" : "transparent"),
              }}
            >
              {f.label}{" "}
              <span className="font-mono" style={{ color: "var(--paper-4)", marginLeft: 4 }}>
                {counts[f.id] ?? 0}
              </span>
            </button>
          );
        })}
      </div>

      <div style={{ background: "var(--ink-1)", border: "1px solid var(--line)", borderRadius: 8, overflow: "hidden" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "170px 30px 100px 1fr 1fr 60px",
            gap: 14,
            padding: "10px 20px",
            background: "var(--ink-2)",
            borderBottom: "1px solid var(--line-strong)",
            fontFamily: "var(--mono)",
            fontSize: 10,
            color: "var(--paper-3)",
            letterSpacing: "0.1em",
          }}
        >
          <span>TIMESTAMP</span>
          <span />
          <span>ACTOR</span>
          <span>ACTION</span>
          <span>TARGET / REASON</span>
          <span style={{ textAlign: "right" }}>RISK</span>
        </div>

        {filtered.length === 0 ? (
          <div style={{ padding: "40px 20px", textAlign: "center" }}>
            <p className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)" }}>
              No audit entries{filter !== "all" ? ` for ${filter}` : ""} yet.
            </p>
          </div>
        ) : (
          filtered.map((e, i) => {
            const cat = categorize(e);
            const meta = CAT_META[cat];
            const actor = cat === "kg" || cat === "auth" ? "system" : "yuji";
            const risk = riskOf(e);
            return (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "170px 30px 100px 1fr 1fr 60px",
                  gap: 14,
                  padding: "12px 20px",
                  borderBottom: "1px solid var(--line)",
                  alignItems: "center",
                  fontSize: 12,
                }}
              >
                <span className="font-mono" style={{ color: "var(--paper-4)", fontSize: 11 }}>
                  {e.completed_at ? new Date(e.completed_at).toLocaleString([], { hour12: false }) : "—"}
                </span>
                <meta.Icon size={13} style={{ color: `var(--${meta.color})` }} />
                <span
                  className="font-mono"
                  style={{ color: actor === "yuji" ? "var(--amber)" : "var(--paper-3)" }}
                >
                  {actor}
                </span>
                <span style={{ color: "var(--paper-0)" }}>{e.action}</span>
                <div>
                  <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-1)" }}>
                    {e.entity_type || "—"}
                    {e.entity_id ? ` · ${e.entity_id}` : ""}
                  </div>
                  {e.summary && (
                    <div className="font-mono" style={{ fontSize: 10, marginTop: 2, color: "var(--paper-4)" }}>
                      {e.summary}
                    </div>
                  )}
                </div>
                <span
                  className={`tag tag-${risk === "high" ? "rust" : risk === "medium" ? "amber" : "sage"}`}
                  style={{ justifySelf: "end", fontSize: 9 }}
                >
                  {risk === "high" && <AlertCircle size={9} />} {risk}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
