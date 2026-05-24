"use client";

import { useEffect, useState } from "react";
import { Plus, Loader2, GitBranch, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { useRouter } from "next/navigation";

export default function ReposPage() {
  const router = useRouter();
  const [repos, setRepos] = useState<any[]>([]);
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [onboardStatus, setOnboardStatus] = useState<Record<string, any>>({});

  async function loadRepos() {
    try {
      const data = await api.get<any[]>("/repos");
      setRepos(data);
      for (const r of data) {
        try {
          const status = await api.get<any>(`/repos/${r.id}/onboarding`);
          setOnboardStatus((prev) => ({ ...prev, [r.id]: status }));
        } catch {}
      }
    } catch {}
    setLoading(false);
  }

  useEffect(() => { loadRepos(); }, []);

  async function addRepo() {
    if (!url.trim()) return;
    setAdding(true); setError("");
    try {
      await api.post("/repos", { github_url: url.trim() });
      setUrl(""); await loadRepos();
    } catch (e: any) { setError(e.message || "Failed"); }
    setAdding(false);
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-lg font-semibold text-[#cccccc]">Repositories</h1>
        <p className="mt-0.5 text-xs text-[#6a6a6e]">Add repos to begin onboarding</p>
      </div>

      <div className="mb-6 flex gap-2">
        <input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addRepo()} placeholder="https://github.com/owner/repo" className="input flex-1" />
        <button onClick={addRepo} disabled={adding || !url.trim()} className="btn-primary">
          <Plus className="h-3.5 w-3.5" /> Add
        </button>
      </div>

      {error && <div className="mb-4 panel px-4 py-3 text-xs text-[#e06060]">{error}</div>}

      {loading ? (
        <div className="space-y-2">
          {[1,2,3].map((i) => <div key={i} className="h-16 rounded-md bg-[#25252b] animate-pulse" />)}
        </div>
      ) : repos.length === 0 ? (
        <div className="panel p-12 text-center">
          <GitBranch className="h-8 w-8 text-[#5a5a5e] mx-auto mb-3" />
          <p className="text-sm text-[#6a6a6e]">No repositories added yet.</p>
        </div>
      ) : (
        <div className="space-y-1.5">
          {repos.map((repo) => {
            const status = onboardStatus[repo.id];
            const completed = status?.stages?.filter((s: any) => s.status === "completed").length || 0;
            const pct = status?.stages?.length > 0 ? Math.round((completed / 12) * 100) : 0;

            return (
              <div key={repo.id} className="panel flex items-center justify-between px-4 py-3">
                <div className="flex items-center gap-3">
                  <GitBranch className="h-4 w-4 text-[#5a5a5e]" />
                  <div>
                    <span className="font-mono text-sm text-[#cccccc]">{repo.local_name}</span>
                    <span className="ml-2 text-[11px] text-[#5a5a5e]">{repo.github_url}</span>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  {status ? (
                    <div className="flex items-center gap-2">
                      <div className="h-1 w-24 rounded-sm bg-[#2a2a30] overflow-hidden">
                        <div className="h-1 rounded-sm bg-[#264f78] transition-all" style={{ width: `${pct}%` }} />
                      </div>
                      <span className="text-[11px] text-[#6a6a6e] font-mono">{completed}/12</span>
                    </div>
                  ) : (
                    <span className="text-[11px] text-[#5a5a5e]">Queued</span>
                  )}
                  <button onClick={() => router.push("/onboarding")} className="text-[11px] text-[#5a5a5e] hover:text-[#8a8a8e] transition-colors">
                    View pipeline
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
