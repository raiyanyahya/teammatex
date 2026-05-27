"use client";

import { useCallback, useEffect, useState } from "react";
import {
  GitPullRequest, ListTodo, AlertTriangle, CheckCircle2,
  RefreshCw, Loader2,
} from "lucide-react";

type PR = { title: string; status: string; branch: string };
type Task = { title: string; status: string; priority: string };
type Blocker = { question: string; created_at: string | null };

type Standup = {
  name: string;
  date: string;
  prs: PR[];
  tasks: Task[];
  blockers_list: Blocker[];
};

function relativeAge(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.max(0, Math.round((Date.now() - then) / 60000));
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

const STATUS_TONE: Record<string, string> = {
  open: "bg-[#13301f] text-[#5fb87f]",
  merged: "bg-[#2a1f3a] text-[#a585d0]",
  closed: "bg-[#3a2020] text-[#c06060]",
  in_progress: "bg-[#3a3010] text-[#c0a040]",
};

function pill(label: string) {
  const tone = STATUS_TONE[label] ?? "bg-[#2a2a30] text-[#8a8a8e]";
  return (
    <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${tone}`}>
      {label}
    </span>
  );
}

export default function StandupPage() {
  const [data, setData] = useState<Standup | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await fetch("/api/features/standup");
      if (!res.ok) throw new Error(String(res.status));
      setData(await res.json());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="p-8">
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#cccccc]">Standup</h1>
          <p className="mt-0.5 text-xs text-[#6a6a6e]">
            {data?.name ? `${data.name} · ` : ""}{data?.date ?? "Daily summary of recent activity"}
          </p>
        </div>
        <button onClick={load} disabled={loading} className="btn-secondary disabled:opacity-50">
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          Refresh
        </button>
      </div>

      {error ? (
        <div className="panel p-6 text-center text-sm text-[#c06060]">
          Couldn&apos;t load the standup. <button onClick={load} className="underline">Try again</button>.
        </div>
      ) : loading && !data ? (
        <div className="flex items-center gap-2 py-12 text-sm text-[#6a6a6e]">
          <Loader2 className="h-4 w-4 animate-spin" /> Gathering activity…
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Section icon={<GitPullRequest className="h-3.5 w-3.5" />} title="Yesterday" count={data?.prs.length ?? 0}>
            {data && data.prs.length > 0 ? (
              data.prs.map((p, i) => (
                <Row key={i} title={p.title} sub={p.branch}>{pill(p.status)}</Row>
              ))
            ) : (
              <Empty>No PR activity.</Empty>
            )}
          </Section>

          <Section icon={<ListTodo className="h-3.5 w-3.5" />} title="Today" count={data?.tasks.length ?? 0}>
            {data && data.tasks.length > 0 ? (
              data.tasks.map((t, i) => (
                <Row key={i} title={t.title} sub={t.priority}>{pill(t.status)}</Row>
              ))
            ) : (
              <Empty>Monitoring for new tasks.</Empty>
            )}
          </Section>

          <Section icon={<AlertTriangle className="h-3.5 w-3.5" />} title="Blockers" count={data?.blockers_list.length ?? 0}>
            {data && data.blockers_list.length > 0 ? (
              data.blockers_list.map((b, i) => (
                <Row key={i} title={b.question} sub={relativeAge(b.created_at)} />
              ))
            ) : (
              <div className="flex items-center gap-2 px-4 py-6 text-xs text-[#5fb87f]">
                <CheckCircle2 className="h-3.5 w-3.5" /> All clear — nothing blocked.
              </div>
            )}
          </Section>
        </div>
      )}
    </div>
  );
}

function Section({ icon, title, count, children }: {
  icon: React.ReactNode; title: string; count: number; children: React.ReactNode;
}) {
  return (
    <div className="panel">
      <div className="flex items-center gap-2 border-b border-[#2a2a2e] px-4 py-2.5 text-[#8a8a8e]">
        {icon}
        <span className="text-xs font-semibold uppercase tracking-wide">{title}</span>
        <span className="ml-auto text-[10px] text-[#5a5a5e]">{count}</span>
      </div>
      <div className="divide-y divide-[#2a2a2e]">{children}</div>
    </div>
  );
}

function Row({ title, sub, children }: { title: string; sub?: string; children?: React.ReactNode }) {
  return (
    <div className="px-4 py-2.5">
      <p className="text-sm text-[#cccccc]">{title}</p>
      <div className="mt-1.5 flex items-center gap-2">
        {children}
        {sub ? <span className="text-[10px] text-[#5a5a5e]">{sub}</span> : null}
      </div>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="px-4 py-6 text-center text-xs text-[#5a5a5e]">{children}</p>;
}
