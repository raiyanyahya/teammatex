"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Send,
  Sparkles,
  GitBranch,
  GitPullRequest,
  Pencil,
} from "lucide-react";

type Repo = {
  id: string;
  local_name: string;
  files?: number;
  open_prs?: number;
  onboarding_pct?: number;
  health?: number;
  last_synced?: string | null;
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
type CallTypeCost = { call_type: string; tokens: number; cost_cents: number };
type Budget = {
  status: "unset" | "ok" | "warn" | "over";
  monthly_usd_limit: number | null;
  usd_used_pct: number | null;
  token_used_pct: number | null;
  month_to_date_cost_cents: number;
};
type Cost = {
  total_tokens: number;
  total_cost_cents: number;
  by_call_type?: CallTypeCost[];
  budget?: Budget;
};
type HealthCheck = { name: string; ok: boolean; detail: string; required: boolean };
type Health = { checks: HealthCheck[]; ready: boolean };
type Period = "today" | "7d" | "30d" | "all";
type GraphStats = { concepts: number };
type Contributors = { count: number };
type PRActivity = {
  repo: string;
  number: number | null;
  title: string;
  branch: string;
  status: string;
  created_at: string | null;
};

export default function Overview({ name, onRename }: { name: string; onRename: (n: string) => Promise<void> }) {
  const router = useRouter();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [onboarded, setOnboarded] = useState(0);
  const [standup, setStandup] = useState<Standup | null>(null);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [cost, setCost] = useState<Cost | null>(null);
  const [period, setPeriod] = useState<Period>("all");
  const [health, setHealth] = useState<Health | null>(null);
  const [people, setPeople] = useState<number | null>(null);
  const [concepts, setConcepts] = useState<number | null>(null);
  const [activity, setActivity] = useState<PRActivity[]>([]);
  const [ask, setAsk] = useState("");
  const [suggested, setSuggested] = useState<string[]>([]);
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
      try {
        const a = await fetch("/api/repos/activity?limit=8").then((x) => x.json());
        setActivity(Array.isArray(a) ? a : []);
      } catch {}
      try { setStandup(await fetch("/api/features/standup").then((x) => x.json())); } catch {}
      try { setAudit((await fetch("/api/knowledge/audit?limit=8").then((x) => x.json())) || []); } catch {}
      try { setHealth(await fetch("/api/integrations/health").then((x) => x.json())); } catch {}
      try {
        const c: Contributors = await fetch("/api/knowledge/contributors").then((x) => x.json());
        setPeople(c?.count ?? 0);
      } catch {}
      try {
        const g: GraphStats = await fetch("/api/knowledge/graph/stats").then((x) => x.json());
        setConcepts(g?.concepts ?? 0);
      } catch {}
      try {
        const sq = await fetch("/api/knowledge/suggested-questions").then((x) => x.json());
        setSuggested(Array.isArray(sq?.questions) ? sq.questions : []);
      } catch {}
    })();
  }, []);

  // Re-fetch cost/budget whenever the period toggle changes.
  useEffect(() => {
    (async () => {
      try {
        setCost(await fetch(`/api/knowledge/costs/summary?period=${period}`).then((x) => x.json()));
      } catch {}
    })();
  }, [period]);

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
  const spentUsd = (cost?.total_cost_cents ?? 0) / 100;
  // Show sub-cent precision when spend is tiny (cheap models), else 2 decimals.
  const spent = spentUsd > 0 && spentUsd < 0.01 ? spentUsd.toFixed(4) : spentUsd.toFixed(2);
  const budget = cost?.budget;
  const byCallType = cost?.by_call_type ?? [];
  const lastSyncedTs = repos
    .map((r) => r.last_synced)
    .filter((t): t is string => !!t)
    .sort()
    .pop();

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
                {(name || "Teammate").toUpperCase()} · KNOWLEDGE GRAPH
              </div>
              <div className="mt-1.5 font-serif text-[24px] leading-[1.1]">
                I&rsquo;ve indexed{" "}
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
              <div
                className="mt-1 font-mono text-[13px]"
                style={{ color: lastSyncedTs && isStale(lastSyncedTs) ? "var(--amber)" : "var(--paper-0)" }}
                title={lastSyncedTs ? new Date(lastSyncedTs).toLocaleString() : undefined}
              >
                {lastSyncedTs ? timeAgo(lastSyncedTs) : "never"}
              </div>
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
                placeholder={`Ask ${name || "your teammate"} anything about your codebase, team, or history…`}
                className="flex-1 bg-transparent font-serif text-[15px] outline-none"
                style={{ color: "var(--paper-0)" }}
              />
              <button onClick={() => submitAsk()} className="btn btn-primary">
                <Send size={12} /> Ask
              </button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {suggested.length > 0 ? (
                suggested.map((q) => (
                  <button
                    key={q}
                    className="tag"
                    style={{ cursor: "pointer" }}
                    onClick={() => { setAsk(q); submitAsk(q); }}
                  >
                    {q}
                  </button>
                ))
              ) : (
                <span className="font-mono text-[12px]" style={{ color: "var(--paper-4)" }}>
                  Onboard a repo to start asking questions.
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Status column */}
        <div className="flex flex-col gap-4">
          <RecentRunsCard audit={audit} />


          <div
            className="p-[18px]"
            style={{ background: "var(--ink-1)", border: "1px solid var(--line)", borderRadius: 8 }}
          >
            <div className="mb-3 flex items-center justify-between">
              <div className="font-mono text-[10px] tracking-[0.12em]" style={{ color: "var(--paper-3)" }}>
                LLM USAGE
              </div>
              <PeriodToggle period={period} onChange={setPeriod} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Stat val={formatTokens(tokens)} label="tokens used" />
              <Stat val={`$${spent}`} label="spend" />
              <Stat val={String(audit.length)} label="actions today" />
              <Stat val={String(standup?.prs.length ?? 0)} label="prs reviewed" />
            </div>
            {budget && budget.status !== "unset" && <BudgetBar budget={budget} />}
          </div>
        </div>
      </div>

      {/* Three-col: Activity / Today / Repos */}
      <div className="grid gap-6" style={{ gridTemplateColumns: "1.4fr 1fr 1fr" }}>
        <ActivityCard activity={activity} />
        <TodayCard standup={standup} />
        <ReposCard repos={repos} onboarded={onboarded} onClick={() => router.push("/repos")} />
      </div>

      {/* Spend by activity + setup checklist */}
      <div className="mt-6 grid gap-6" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <SpendByActivityCard items={byCallType} />
        <SetupChecklistCard health={health} />
      </div>
    </div>
  );
}

