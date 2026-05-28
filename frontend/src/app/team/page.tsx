"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, RefreshCw } from "lucide-react";

type Contributor = {
  name: string | null;
  email: string;
  files_owned: number;
  repos: string[];
  languages: string[];
};

function badge(label: string) {
  return (
    <span key={label} className="rounded bg-[#262626] px-1.5 py-0.5 text-[10px] font-medium text-[#a1a1aa]">
      {label}
    </span>
  );
}

export default function TeamPage() {
  const [members, setMembers] = useState<Contributor[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await fetch("/api/knowledge/contributors");
      if (!res.ok) throw new Error(String(res.status));
      const data = await res.json();
      setMembers(data.contributors ?? []);
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
          <h1 className="text-lg font-semibold text-[#e4e4e7]">Team</h1>
          <p className="mt-0.5 text-xs text-[#a1a1aa]">
            Contributors your teammate profiled from commit history
          </p>
        </div>
        <button onClick={load} disabled={loading} className="btn-secondary disabled:opacity-50">
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          Refresh
        </button>
      </div>

      {error ? (
        <div className="panel p-6 text-center text-sm text-[#fb7185]">
          Couldn&apos;t load contributors. <button onClick={load} className="underline">Try again</button>.
        </div>
      ) : loading && members.length === 0 ? (
        <div className="flex items-center gap-2 py-12 text-sm text-[#a1a1aa]">
          <Loader2 className="h-4 w-4 animate-spin" /> Reading the knowledge graph…
        </div>
      ) : members.length === 0 ? (
        <p className="py-12 text-center text-xs text-[#71717a]">
          No contributors yet — they appear once a repository is onboarded and its history is indexed.
        </p>
      ) : (
        <div className="max-w-2xl space-y-1">
          {members.map((m) => (
            <div key={m.email} className="panel flex items-center justify-between gap-4 px-4 py-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#262626] text-xs font-medium text-[#a1a1aa]">
                  {(m.name || m.email)[0]?.toUpperCase() || "?"}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm text-[#e4e4e7]">{m.name || m.email}</p>
                  <p className="truncate text-[11px] text-[#a1a1aa]">{m.email}</p>
                </div>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1.5">
                <span className="text-[11px] text-[#a1a1aa]">
                  {m.files_owned} {m.files_owned === 1 ? "file" : "files"}
                </span>
                <div className="flex flex-wrap justify-end gap-1">
                  {m.repos.map((r) => badge(r))}
                  {m.languages.map((l) => badge(l))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
