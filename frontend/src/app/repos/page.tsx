"use client";

import { useEffect, useState } from "react";
import { Plus, Loader2, GitBranch, Github, RefreshCw, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { useRouter } from "next/navigation";
import RepoSelector from "@/components/RepoSelector";

type Repo = { id: string; local_name: string; github_url: string };

export default function ReposPage() {
  const router = useRouter();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [onboardStatus, setOnboardStatus] = useState<Record<string, any>>({});
  const [browsing, setBrowsing] = useState(false);
  const [busy, setBusy] = useState<Record<string, "resync" | "remove">>({});
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);

  async function loadRepos() {
    try {
      const data = await api.get<Repo[]>("/repos");
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

  async function resync(id: string) {
    setBusy((b) => ({ ...b, [id]: "resync" }));
    try { await api.post(`/repos/${id}/retry`, {}); await loadRepos(); } catch {}
    setBusy((b) => { const n = { ...b }; delete n[id]; return n; });
  }

  async function remove(id: string) {
    setBusy((b) => ({ ...b, [id]: "remove" }));
    setConfirmRemove(null);
    try {
      await fetch(`/api/repos/${id}`, { method: "DELETE" });
      setRepos((prev) => prev.filter((r) => r.id !== id));
    } catch {}
    setBusy((b) => { const n = { ...b }; delete n[id]; return n; });
  }

  return (
    <div className="p-8">
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-[#e4e4e7]">Repositories</h1>
          <p className="mt-0.5 text-xs text-[#a1a1aa]">Browse your GitHub account or add repos by URL</p>
        </div>
        {!browsing && (
          <button onClick={() => setBrowsing(true)} className="btn-secondary">
            <Github className="h-3.5 w-3.5" /> Browse my repositories
          </button>
        )}
      </div>

      {browsing ? (
        <RepoSelector
          existing={repos}
          onDone={() => { setBrowsing(false); setLoading(true); loadRepos(); }}
          onCancel={() => setBrowsing(false)}
        />
      ) : (
        <>
          <div className="mb-6 flex gap-2">
            <input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addRepo()} placeholder="https://github.com/owner/repo" className="input flex-1" />
            <button onClick={addRepo} disabled={adding || !url.trim()} className="btn-primary">
              <Plus className="h-3.5 w-3.5" /> Add
            </button>
          </div>

          {error && <div className="mb-4 panel px-4 py-3 text-xs text-[#f87171]">{error}</div>}

          {loading ? (
            <div className="space-y-2">
              {[1, 2, 3].map((i) => <div key={i} className="h-16 animate-pulse rounded-md bg-[#202020]" />)}
            </div>
          ) : repos.length === 0 ? (
            <div className="panel p-12 text-center">
              <GitBranch className="mx-auto mb-3 h-8 w-8 text-[#71717a]" />
              <p className="text-sm text-[#a1a1aa]">No repositories added yet.</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {repos.map((repo) => {
                const status = onboardStatus[repo.id];
                const completed = status?.stages?.filter((s: any) => s.status === "completed").length || 0;
                const pct = status?.stages?.length > 0 ? Math.round((completed / 12) * 100) : 0;
                const action = busy[repo.id];

                return (
                  <div key={repo.id} className="panel flex items-center justify-between px-4 py-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <GitBranch className="h-4 w-4 shrink-0 text-[#71717a]" />
                      <div className="min-w-0">
                        <span className="font-mono text-sm text-[#e4e4e7]">{repo.local_name}</span>
                        <span className="ml-2 truncate text-[11px] text-[#71717a]">{repo.github_url}</span>
                      </div>
                    </div>

                    {confirmRemove === repo.id ? (
                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-[#fbbf24]">Remove {repo.local_name}?</span>
                        <button onClick={() => remove(repo.id)} className="rounded bg-[#2e1818] px-2 py-1 text-[#f87171] hover:bg-[#3a1818]">Remove</button>
                        <button onClick={() => setConfirmRemove(null)} className="btn-ghost">Cancel</button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                          <div className="h-1 w-24 overflow-hidden rounded-sm bg-[#262626]">
                            <div className="h-1 rounded-sm bg-[#3b82f6] transition-all" style={{ width: `${pct}%` }} />
                          </div>
                          <span className="font-mono text-[11px] text-[#a1a1aa]">{status ? `${completed}/12` : "queued"}</span>
                        </div>
                        <button onClick={() => router.push(`/onboarding?repo=${repo.id}`)} className="text-[11px] text-[#71717a] transition-colors hover:text-[#a1a1aa]">
                          View pipeline
                        </button>
                        <button onClick={() => resync(repo.id)} disabled={!!action} className="text-[#71717a] transition-colors hover:text-[#a1a1aa] disabled:opacity-50" title="Re-sync (re-run onboarding)">
                          {action === "resync" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                        </button>
                        <button onClick={() => setConfirmRemove(repo.id)} disabled={!!action} className="text-[#71717a] transition-colors hover:text-[#f87171] disabled:opacity-50" title="Remove">
                          {action === "remove" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