function PeriodToggle({ period, onChange }: { period: Period; onChange: (p: Period) => void }) {
  const opts: Period[] = ["today", "7d", "30d", "all"];
  return (
    <div className="flex gap-1">
      {opts.map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className="font-mono text-[10px] uppercase tracking-[0.06em]"
          style={{
            padding: "2px 6px",
            borderRadius: 4,
            color: p === period ? "var(--ink-0)" : "var(--paper-3)",
            background: p === period ? "var(--amber)" : "transparent",
            border: "1px solid " + (p === period ? "var(--amber)" : "var(--line)"),
            cursor: "pointer",
          }}
        >
          {p}
        </button>
      ))}
    </div>
  );
}

function BudgetBar({ budget }: { budget: Budget }) {
  const pct = Math.max(budget.usd_used_pct ?? 0, budget.token_used_pct ?? 0);
  const color =
    budget.status === "over" ? "var(--rust)" : budget.status === "warn" ? "var(--amber)" : "var(--sage)";
  return (
    <div className="mt-3.5">
      <div className="mb-1 flex justify-between font-mono text-[10px]" style={{ color: "var(--paper-3)" }}>
        <span>MONTHLY BUDGET</span>
        <span style={{ color }}>
          {pct.toFixed(0)}% {budget.status === "over" ? "· over" : budget.status === "warn" ? "· near limit" : ""}
        </span>
      </div>
      <div className="h-[3px] rounded-[2px]" style={{ background: "var(--ink-3)" }}>
        <div className="h-full rounded-[2px]" style={{ width: `${Math.min(100, pct)}%`, background: color }} />
      </div>
    </div>
  );
}

