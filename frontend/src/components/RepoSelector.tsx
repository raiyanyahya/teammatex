"use client";

import { useEffect, useState } from "react";
import { Github, GitFork, Archive, Lock, X, Plus, Loader2 } from "lucide-react";

export type GhRepo = {
  name: string; url: string; default_branch?: string;
  private?: boolean; language?: string | null; fork?: boolean; archived?: boolean;
};

type Existing = { github_url?: string; local_name?: string };

/** Normalize a GitHub url or full_name to a lowercase owner/repo slug. */
export function repoSlug(s: string): string {
  const t = s.trim().toLowerCase()
    .replace(/^git@github\.com:/, "")
    .replace(/^https?:\/\/github\.com\//, "")
    .replace(/\.git$/, "")
    .replace(/\/$/, "");
  const parts = t.split("/").filter(Boolean);
  return parts.length >= 2 ? `${parts[parts.length - 2]}/${parts[parts.length - 1]}` : t;
}

/**
 * Lists the connected account's GitHub repos with smart-default selection
 * (everything except already-added, forks, and archived) and bulk-onboards the
 * chosen set. Self-contained — used by both the Onboarding and Repos pages.
 */
export default function RepoSelector({ existing, onDone, onCancel }: {
  existing: Existing[]; onDone: () => void; onCancel: () => void;
}) {
  const [repos, setRepos] = useState<GhRepo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [onboarding, setOnboarding] = useState(false);

  const addedSlugs = new Set(existing.map((r) => repoSlug(r.github_url || r.local_name || "")));

  useEffect(() => {
    (async () => {
      setLoading(true); setError("");
      try {
        const res = await fetch("/api/integrations/github/repos");
        if (!res.ok) throw new Error(String(res.status));
        const data = await res.json();
        const list: GhRepo[] = data.repos || [];
        setRepos(list);
        setChecked(new Set(
          list.filter((r) => !addedSlugs.has(repoSlug(r.name)) && !r.fork && !r.archived).map((r) => r.url)
        ));
      } catch {
        setError("Couldn't load your GitHub repositories. Is a token saved in Settings?");
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggle(url: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  }

  const selectable = repos.filter((r) => !addedSlugs.has(repoSlug(r.name)));
  const allSelected = selectable.length > 0 && checked.size === selectable.length;
  function toggleAll() {
    if (allSelected) setChecked(new Set());
    else setChecked(new Set(selectable.map((r) => r.url)));
  }

  async function onboardSelected() {
    const github_urls = [...checked];
    if (github_urls.length === 0) return;
    setOnboarding(true); setError("");
    try {
      const res = await fetch("/api/repos/bulk", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_urls }),
      });
      if (!res.ok) throw new Error(String(res.status));
      onDone();
    } catch {
      setError("Failed to onboard the selected repositories.");
    }
    setOnboarding(false);
  }

  return (
    <div className="panel mx-auto max-w-3xl">
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
            <button onClick={toggleAll} className="text-xs text-[#7a9ec8] hover:text-[#9ab8e0]">
              {allSelected ? "Deselect all" : "Select all"}
            </button>
            <span className="text-[11px] text-[#6a6a6e]">{checked.size} of {selectable.length} selected</span>
          </div>
          <div className="max-h-[55vh] divide-y divide-[#2a2a2e] overflow-y-auto">
            {repos.map((r) => {
              const added = addedSlugs.has(repoSlug(r.name));
              return (
                <label key={r.url} className={`flex items-center gap-3 px-5 py-2.5 ${added ? "cursor-not-allowed opacity-50" : "cursor-pointer hover:bg-[#25252b]"}`}>
                  <input type="checkbox" checked={added ? false : checked.has(r.url)} disabled={added} onChange={() => toggle(r.url)} className="h-3.5 w-3.5 accent-[#264f78]" />
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
            <button onClick={onboardSelected} disabled={onboarding || checked.size === 0} className="btn-primary disabled:opacity-50">
              {onboarding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              Onboard {checked.size} selected
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Badge({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded bg-[#2a2a30] px-1.5 py-0.5 text-[10px] text-[#8a8a8e]">
      {icon}{label}
    </span>
  );
}
