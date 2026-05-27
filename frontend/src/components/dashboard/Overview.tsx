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
    <div className="p-8">
      <div className="mb-8 flex items-center gap-2">
        {editing ? (
          <>
            <input autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && saveName()} className="input w-48" />
            <button onClick={saveName} className="btn-primary text-xs"><Check className="h-3.5 w-3.5" /> Save</button>
          </>
        ) : (
          <>
            <h1 className="text-lg font-semibold text-[#cccccc]">{name || "Your teammate"}</h1>
            <button onClick={() => { setDraft(name); setEditing(true); }} className="text-[#5a5a5e] transition-colors hover:text-[#8a8a8e]" aria-label="Rename teammate">
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <span className="ml-1 text-xs text-[#6a6a6e]">is watching {repoCount} {repoCount === 1 ? "repository" : "repositories"}</span>
          </>
        )}
      </div>

      <div className="mb-6 flex max-w-2xl gap-2">
        <input value={ask} onChange={(e) => setAsk(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submitAsk()} placeholder={`Ask ${name || "your teammate"} about your code…`} className="input flex-1" />
        <button onClick={submitAsk} className="btn-primary"><Send className="h-3.5 w-3.5" /> Ask</button>
      </div>

      <div className="grid max-w-4xl grid-cols-1 gap-4 md:grid-cols-2">
        <Card title="Repositories" icon={<GitBranch className="h-3.5 w-3.5" />} onClick={() => router.push("/repos")}>
          <div className="flex items-end gap-5">
            <Stat big={repoCount} label="connected" />
          </div>
          <p className="mt-2 text-xs text-[#6a6a6e]">{onboarded} fully onboarded{inProgress > 0 ? ` · ${inProgress} in progress` : ""}</p>
        </Card>

        <Card title="Today's standup" icon={<ListChecks className="h-3.5 w-3.5" />} onClick={() => router.push("/standup")}>
          {standup ? (
            <div className="flex gap-6">
              <Stat big={standup.prs.length} label="PRs" />
              <Stat big={standup.tasks.length} label="tasks" />
              <Stat big={standup.blockers_list.length} label="blockers" />
            </div>
          ) : <Skeleton />}
        </Card>

        <Card title="Recent activity" icon={<ScrollText className="h-3.5 w-3.5" />} onClick={() => router.push("/audit")}>
          {audit.length > 0 ? (
            <ul className="space-y-1.5">
              {audit.slice(0, 5).map((a, i) => (
                <li key={i} className="flex items-center gap-2 text-xs">
                  <span className={a.status === "success" ? "text-[#6aaa6a]" : a.status === "failed" ? "text-[#e06060]" : "text-[#6a6a6e]"}>
                    {a.status === "success" ? "✓" : a.status === "failed" ? "✗" : "·"}
                  </span>
                  <span className="font-mono text-[#8a8a8e]">{a.action}</span>
                  <span className="truncate text-[#6a6a6e]">{a.summary}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-xs text-[#5a5a5e]">No activity yet.</p>}
        </Card>

        <Card title="Usage" icon={<BarChart3 className="h-3.5 w-3.5" />} onClick={() => router.push("/costs")}>
          {cost ? (
            <div className="flex gap-6">
              <Stat big={(cost.total_tokens ?? 0).toLocaleString()} label="tokens" />
              <Stat big={`$${((cost.total_cost_cents ?? 0) / 100).toFixed(2)}`} label="spent" />
            </div>
          ) : <Skeleton />}
        </Card>
      </div>
    </div>
  );
}

function Card({ title, icon, onClick, children }: { title: string; icon: React.ReactNode; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className="panel group p-4 text-left transition-colors hover:border-[#3a3a42]">
      <div className="mb-3 flex items-center gap-2 text-[#8a8a8e]">
        {icon}
        <span className="text-xs font-semibold uppercase tracking-wide">{title}</span>
        <ArrowRight className="ml-auto h-3.5 w-3.5 text-[#3a3a42] transition-colors group-hover:text-[#8a8a8e]" />
      </div>
      {children}
    </button>
  );
}

function Stat({ big, label }: { big: number | string; label: string }) {
  return (
    <div>
      <div className="text-xl font-semibold text-[#cccccc]">{big}</div>
      <div className="text-[10px] uppercase tracking-wide text-[#6a6a6e]">{label}</div>
    </div>
  );
}

function Skeleton() {
  return <div className="h-6 w-28 animate-pulse rounded bg-[#2a2a30]" />;
}