function SpendByActivityCard({ items }: { items: CallTypeCost[] }) {
  const total = items.reduce((s, i) => s + i.cost_cents, 0) || 1;
  const top = [...items].sort((a, b) => b.cost_cents - a.cost_cents).slice(0, 6);
  const colors = ["var(--amber)", "var(--sage)", "var(--sky)", "var(--plum)", "var(--rust)", "var(--paper-3)"];
  return (
    <div className="card">
      <div className="card-head">
        <div className="card-title">Token spend by activity</div>
        <span className="font-mono text-[10px]" style={{ color: "var(--paper-4)" }}>this period</span>
      </div>
      <div className="px-4 py-3">
        {top.length === 0 ? (
          <div className="py-4 font-mono text-[11px]" style={{ color: "var(--paper-4)" }}>No LLM usage yet.</div>
        ) : (
          <div className="flex flex-col gap-2.5">
            {top.map((it, i) => (
              <div key={it.call_type}>
                <div className="flex justify-between text-[12px]">
                  <span style={{ color: "var(--paper-1)" }}>{it.call_type.replace(/_/g, " ")}</span>
                  <span className="font-mono text-[11px]" style={{ color: "var(--paper-3)" }}>
                    {formatTokens(it.tokens)} · {((100 * it.cost_cents) / total).toFixed(0)}%
                  </span>
                </div>
                <div className="mt-[5px] h-[2px] rounded-[1px]" style={{ background: "var(--ink-3)" }}>
                  <div
                    className="h-full rounded-[1px]"
                    style={{ width: `${(100 * it.cost_cents) / total}%`, background: colors[i % colors.length] }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SetupChecklistCard({ health }: { health: Health | null }) {
  const checks = health?.checks ?? [];
  return (
    <div className="card">
      <div className="card-head">
        <div className="card-title">Setup checklist</div>
        <span className="font-mono text-[10px]" style={{ color: health?.ready ? "var(--sage)" : "var(--amber)" }}>
          {health?.ready ? "ready" : "needs setup"}
        </span>
      </div>
      <div>
        {checks.length === 0 ? (
          <div className="px-4 py-6 font-mono text-[11px]" style={{ color: "var(--paper-4)" }}>Checking…</div>
        ) : (
          checks.map((c, i) => (
            <div
              key={c.name}
              className="flex items-center gap-3 px-4 py-[11px]"
              style={{ borderBottom: i === checks.length - 1 ? "none" : "1px solid var(--line)" }}
            >
              <span
                className="flex h-[16px] w-[16px] items-center justify-center rounded-full"
                style={{
                  background: c.ok ? "var(--sage)" : c.required ? "var(--rust)" : "var(--ink-3)",
                  color: "var(--ink-0)",
                  fontSize: 10,
                }}
              >
                {c.ok ? "✓" : c.required ? "!" : "·"}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[13px]" style={{ color: "var(--paper-0)" }}>{c.name}</div>
              </div>
              <span className="font-mono text-[10px]" style={{ color: "var(--paper-4)" }}>{c.detail}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function timeAgo(iso: string): string {
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

function isStale(iso: string): boolean {
  // Older than 24h → flag amber so a forgotten sync is visible.
  return Date.now() - new Date(iso).getTime() > 24 * 3600 * 1000;
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

function ActivityCard({ activity }: { activity: PRActivity[] }) {
  // Real pull-request activity pulled from the watched repos (newest first).
  return (
    <div className="card">
      <div className="card-head">
        <div className="card-title">Live activity</div>
        <span className="font-mono text-[10px]" style={{ color: "var(--paper-4)" }}>recent prs</span>
      </div>
      <div>
        {activity.length === 0 ? (
          <div className="px-4 py-6 font-mono text-[11px]" style={{ color: "var(--paper-4)" }}>
            No pull-request activity yet.
          </div>
        ) : (
          activity.map((a, i) => (
            <div
              key={i}
              className="grid items-start gap-3 px-4 py-[11px]"
              style={{
                gridTemplateColumns: "auto auto 1fr auto",
                borderBottom: i === activity.length - 1 ? "none" : "1px solid var(--line)",
              }}
            >
              <span className="pt-[3px] font-mono text-[10px]" style={{ color: "var(--paper-4)" }}>
                {a.created_at ? new Date(a.created_at).toLocaleDateString([], { month: "short", day: "numeric" }) : ""}
              </span>
              <span style={{ color: "var(--sky)", marginTop: 3 }}>
                <GitPullRequest size={13} />
              </span>
              <div className="min-w-0">
                <div className="truncate text-[13px]" style={{ color: "var(--paper-0)" }}>
                  {a.number ? `#${a.number} ` : ""}{a.title}
                </div>
                <div className="mt-0.5 truncate font-mono text-[11px]" style={{ color: "var(--paper-3)" }}>
                  {a.repo}{a.branch ? ` · ${a.branch}` : ""}
                </div>
              </div>
              <span className="tag uppercase">{a.status}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
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
        <div className="card-title">Today&rsquo;s standup</div>
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
  const display = repos.slice(0, 8).map((r) => {
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
