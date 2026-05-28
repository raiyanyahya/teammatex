"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, GitPullRequest, Play, RefreshCw } from "lucide-react";

type PR = { title: string; status: string; branch: string; who?: string };
type Task = { title: string; status: string; priority: string; who?: string; progress?: number };
type Blocker = { question: string; created_at: string | null };

type Standup = {
  name: string;
  date: string;
  yesterday: string;
  today: string;
  prs: PR[];
  tasks: Task[];
  blockers_list: Blocker[];
};

const GREETING_BY_HOUR = (h: number) =>
  h < 5 ? "Late night" : h < 12 ? "Good morning" : h < 17 ? "Afternoon" : h < 21 ? "Good evening" : "Evening";

const ROW_COLORS = ["var(--sage)", "var(--sky)", "var(--plum)", "var(--amber)"];

function relativeAge(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 60) return `${mins}m elapsed`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h elapsed`;
  return `${Math.round(hours / 24)}d elapsed`;
}

export default function StandupPage() {
  const [data, setData] = useState<Standup | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/features/standup");
      if (r.ok) setData(await r.json());
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const now = new Date();
  const dateLine = useMemo(() => {
    const day = now.toLocaleDateString([], { weekday: "long" });
    const date = now.toLocaleDateString([], { month: "long", day: "numeric", year: "numeric" });
    const time = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    return `${day} · ${date} · ${time}`;
  }, [now]);

  const greeting = GREETING_BY_HOUR(now.getHours());
  const prs = data?.prs ?? [];
  const tasks = data?.tasks ?? [];
  const blockers = data?.blockers_list ?? [];
  const blockerLead = blockers[0]?.question;

  return (
    <div style={{ padding: 40, maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 28 }}>
        <div>
          <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-3)", letterSpacing: "0.12em" }}>
            {dateLine.toUpperCase()}
          </div>
          <h1 className="page-title" style={{ marginTop: 6 }}>
            {greeting}<em>.</em>
          </h1>
          <div
            style={{
              fontFamily: "var(--serif)",
              fontSize: 18,
              color: "var(--paper-2)",
              marginTop: 6,
              maxWidth: 720,
              lineHeight: 1.5,
            }}
          >
            {blockers.length === 0 && tasks.length === 0 && prs.length === 0 ? (
              <>The team is quiet — no recent PRs, tasks, or blockers landed yet.</>
            ) : (
              <>
                {prs.length} {prs.length === 1 ? "PR" : "PRs"} shipped, {tasks.length} in flight
                {blockerLead ? (
                  <>
                    , and one thing keeping us{" "}
                    <em style={{ color: "var(--rust)", fontStyle: "italic" }}>blocked</em>.
                  </>
                ) : (
                  "."
                )}
              </>
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" disabled>
            Post to #team
          </button>
          <button className="btn btn-primary" onClick={load} disabled={loading}>
            <RefreshCw size={13} /> Regenerate
          </button>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          border: "1px solid var(--line)",
          borderRadius: 8,
          overflow: "hidden",
          marginBottom: 28,
        }}
      >
        {[
          { label: "PRs", val: prs.length },
          { label: "Tasks", val: tasks.length },
          { label: "Blockers", val: blockers.length, accent: blockers.length ? "var(--rust)" : undefined },
          { label: "Repos", val: new Set(prs.map((p) => p.branch?.split("/")[0])).size || "—" },
        ].map((m, i) => (
          <div
            key={i}
            style={{
              padding: "16px 20px",
              borderRight: i < 3 ? "1px solid var(--line)" : "none",
              background: "var(--ink-1)",
            }}
          >
            <div
              className="font-mono"
              style={{
                fontSize: 10,
                color: m.accent || "var(--paper-3)",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
              }}
            >
              {m.label}
            </div>
            <div style={{ fontFamily: "var(--serif)", fontSize: 32, lineHeight: 1, color: "var(--paper-0)", marginTop: 6 }}>
              {m.val}
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 20, marginBottom: 32 }}>
        <div className="card">
          <div className="card-head">
            <div className="card-title">Yesterday</div>
            <GitPullRequest size={12} style={{ color: "var(--sage)" }} />
          </div>
          <div>
            {prs.length === 0 ? (
              <div style={{ padding: "20px 16px" }}>
                <p className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)" }}>
                  No PR activity in the last 24h.
                </p>
              </div>
            ) : (
              prs.slice(0, 6).map((p, i) => (
                <div key={i} style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span className="font-mono" style={{ fontSize: 11, color: "var(--sage)" }}>{p.status}</span>
                    {p.branch && (
                      <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>{p.branch}</span>
                    )}
                  </div>
                  <div style={{ fontSize: 13, marginTop: 4, color: "var(--paper-0)" }}>{p.title}</div>
                  {p.who && (
                    <div className="font-mono" style={{ fontSize: 10, marginTop: 4, color: "var(--paper-4)" }}>
                      @{p.who}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title">Today</div>
            <Play size={11} style={{ color: "var(--amber)" }} />
          </div>
          <div>
            {tasks.length === 0 ? (
              <div style={{ padding: "20px 16px" }}>
                <p className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)" }}>
                  Monitoring for new tasks.
                </p>
              </div>
            ) : (
              tasks.slice(0, 6).map((t, i) => {
                const color = ROW_COLORS[i % ROW_COLORS.length];
                const pct = t.progress ?? 0;
                return (
                  <div key={i} style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)" }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span className="font-mono" style={{ fontSize: 11, color: "var(--paper-3)" }}>
                        @{t.who || "unassigned"}
                      </span>
                      <span className="font-mono" style={{ fontSize: 11, color: "var(--amber)" }}>{pct}%</span>
                    </div>
                    <div style={{ fontSize: 13, marginTop: 4, color: "var(--paper-0)" }}>{t.title}</div>
                    <div style={{ marginTop: 8, height: 2, background: "var(--ink-3)", borderRadius: 1 }}>
                      <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 1 }} />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <div className="card-title" style={{ color: blockers.length ? "var(--rust)" : undefined }}>
              Blockers
            </div>
            <AlertTriangle size={12} style={{ color: blockers.length ? "var(--rust)" : "var(--paper-4)" }} />
          </div>
          <div style={{ padding: 16 }}>
            {blockers.length === 0 ? (
              <div
                style={{
                  padding: 14,
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <CheckCircle2 size={14} style={{ color: "var(--sage)" }} />
                <span className="font-mono" style={{ fontSize: 11, color: "var(--sage)" }}>
                  NO OPEN BLOCKERS
                </span>
              </div>
            ) : (
              blockers.slice(0, 3).map((b, i) => (
                <div
                  key={i}
                  style={{
                    padding: 14,
                    marginBottom: 10,
                    border: "1px solid rgba(194, 116, 95, 0.3)",
                    background: "rgba(194, 116, 95, 0.05)",
                    borderRadius: 6,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <span className="tag tag-rust" style={{ fontSize: 9 }}>blocked</span>
                    {b.created_at && (
                      <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>
                        {relativeAge(b.created_at)}
                      </span>
                    )}
                  </div>
                  <div style={{ fontFamily: "var(--serif)", fontSize: 16, lineHeight: 1.4, color: "var(--paper-0)" }}>
                    {b.question}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <div
        className="card"
        style={{
          padding: "28px 32px",
          background: "linear-gradient(180deg, rgba(212, 165, 116, 0.04), transparent)",
        }}
      >
        <div className="font-mono" style={{ fontSize: 10, color: "var(--amber)", letterSpacing: "0.12em" }}>
          {(data?.name || "YUJI").toUpperCase()}&rsquo;S TAKE
        </div>
        <div
          style={{
            fontFamily: "var(--serif)",
            fontSize: 19,
            lineHeight: 1.55,
            color: "var(--paper-0)",
            marginTop: 12,
            maxWidth: 780,
          }}
        >
          {data?.yesterday && data.yesterday !== "No PR activity."
            ? data.yesterday
            : "Quiet day on the activity feed. I'll keep watching for new PRs and tasks, and surface anything that looks urgent."}
          {data?.today && data.today !== "Monitoring for new tasks." && (
            <>
              {" "}
              <em style={{ color: "var(--amber)", fontStyle: "italic" }}>{data.today}</em>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
