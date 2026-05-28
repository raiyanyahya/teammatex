"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { GitBranch, ListChecks, ScrollText, BarChart3, Pencil, Check, Send, ArrowRight } from "lucide-react";

type Repo = { id: string; local_name: string };
type Audit = { action: string; summary: string; status: string; completed_at: string };
type Standup = { prs: any[]; tasks: any[]; blockers_list: any[] };
type Cost = { total_tokens: number; total_cost_cents: number };

export default function Overview({ name, onRename }: { name: string; onRename: (n: string) => Promise<void> }) {
  const router = useRouter();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [onboarded, setOnboarded] = useState(0);
  const [standup, setStandup] = useState<Standup | null>(null);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [cost, setCost] = useState<Cost | null>(null);
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
        await Promise.all(safe.map(async (repo) => {
          try {
            const s = await fetch(`/api/repos/${repo.id}/onboarding`).then((x) => x.json());
            if ((s.stages || []).filter((st: any) => st.status === "completed").length >= 12) done++;
          } catch {}
        }));
        setOnboarded(done);
      } catch {}
      try { setStandup(await fetch("/api/features/standup").then((x) => x.json())); } catch {}
      try { setAudit((await fetch("/api/knowledge/audit?limit=5").then((x) => x.json())) || []); } catch {}
      try { setCost(await fetch("/api/knowledge/costs/summary").then((x) => x.json())); } catch {}
    })();
  }, []);

  function submitAsk() {
    const q = ask.trim();
    router.push(`/chat${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  }
  async function saveName() {
    await onRename(draft);
    setEditing(false);
  }

  const repoCount = repos.length;
  const inProgress = repoCount - onboarded;

  return (
    <div className="mx-auto max-w-5xl p-8">
      <div className="mb-6 flex items-center gap-2">
        {editing ? (
          <>
            <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && saveName()} className="input w-56" />
            <button onClick={saveName} className="btn-primary text-sm"><Check className="h-4 w-4" /> Save</button>
          </>
        ) : (
          <>
            <h1 className="text-2xl font-semibold tracking-tight text-[#e4e4e7]">{name || "Your teammate"}</h1>
            <button onClick={() => { setDraft(name); setEditing(true); }} className="ml-1 text-[#52525b] transition-colors hover:text-[#a1a1aa]" aria-label="Rename teammate">
              <Pencil className="h-4 w-4" />
            </button>
            <span className="ml-2 text-sm text-[#a1a1aa]">is watching {repoCount} {repoCount === 1 ? "repository" : "repositories"}</span>
          </>
        )}
      </div>

      <div className="mb-6 flex gap-2">
        <input value={ask} onChange={(e) => setAsk(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submitAsk()} placeholder={`Ask ${name || "your teammate"} about your code…`} className="input flex-1 py-2 text-[15px]" />
        <button onClick={submitAsk} className="btn-primary px-4"><Send className="h-4 w-4" /> Ask</button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card title="Repositories" tile="tile-blue" icon={<GitBranch className="h-[18px] w-[18px]" />} onClick={() => router.push("/repos")}>
          <Stat big={repoCount} label="connected" />
          <p className="mt-2.5 text-[13px] text-[#a1a1aa]">{onboarded} fully onboarded{inProgress > 0 ? ` · ${inProgress} in progress` : ""}</p>
        </Card>

        <Card title="Today's standup" tile="tile-green" icon={<ListChecks className="h-[18px] w-[18px]" />} onClick={() => router.push("/standup")}>
          {standup ? (
            <div className="flex gap-8">
              <Stat big={standup.prs.length} label="PRs" />
              <Stat big={standup.tasks.length} label="tasks" />
              <Stat big={standup.blockers_list.length} label="blockers" />
            </div>
          ) : <Skeleton />}
        </Card>

        <Card title="Recent activity" tile="tile-purple" icon={<ScrollText className="h-[18px] w-[18px]" />} onClick={() => router.push("/audit")}>
          {audit.length > 0 ? (
            <ul className="space-y-2">
              {audit.slice(0, 5).map((a, i) => (
                <li key={i} className="flex items-center gap-2 text-[13px]">
                  <span className={a.status === "success" ? "text-[#4ade80]" : a.status === "failed" ? "text-[#f87171]" : "text-[#71717a]"}>
                    {a.status === "success" ? "✓" : a.status === "failed" ? "✗" : "·"}
                  </span>
                  <span className="font-mono text-[12px] text-[#a1a1aa]">{a.action}</span>
                  <span className="truncate text-[#71717a]">{a.summary}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-[13px] text-[#71717a]">No activity yet.</p>}
        </Card>

        <Card title="Usage" tile="tile-orange" icon={<BarChart3 className="h-[18px] w-[18px]" />} onClick={() => router.push("/costs")}>
          {cost ? (
            <div className="flex gap-8">
              <Stat big={(cost.total_tokens ?? 0).toLocaleString()} label="tokens" />
              <Stat big={`$${((cost.total_cost_cents ?? 0) / 100).toFixed(2)}`} label="spent" />
            </div>
          ) : <Skeleton />}
        </Card>
      </div>
    </div>
  );
}

function Card({ title, icon, tile, onClick, children }: { title: string; icon: React.ReactNode; tile: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className="panel group p-4 text-left transition-colors hover:border-[#3a3a3c]">
      <div className="mb-3 flex items-center gap-2.5">
        <span className={`tile h-8 w-8 ${tile}`}>{icon}</span>
        <span className="text-[14px] font-semibold text-[#e4e4e7]">{title}</span>
        <ArrowRight className="ml-auto h-4 w-4 text-[#52525b] transition-colors group-hover:text-[#a1a1aa]" />
      </div>
      {children}
    </button>
  );
}

function Stat({ big, label }: { big: number | string; label: string }) {
  return (
    <div>
      <div className="text-2xl font-semibold tracking-tight text-[#e4e4e7]">{big}</div>
      <div className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-[#71717a]">{label}</div>
    </div>
  );
}

function Skeleton() {
  return <div className="h-7 w-28 animate-pulse rounded-md bg-[#2a2a2a]" />;
}
