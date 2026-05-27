"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { CheckCircle2, Loader2, AlertCircle, GitBranch, Plus, RefreshCw, Github, GitFork, Archive, Lock, X } from "lucide-react";

type GhRepo = { name: string; url: string; default_branch?: string; private?: boolean; language?: string | null; fork?: boolean; archived?: boolean };

/** Normalize a GitHub url or full_name to a lowercase owner/repo slug. */
function repoSlug(s: string): string {
  const t = s.trim().toLowerCase()
    .replace(/^git@github\.com:/, "")
    .replace(/^https?:\/\/github\.com\//, "")
    .replace(/\.git$/, "")
    .replace(/\/$/, "");
  const parts = t.split("/").filter(Boolean);
  return parts.length >= 2 ? `${parts[parts.length - 2]}/${parts[parts.length - 1]}` : t;
}

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

  // Repo selector ("Browse my repositories")
  const [browsing, setBrowsing] = useState(false);
  const [ghRepos, setGhRepos] = useState<GhRepo[]>([]);
  const [ghLoading, setGhLoading] = useState(false);
  const [ghError, setGhError] = useState("");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [onboarding, setOnboarding] = useState(false);

  // owner/repo slugs already in TeammateX — can't be re-added from the selector.
  const addedSlugs = new Set(repos.map((r) => repoSlug(r.github_url || r.local_name)));

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

  async function openSelector() {
    setBrowsing(true);
    setGhError("");
    setGhLoading(true);
    try {
      const data = await api.get<{ repos: GhRepo[] }>("/integrations/github/repos");
      const list = data.repos || [];
      setGhRepos(list);
      // Smart default: check everything that isn't already added, a fork, or archived.
      const added = new Set(repos.map((r) => repoSlug(r.github_url || r.local_name)));
      setChecked(new Set(
        list.filter((r) => !added.has(repoSlug(r.name)) && !r.fork && !r.archived).map((r) => r.url)
      ));
    } catch (e: any) {
      setGhError(e.message || "Couldn't load your GitHub repositories. Is a token saved in Settings?");
    }
    setGhLoading(false);
  }

  function toggle(url: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  }

  async function onboardSelected() {
    const github_urls = [...checked];
    if (github_urls.length === 0) return;
    setOnboarding(true);
    setGhError("");
    try {
      const res = await api.post<{ added: { repo_id: string }[] }>("/repos/bulk", { github_urls });
      setBrowsing(false);
      await loadRepos();
      if (res.added?.[0]) setSelectedId(res.added[0].repo_id);
    } catch (e: any) {
      setGhError(e.message || "Failed to onboard the selected repositories.");
    }
    setOnboarding(false);
  }

  // Repos that can actually be selected (already-added ones are shown but locked).
  const selectableCount = ghRepos.filter((r) => !addedSlugs.has(repoSlug(r.name))).length;
  const allSelected = selectableCount > 0 && checked.size === selectableCount;
  function toggleAll() {
    if (allSelected) setChecked(new Set());
    else setChecked(new Set(ghRepos.filter((r) => !addedSlugs.has(repoSlug(r.name))).map((r) => r.url)));
  }

  const completed = Object.values(stages).filter((s: any) => s?.status === "completed" || s === "completed").length;
  const failed = Object.values(stages).filter((s: any) => s?.status === "failed").length;
  const pct = Object.keys(stages).length > 0 ? Math.round((completed / 12) * 100) : 0;
  const activeRepo = repos.find((r) => r.id === selectedId);
  const errors = Object.entries(stages).filter(([_, s]: any) => s?.error).map(([i, s]: any) => ({ stage: parseInt(i), error: s.error }));

  return (
    <div className="p-8">
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#cccccc]">Onboarding Pipeline</h1>
          <p className="mt-0.5 text-xs text-[#6a6a6e]">Repository analysis progress</p>
        </div>
        {!browsing && repos.length > 0 && (
          <button onClick={openSelector} className="btn-secondary">
            <Github className="h-3.5 w-3.5" /> Browse my repositories
          </button>
        )}
      </div>

      {browsing ? (
        <RepoSelector
          loading={ghLoading}
          error={ghError}
          repos={ghRepos}
          checked={checked}
          addedSlugs={addedSlugs}
          allSelected={allSelected}
          selectableCount={selectableCount}
          onboarding={onboarding}
          onToggle={toggle}
          onToggleAll={toggleAll}
          onCancel={() => setBrowsing(false)}
          onOnboard={onboardSelected}
        />
      ) : repos.length === 0 ? (
        <div className="panel p-12 text-center max-w-lg mx-auto">
          <GitBranch className="h-8 w-8 text-[#5a5a5e] mx-auto mb-4" />
          <h2 className="text-sm font-semibold text-[#cccccc] mb-1">No repositories</h2>
          <p className="text-xs text-[#6a6a6e] mb-6">Pick from your GitHub account, or add a repository by URL.</p>
          <button onClick={openSelector} className="btn-primary mx-auto mb-5">
            <Github className="h-3.5 w-3.5" /> Browse my repositories
          </button>
          <div className="flex items-center gap-3 max-w-sm mx-auto mb-4 text-[10px] uppercase tracking-wider text-[#5a5a5e]">
            <span className="h-px flex-1 bg-[#2a2a2e]" /> or by url <span className="h-px flex-1 bg-[#2a2a2e]" />
          </div>
          <div className="flex gap-2 max-w-sm mx-auto">
            <input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addRepo()} placeholder="https://github.com/owner/repo" className="input flex-1" />
            <button onClick={addRepo} disabled={adding} className="btn-secondary">
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
                // stages[i] is the stage object {stage, status, error}; read .status
                // (older shapes stored the raw status string, so fall back to it).
                const st = stages[i];
                const status = st?.status ?? st;
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

function Badge({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] bg-[#2a2a30] text-[#8a8a8e]">
      {icon}{label}
    </span>
  );
}

function RepoSelector({
  loading, error, repos, checked, addedSlugs, allSelected, selectableCount, onboarding,
  onToggle, onToggleAll, onCancel, onOnboard,
}: {
  loading: boolean; error: string; repos: GhRepo[]; checked: Set<string>;
  addedSlugs: Set<string>; allSelected: boolean; selectableCount: number; onboarding: boolean;
  onToggle: (url: string) => void; onToggleAll: () => void; onCancel: () => void; onOnboard: () => void;
}) {
  return (
    <div className="panel max-w-3xl mx-auto">
      <div className="flex items-center justify-between border-b border-[#2a2a2e] px-5 py-3">
        <div className="flex items-center gap-2 text-[#cccccc]">
          <Github className="h-4 w-4" />
          <span className="text-sm font-semibold">Select repositories to onboard</span>
        </div>
        <button onClick={onCancel} className="btn-ghost"><X className="h-3.5 w-3.5" /></button>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 px-5 py-12 text-sm text-[#6a6a6e]">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading your repositories…
        </div>
      ) : error ? (
        <div className="px-5 py-10 text-center text-sm text-[#e06060]">{error}</div>
      ) : repos.length === 0 ? (
        <div className="px-5 py-10 text-center text-sm text-[#6a6a6e]">No repositories found for this token.</div>
      ) : (
        <>
          <div className="flex items-center justify-between border-b border-[#2a2a2e] px-5 py-2.5">
            <button onClick={onToggleAll} className="text-xs text-[#7a9ec8] hover:text-[#9ab8e0]">
              {allSelected ? "Deselect all" : "Select all"}
            </button>
            <span className="text-[11px] text-[#6a6a6e]">{checked.size} of {selectableCount} selected</span>
          </div>

          <div className="max-h-[55vh] divide-y divide-[#2a2a2e] overflow-y-auto">
            {repos.map((r) => {
              const added = addedSlugs.has(repoSlug(r.name));
              return (
                <label
                  key={r.url}
                  className={`flex items-center gap-3 px-5 py-2.5 ${added ? "cursor-not-allowed opacity-50" : "cursor-pointer hover:bg-[#25252b]"}`}
                >
                  <input
                    type="checkbox"
                    checked={added ? false : checked.has(r.url)}
                    disabled={added}
                    onChange={() => onToggle(r.url)}
                    className="h-3.5 w-3.5 accent-[#264f78]"
                  />
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-[#cccccc]">{r.name}</span>
                  <div className="flex shrink-0 items-center gap-1.5">
                    {r.language && <span className="text-[10px] text-[#6a6a6e]">{r.language}</span>}
                    {r.private && <Badge icon={<Lock className="h-2.5 w-2.5" />} label="private" />}
                    {r.fork && <Badge icon={<GitFork className="h-2.5 w-2.5" />} label="fork" />}
                    {r.archived && <Badge icon={<Archive className="h-2.5 w-2.5" />} label="archived" />}
                    {added && <span className="rounded bg-[#223040] px-1.5 py-0.5 text-[10px] text-[#7a9ec8]">added</span>}
                  </div>
                </label>
              );
            })}
          </div>

          <div className="flex items-center justify-between border-t border-[#2a2a2e] px-5 py-3">
            <button onClick={onCancel} className="btn-ghost text-xs">Cancel</button>
            <button onClick={onOnboard} disabled={onboarding || checked.size === 0} className="btn-primary disabled:opacity-50">
              {onboarding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              Onboard {checked.size} selected
            </button>
          </div>
        </>
      )}
    </div>
  );
}
