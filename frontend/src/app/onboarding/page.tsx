"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { CheckCircle2, Loader2, AlertCircle, GitBranch, Plus, RefreshCw } from "lucide-react";

const STAGES = [
  "Repository Discovery",
  "History Mining",
  "Code Analysis",
  "People Profiling",
  "Feature Extraction",
  "Graph Building",
  "Vector Embeddings",
  "Knowledge Synthesis",
  "Tech Debt Scan",
  "Style Learning",
  "Dependency Scan",
  "Introduction Report",
];

export default function OnboardingPage() {
  const [repos, setRepos] = useState<{ id: string; local_name: string; github_url?: string }[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [stages, setStages] = useState<Record<number, any>>({});
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);

  const loadRepos = useCallback(async () => {
    try {
      const data = await api.get<{ id: string; local_name: string; github_url: string }[]>("/repos");
      setRepos(data);
      if (data.length > 0 && !selectedId) setSelectedId(data[0].id);
    } catch {}
  }, [selectedId]);

  const loadStages = useCallback(async (repoId: string) => {
    try {
      const data = await api.get<{ stages: { stage: string; status: string; error?: string }[] }>(`/repos/${repoId}/onboarding`);
      const map: Record<number, any> = {};
      data.stages.forEach((s: any, i: number) => { map[i] = s; });
      setStages(map);
    } catch {}
  }, []);

  useEffect(() => { loadRepos(); }, [loadRepos]);
  useEffect(() => {
    if (selectedId) {
      loadStages(selectedId);
      const i = setInterval(() => loadStages(selectedId), 3000);
      return () => clearInterval(i);
    }
  }, [selectedId, loadStages]);

  async function addRepo() {
    if (!url.trim()) return;
    setAdding(true);
    try {
      const data = await api.post<{ repo_id: string }>("/repos", { github_url: url.trim() });
      setUrl("");
      await loadRepos();
      setSelectedId(data.repo_id);
    } catch (e: any) {
      setError(e.message || "Failed");
    }
    setAdding(false);
  }

  async function retryPipeline() {
    if (!selectedId) return;
    setRetrying(true);
    try {
      await api.post(`/repos/${selectedId}/retry`, {});
      setStages({});
      await loadStages(selectedId);
      const interval = setInterval(async () => {
        await loadStages(selectedId);
        const data = await api.get<{ stages: { status: string }[] }>(`/repos/${selectedId}/onboarding`);
        const allDone = data.stages.every((s: any) => s.status === "completed" || s.status === "failed");
        if (allDone) clearInterval(interval);
      }, 3000);
    } catch (e: any) {
      setError(e.message || "Retry failed");
    }
    setRetrying(false);
  }

  const completed = Object.values(stages).filter((s: any) => s?.status === "completed" || s === "completed").length;
  const failed = Object.values(stages).filter((s: any) => s?.status === "failed").length;
  const pct = Object.keys(stages).length > 0 ? Math.round((completed / 12) * 100) : 0;
  const activeRepo = repos.find((r) => r.id === selectedId);
  const errors = Object.entries(stages).filter(([_, s]: any) => s?.error).map(([i, s]: any) => ({ stage: parseInt(i), error: s.error }));

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-lg font-semibold text-[#cccccc]">Onboarding Pipeline</h1>
        <p className="mt-0.5 text-xs text-[#6a6a6e]">Repository analysis progress</p>
      </div>

      {repos.length === 0 ? (
        <div className="panel p-12 text-center max-w-lg mx-auto">
          <GitBranch className="h-8 w-8 text-[#5a5a5e] mx-auto mb-4" />
          <h2 className="text-sm font-semibold text-[#cccccc] mb-1">No repositories</h2>
          <p className="text-xs text-[#6a6a6e] mb-6">Add a GitHub repository to begin the onboarding pipeline.</p>
          <div className="flex gap-2 max-w-sm mx-auto">
            <input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addRepo()} placeholder="https://github.com/owner/repo" className="input flex-1" />
            <button onClick={addRepo} disabled={adding} className="btn-primary">
              <Plus className="h-3.5 w-3.5" /> Add
            </button>
          </div>
          {error && <p className="mt-3 text-xs text-[#e06060]">{error}</p>}
        </div>
      ) : (
        <div className="grid grid-cols-4 gap-6">
          <div className="space-y-1">
            <p className="text-[10px] font-semibold text-[#5a5a5e] uppercase tracking-wider mb-2 px-2">Repos</p>
            {repos.map((repo) => (
              <button
                key={repo.id}
                onClick={() => setSelectedId(repo.id)}
                className={`w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                  selectedId === repo.id
                    ? "bg-[#2a2a30] text-[#cccccc]"
                    : "text-[#6a6a6e] hover:text-[#cccccc] hover:bg-[#25252b]"
                }`}
              >
                <div className="flex items-center gap-2">
                  <GitBranch className="h-3 w-3 shrink-0" />
                  <span className="font-mono text-xs truncate">{repo.local_name}</span>
                </div>
              </button>
            ))}
            <div className="pt-3 px-1">
              <div className="flex gap-1.5">
                <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="URL..." className="input flex-1 text-xs py-1.5" />
                <button onClick={addRepo} disabled={adding} className="btn-primary text-xs px-2 py-1.5"><Plus className="h-3 w-3" /></button>
            </div>
            {errors.length > 0 && (
              <div className="mt-6 panel p-4">
                <h3 className="text-xs font-semibold text-[#e06060] mb-2">Errors ({errors.length})</h3>
                <div className="space-y-1.5">
                  {errors.map((e: any, i: number) => (
                    <div key={i} className="flex items-start gap-2 rounded p-2 bg-[#2a1515] border border-[#4a2020]">
                      <AlertCircle className="h-3.5 w-3.5 text-[#e06060] mt-0.5 shrink-0" />
                      <div>
                        <span className="text-xs text-[#e06060] font-medium">{STAGES.length > e.stage ? STAGES[e.stage] : `Stage ${e.stage + 1}`}</span>
                        <p className="text-[11px] text-[#c06060] mt-0.5 font-mono">{e.error}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
          </div>

          <div className="col-span-3 panel p-6">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-sm font-semibold text-[#cccccc]">{activeRepo?.local_name || "Select a repo"}</h2>
                <p className="text-xs text-[#6a6a6e]">{completed}/12 stages complete</p>
              </div>
              <span className={`badge ${pct === 100 ? "border-[#3a6a3a] bg-[#2a3a2a] text-[#6aaa6a]" : "border-[#2a4a6a] bg-[#223040] text-[#7a9ec8]"}`}>
                {pct === 100 ? "Complete" : `${pct}%`}
              </span>
              {failed > 0 || (completed === 0 && Object.keys(stages).length === 0) ? (
                <button onClick={retryPipeline} disabled={retrying} className="btn-primary text-xs flex items-center gap-1">
                  {retrying ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                  {failed > 0 ? "Retry pipeline" : "Start pipeline"}
                </button>
              ) : null}
            </div>

            <div className="mb-6 h-1.5 w-full rounded-sm bg-[#2a2a30] overflow-hidden">
              <div className="h-1.5 rounded-sm bg-[#264f78] transition-all duration-1000" style={{ width: `${pct}%` }} />
            </div>

            <div className="grid grid-cols-2 gap-x-6 gap-y-1">
              {STAGES.map((label, i) => {
                const status = stages[i];
                const isDone = status === "completed";
                const isRunning = status === "running";
                const isFailed = status === "failed";

                return (
                  <div key={i} className="flex items-center gap-2.5 py-1.5">
                    {isDone ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-[#6aaa6a] shrink-0" />
                    ) : isRunning ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-[#7a9ec8] shrink-0" />
                    ) : isFailed ? (
                      <AlertCircle className="h-3.5 w-3.5 text-[#e06060] shrink-0" />
                    ) : (
                      <span className="flex h-3.5 w-3.5 items-center justify-center rounded-sm bg-[#2a2a30] text-[9px] text-[#5a5a5e] font-mono shrink-0">{i + 1}</span>
                    )}
                    <span className={`text-xs ${isDone ? "text-[#8a8a8e]" : isRunning ? "text-[#cccccc]" : isFailed ? "text-[#e06060]" : "text-[#5a5a5e]"}`}>
                      {label}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
