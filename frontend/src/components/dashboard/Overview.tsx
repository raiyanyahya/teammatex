"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Send,
  Sparkles,
  GitBranch,
  GitPullRequest,
  GitCommit,
  MessageSquare,
  CheckCircle2,
  AlertTriangle,
  BookOpen,
  Pencil,
} from "lucide-react";

type Repo = {
  id: string;
  local_name: string;
  files?: number;
  open_prs?: number;
  onboarding_pct?: number;
  health?: number;
};
type Audit = { action: string; summary: string; status: string; completed_at: string };
type StandupTask = { title: string; who: string; progress: number; status?: string };
type StandupPR = { title: string; status: string; branch: string; who: string };
type StandupBlocker = { question: string; created_at?: string | null };
type Standup = {
  yesterday?: string;
  today?: string;
  prs: StandupPR[];
  tasks: StandupTask[];
  blockers_list: StandupBlocker[];
};
type Cost = { total_tokens: number; total_cost_cents: number };
type GraphStats = { concepts: number };
type Contributors = { count: number };

const SUGGESTED = [
  "Why is the build slow on kit-fork?",
  "Summarize this week's PRs",
  "Who knows the billing module?",
  "Find security issues in zapq",
];

export default function Overview({ name, onRename }: { name: string; onRename: (n: string) => Promise<void> }) {
  const router = useRouter();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [onboarded, setOnboarded] = useState(0);
  const [standup, setStandup] = useState<Standup | null>(null);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [cost, setCost] = useState<Cost | null>(null);
  const [people, setPeople] = useState<number | null>(null);
  const [concepts, setConcepts] = useState<number | null>(null);
  const [ask, setAsk] = useState("");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);

  useEffect(() => {
    (async () => {
      try {
        const list: Repo[] = await fetch("/api/repos").then((x) => x.json());
        const safe = Array.isArray(list) ? list : [];
        setRepos(safe);
        let done = 0;
        await Promise.all(
          safe.map(async (repo) => {
            try {
              const s = await fetch(`/api/repos/${repo.id}/onboarding`).then((x) => x.json());
              if ((s.stages || []).filter((st: any) => st.status === "completed").length >= 12) done++;
            } catch {}
          }),
        );
        setOnboarded(done);
      } catch {}
      try { setStandup(await fetch("/api/features/standup").then((x) => x.json())); } catch {}
      try { setAudit((await fetch("/api/knowledge/audit?limit=8").then((x) => x.json())) || []); } catch {}
      try { setCost(await fetch("/api/knowledge/costs/summary").then((x) => x.json())); } catch {}
      try {
        const c: Contributors = await fetch("/api/knowledge/contributors").then((x) => x.json());
        setPeople(c?.count ?? 0);
      } catch {}
      try {
        const g: GraphStats = await fetch("/api/knowledge/graph/stats").then((x) => x.json());
        setConcepts(g?.concepts ?? 0);
      } catch {}
    })();
  }, []);

  function submitAsk(q?: string) {
    const v = (q ?? ask).trim();
    router.push(`/chat${v ? `?q=${encodeURIComponent(v)}` : ""}`);
  }
  async function saveName() {
    await onRename(draft);
    setEditing(false);
  }

  const repoCount = repos.length;
  const tokens = cost?.total_tokens ?? 0;
  const spent = ((cost?.total_cost_cents ?? 0) / 100).toFixed(2);

  return (
    <div className="p-10">
      {/* Name header */}
      <div className="mb-7 flex items-center gap-2">
        {editing ? (
          <>
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && saveName()}
              className="input w-56"
            />
            <button onClick={saveName} className="btn btn-primary">Save</button>
          </>
        ) : (
          <>
            <h1 className="font-serif text-[28px] leading-none tracking-[-0.02em]" style={{ color: "var(--paper-0)" }}>
              {name || "Your teammate"}
            </h1>
            <button
              onClick={() => { setDraft(name); setEditing(true); }}
              className="ml-1 transition-colors"
              style={{ color: "var(--paper-4)" }}
              aria-label="Rename teammate"
            >
              <Pencil className="h-4 w-4" />
            </button>
            <span className="ml-2 font-mono text-[11px] uppercase tracking-[0.06em]" style={{ color: "var(--paper-3)" }}>
              watching {repoCount} {repoCount === 1 ? "repo" : "repos"}
            </span>
          </>
        )}
      </div>

      {/* HERO */}
      <div className="mb-7 grid gap-6" style={{ gridTemplateColumns: "1fr 320px" }}>
        <div
          className="relative overflow-hidden"
          style={{ background: "var(--ink-1)", border: "1px solid var(--line)", borderRadius: 8 }}
        >
          <div
            className="flex items-center justify-between px-6 py-5"
            style={{ borderBottom: "1px solid var(--line)" }}
          >
            <div>
              <div className="font-mono text-[10px] tracking-[0.12em]" style={{ color: "var(--paper-3)" }}>
                {name.toUpperCase()} · KNOWLEDGE GRAPH
              </div>
              <div className="mt-1.5 font-serif text-[24px] leading-[1.1]">
                I've indexed{" "}
                <em className="italic" style={{ color: "var(--amber)" }}>
                  {repoCount} {repoCount === 1 ? "repo" : "repos"}
                </em>
                ,{" "}
                <em className="italic" style={{ color: "var(--sage)" }}>
                  {people ?? "…"} {people === 1 ? "person" : "people"}
                </em>,
                <br />
                and{" "}
                <em className="italic" style={{ color: "var(--plum)" }}>
                  {concepts === null ? "…" : concepts.toLocaleString()} concepts
                </em>{" "}
                across your team.
              </div>
            </div>
            <div className="text-right">
              <div className="font-mono text-[10px] tracking-[0.1em]" style={{ color: "var(--paper-3)" }}>
                LAST SYNCED
              </div>
              <div className="mt-1 font-mono text-[13px]" style={{ color: "var(--paper-0)" }}>2m ago</div>
            </div>
          </div>
          <div
            className="px-5 py-4"
            style={{ background: "var(--ink-0)" }}
          >
            <div className="flex items-center gap-3">
              <Sparkles size={14} style={{ color: "var(--amber)" }} />
              <input
                value={ask}
                onChange={(e) => setAsk(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submitAsk()}
                placeholder={`Ask ${name} anything about your codebase, team, or history…`}
                className="flex-1 bg-transparent font-serif text-[15px] outline-none"
                style={{ color: "var(--paper-0)" }}
              />
              <button onClick={() => submitAsk()} className="btn btn-primary">
                <Send size={12} /> Ask
              </button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {SUGGESTED.map((q) => (
                <button
                  key={q}
                  className="tag"
                  style={{ cursor: "pointer" }}
                  onClick={() => { setAsk(q); submitAsk(q); }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Status column */}
        <div className="flex flex-col gap-4">
          <RecentRunsCard audit={audit} />


          <div
            className="grid grid-cols-2 gap-4 p-[18px]"
            style={{ background: "var(--ink-1)", border: "1px solid var(--line)", borderRadius: 8 }}
          >
            <Stat val={formatTokens(tokens)} label="tokens used" />
            <Stat val={`$${spent}`} label="today" />
            <Stat val={String(audit.length)} label="actions today" />
            <Stat val={String(standup?.prs.length ?? 0)} label="prs reviewed" />
          </div>
        </div>
      </div>

      {/* Three-col: Activity / Today / Repos */}
      <div className="grid gap-6" style={{ gridTemplateColumns: "1.4fr 1fr 1fr" }}>
        <ActivityCard audit={audit} />
        <TodayCard standup={standup} />
        <ReposCard repos={repos} onboarded={onboarded} onClick={() => router.push("/repos")} />
      </div>
    </div>
  );
}

function RecentRunsCard({ audit }: { audit: Audit[] }) {
  const runs = audit.slice(0, 4);
  return (
    <div className="p-[18px]" style={{ background: "var(--ink-1)", border: "1px solid var(--line)", borderRadius: 8 }}>
      <div className="mb-3.5 flex items-center justify-between">
        <div className="font-mono text-[10px] tracking-[0.12em]" style={{ color: "var(--paper-3)" }}>
          RECENT AGENT RUNS
        </div>
        <span className="font-mono text-[10px]" style={{ color: "var(--paper-4)" }}>
          {audit.length} today
        </span>
      </div>
      {runs.length === 0 ? (
        <div className="font-mono text-[11px]" style={{ color: "var(--paper-4)" }}>
          No recent runs.
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {runs.map((a, i) => (
            <div key={i} className="flex items-start gap-2 text-[12px]" style={{ color: "var(--paper-1)" }}>
              <span
                className="mt-[6px] h-[5px] w-[5px] shrink-0 rounded-full"
                style={{ background: colorForStatus(a.status) }}
              />
              <div className="min-w-0 flex-1">
                <div className="truncate" style={{ color: "var(--paper-0)" }}>{a.action}</div>
                {a.summary && (
                  <div className="truncate font-mono text-[10px]" style={{ color: "var(--paper-4)" }}>
                    {a.summary}
                  </div>
                )}
              </div>
              <span className="font-mono text-[10px]" style={{ color: "var(--paper-4)" }}>
                {a.completed_at ? new Date(a.completed_at).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit" }) : ""}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ val, label }: { val: string; label: string }) {
  return (
    <div>
      <div className="stat-val" style={{ fontSize: 32 }}>{val}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function formatTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

function ActivityCard({ audit }: { audit: Audit[] }) {
  // Use real audit when available, otherwise gentle mock that matches the design vocabulary.
  const items =
    audit.length > 0
      ? audit.slice(0, 7).map((a, i) => ({
          t: new Date(a.completed_at || Date.now()).toLocaleTimeString([], { hour12: false }),
          icon: iconForAction(a.action),
          color: colorForStatus(a.status),
          text: a.action,
          sub: a.summary || "",
          tag: a.status,
        }))
      : DEMO_ACTIVITY;

  return (
    <div className="card">
      <div className="card-head">
        <div className="card-title">Live activity</div>
        <span className="font-mono text-[10px]" style={{ color: "var(--paper-4)" }}>last 1h</span>
      </div>
      <div>
        {items.map((a, i) => (
          <div
            key={i}
            className="grid items-start gap-3 px-4 py-[11px]"
            style={{
              gridTemplateColumns: "auto auto 1fr auto",
              borderBottom: i === items.length - 1 ? "none" : "1px solid var(--line)",
            }}
          >
            <span className="pt-[3px] font-mono text-[10px]" style={{ color: "var(--paper-4)" }}>{a.t}</span>
            <span style={{ color: a.color, marginTop: 3 }}>
              <a.icon size={13} />
            </span>
            <div>
              <div className="text-[13px]" style={{ color: "var(--paper-0)" }}>{a.text}</div>
              <div className="mt-0.5 font-mono text-[11px]" style={{ color: "var(--paper-3)" }}>{a.sub}</div>
            </div>
            <span className="tag uppercase">{a.tag}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const DEMO_ACTIVITY = [
  { t: "12:47:02", icon: GitPullRequest, color: "var(--sky)", text: "Opened PR #847 in build-pipe-frk", sub: "docs: clarify retry semantics", tag: "pr" },
  { t: "12:44:18", icon: MessageSquare, color: "var(--amber)", text: "Answered maya's question in #eng", sub: '"how does the queue handle backpressure?"', tag: "chat" },
  { t: "12:38:55", icon: CheckCircle2, color: "var(--sage)", text: "Resolved Jira KIT-2104", sub: "auth token refresh race condition", tag: "jira" },
  { t: "12:31:09", icon: GitCommit, color: "var(--paper-2)", text: "Pushed 3 commits to feat/rate-limit", sub: "kit-fork · co-authored with @arun", tag: "commit" },
  { t: "12:22:40", icon: BookOpen, color: "var(--plum)", text: "Updated knowledge graph", sub: "+47 concepts from history mining", tag: "kg" },
  { t: "12:15:01", icon: AlertTriangle, color: "var(--rust)", text: "Flagged regression risk in #847", sub: "callsite at queue.ts:142 may deadlock", tag: "alert" },
  { t: "12:08:33", icon: MessageSquare, color: "var(--paper-2)", text: "Posted standup in #team-platform", sub: "3 blockers identified for jin", tag: "slack" },
];

function iconForAction(action: string) {
  if (/pr|pull/i.test(action)) return GitPullRequest;
  if (/commit/i.test(action)) return GitCommit;
  if (/chat|message|answer/i.test(action)) return MessageSquare;
  if (/alert|warn/i.test(action)) return AlertTriangle;
  if (/knowledge|index|concept/i.test(action)) return BookOpen;
  return CheckCircle2;
}

function colorForStatus(status: string) {
  if (status === "success") return "var(--sage)";
  if (status === "failed" || status === "error") return "var(--rust)";
  if (status === "running" || status === "pending") return "var(--amber)";
  return "var(--paper-2)";
}

const ROW_COLORS = ["var(--sage)", "var(--sky)", "var(--plum)", "var(--amber)"];

function TodayCard({ standup }: { standup: Standup | null }) {
  const prs = standup?.prs ?? [];
  const tasks = standup?.tasks ?? [];
  const blockers = standup?.blockers_list ?? [];

  return (
    <div className="card">
      <div className="card-head">
        <div className="card-title">Today's standup</div>
        <span className="font-mono text-[10px]" style={{ color: "var(--paper-4)" }}>auto · 9:00</span>
      </div>
      <div>
        <div className="px-4 py-3.5" style={{ borderBottom: "1px solid var(--line)" }}>
          <div className="font-mono text-[10px] tracking-[0.1em]" style={{ color: "var(--paper-3)" }}>
            YESTERDAY · {prs.length} {prs.length === 1 ? "pr" : "prs"}
          </div>
          <div className="mt-2 font-serif text-[14px] leading-[1.45]" style={{ color: "var(--paper-1)" }}>
            {prs.length === 0
              ? (standup?.yesterday || "No PR activity in the last 24h.")
              : prs.slice(0, 3).map((p) => p.title).join(" · ")}
          </div>
        </div>
        <div className="px-4 py-3.5" style={{ borderBottom: "1px solid var(--line)" }}>
          <div className="font-mono text-[10px] tracking-[0.1em]" style={{ color: "var(--paper-3)" }}>
            TODAY · {tasks.length} in flight
          </div>
          {tasks.length === 0 ? (
            <div className="mt-2 font-mono text-[11px]" style={{ color: "var(--paper-4)" }}>
              No tasks in flight.
            </div>
          ) : (
            <div className="mt-2.5 flex flex-col gap-2">
              {tasks.slice(0, 4).map((row, i) => {
                const color = ROW_COLORS[i % ROW_COLORS.length];
                return (
                  <div key={i}>
                    <div className="flex justify-between text-[12px]">
                      <span className="truncate">
                        <span style={{ color: "var(--paper-3)" }}>@{row.who || "unassigned"}</span> {row.title}
                      </span>
                      <span className="font-mono text-[10px]" style={{ color: "var(--paper-4)" }}>{row.progress}%</span>
                    </div>
                    <div className="mt-[5px] h-[2px] rounded-[1px]" style={{ background: "var(--ink-3)" }}>
                      <div className="h-full rounded-[1px]" style={{ width: `${row.progress}%`, background: color }} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
        <div className="px-4 py-3.5">
          <div className="font-mono text-[10px] tracking-[0.1em]" style={{ color: blockers.length ? "var(--rust)" : "var(--paper-3)" }}>
            BLOCKERS · {blockers.length}
          </div>
          {blockers.length === 0 ? (
            <div className="mt-2 font-mono text-[11px]" style={{ color: "var(--paper-4)" }}>
              No open blockers.
            </div>
          ) : (
            <div className="mt-2 flex flex-col gap-1.5 text-[12px]" style={{ color: "var(--paper-1)" }}>
              {blockers.slice(0, 3).map((b, i) => (
                <div key={i} className="truncate">{b.question}</div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function statusForHealth(h: number): string {
  if (h >= 85) return "sage";
  if (h >= 60) return "amber";
  return "rust";
}

function ReposCard({ repos, onboarded, onClick }: { repos: Repo[]; onboarded: number; onClick: () => void }) {
  const display = repos.slice(0, 4).map((r) => {
    const health = r.health ?? 0;
    return {
      name: r.local_name,
      files: r.files ?? 0,
      prs: r.open_prs ?? 0,
      health,
      status: statusForHealth(health),
    };
  });

  return (
    <div className="card">
      <div className="card-head">
        <div className="card-title">Repository health</div>
        <button className="font-mono text-[10px]" style={{ color: "var(--paper-4)" }} onClick={onClick}>
          {repos.length} watched
        </button>
      </div>
      <div>
        {display.length === 0 ? (
          <div className="px-4 py-6 font-mono text-[11px]" style={{ color: "var(--paper-4)" }}>
            No repos onboarded yet.
          </div>
        ) : (
          display.map((r, i) => (
            <div
              key={i}
              className="flex items-center gap-3 px-4 py-3"
              style={{ borderBottom: i === display.length - 1 ? "none" : "1px solid var(--line)" }}
            >
              <GitBranch size={12} style={{ color: "var(--paper-3)" }} />
              <div className="flex-1 min-w-0">
                <div className="font-mono text-[12px] truncate" style={{ color: "var(--paper-0)" }}>{r.name}</div>
                <div className="mt-0.5 font-mono text-[10px]" style={{ color: "var(--paper-4)" }}>
                  {r.files.toLocaleString()} files · {r.prs} open {r.prs === 1 ? "pr" : "prs"}
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono text-[12px]" style={{ color: `var(--${r.status})` }}>{r.health}</div>
                <div className="font-mono text-[9px] tracking-[0.1em]" style={{ color: "var(--paper-4)" }}>HEALTH</div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
