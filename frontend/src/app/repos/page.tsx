"use client";

import { useEffect, useMemo, useState } from "react";
import { GitBranch, Github, Loader2, Plus, RefreshCw, Settings, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import RepoSelector from "@/components/RepoSelector";

type Repo = {
  id: string;
  local_name: string;
  github_url: string;
  default_branch?: string;
  files?: number;
  open_prs?: number;
  onboarding_pct?: number;
  health?: number;
};

const ACCENT_FOR_HEALTH = (h: number) => (h >= 85 ? "sage" : h >= 60 ? "amber" : "rust");

export default function ReposPage() {
  const router = useRouter();
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [browsing, setBrowsing] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<string, "resync" | "remove">>({});
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);

  async function load() {
    try {
      const data = await api.get<Repo[]>("/repos");
      setRepos(data);
      if (data.length && !selectedId) setSelectedId(data[0].id);
    } catch {}
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, []);

  async function addRepo() {
    if (!url.trim()) return;
    setAdding(true);
    setError("");
    try {
      await api.post("/repos", { github_url: url.trim() });
      setUrl("");
      await load();
    } catch (e: any) {
      setError(e.message || "Failed");
    }
    setAdding(false);
  }

  async function resync(id: string) {
    setBusy((b) => ({ ...b, [id]: "resync" }));
    try {
      await api.post(`/repos/${id}/retry`, {});
      await load();
    } catch {}
    setBusy((b) => {
      const n = { ...b };
      delete n[id];
      return n;
    });
  }

  async function remove(id: string) {
    setBusy((b) => ({ ...b, [id]: "remove" }));
    setConfirmRemove(null);
    try {
      await fetch(`/api/repos/${id}`, { method: "DELETE" });
      setRepos((prev) => prev.filter((r) => r.id !== id));
      if (selectedId === id) setSelectedId(null);
    } catch {}
    setBusy((b) => {
      const n = { ...b };
      delete n[id];
      return n;
    });
  }

  const totalFiles = useMemo(
    () => repos.reduce((s, r) => s + (r.files || 0), 0),
    [repos],
  );
  const selected = repos.find((r) => r.id === selectedId);

  return (
    <div style={{ padding: 40 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 28 }}>
        <div>
          <h1 className="page-title">
            Repos<em>.</em>
          </h1>
          <div className="page-sub">
            {repos.length} watched · {totalFiles.toLocaleString()} files indexed
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {!browsing && (
            <button className="btn" onClick={() => setBrowsing(true)}>
              <Github size={13} /> Browse my repositories
            </button>
          )}
          <button className="btn btn-primary" onClick={() => document.getElementById("repos-url-input")?.focus()}>
            <Plus size={13} /> Add by URL
          </button>
        </div>
      </div>

      {browsing ? (
        <RepoSelector
          existing={repos}
          onDone={() => {
            setBrowsing(false);
            setLoading(true);
            load();
          }}
          onCancel={() => setBrowsing(false)}
        />
      ) : (
        <>
          <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
            <input
              id="repos-url-input"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addRepo()}
              placeholder="https://github.com/owner/repo"
              className="input"
              style={{ flex: 1 }}
            />
            <button onClick={addRepo} disabled={adding || !url.trim()} className="btn btn-primary">
              {adding ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Add
            </button>
          </div>

          {error && (
            <div
              style={{
                marginBottom: 16,
                padding: "10px 14px",
                border: "1px solid rgba(194, 116, 95, 0.3)",
                background: "rgba(194, 116, 95, 0.05)",
                borderRadius: 6,
                fontSize: 12,
                color: "var(--rust)",
              }}
            >
              {error}
            </div>
          )}

          {loading ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[1, 2, 3].map((i) => (
                <div
                  key={i}
                  style={{ height: 120, background: "var(--ink-1)", border: "1px solid var(--line)", borderRadius: 8 }}
                />
              ))}
            </div>
          ) : repos.length === 0 ? (
            <div className="card" style={{ padding: 48, textAlign: "center" }}>
              <GitBranch size={32} style={{ color: "var(--paper-4)", margin: "0 auto 12px" }} />
              <div className="font-mono" style={{ fontSize: 12, color: "var(--paper-3)" }}>
                No repositories added yet.
              </div>
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16, marginBottom: 24 }}>
              {repos.map((r) => {
                const active = selectedId === r.id;
                const health = r.health ?? 0;
                const accent = ACCENT_FOR_HEALTH(health);
                const action = busy[r.id];
                return (
                  <div
                    key={r.id}
                    onClick={() => setSelectedId(r.id)}
                    style={{
                      background: "var(--ink-1)",
                      border: "1px solid " + (active ? "var(--amber-dim)" : "var(--line)"),
                      borderRadius: 8,
                      padding: 20,
                      cursor: "pointer",
                      position: "relative",
                      overflow: "hidden",
                    }}
                  >
                    <svg
                      width="100%"
                      height="40"
                      viewBox="0 0 200 40"
                      preserveAspectRatio="none"
                      style={{ position: "absolute", bottom: 0, left: 0, right: 0, opacity: 0.2 }}
                    >
                      <polyline
                        points={Array.from({ length: 30 }, (_, i) =>
                          `${i * 7},${20 + Math.sin(i * 0.5 + (r.files || 1)) * 12 - Math.cos(i * 0.3) * 6}`,
                        ).join(" ")}
                        fill="none"
                        stroke={`var(--${accent})`}
                        strokeWidth="1"
                      />
                    </svg>
                    <div style={{ position: "relative" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <GitBranch size={14} style={{ color: "var(--paper-2)" }} />
                            <span className="font-mono" style={{ fontSize: 15, color: "var(--paper-0)" }}>
                              {r.local_name}
                            </span>
                          </div>
                          <div
                            className="font-mono"
                            style={{ fontSize: 11, marginTop: 4, color: "var(--paper-4)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 280 }}
                          >
                            {r.github_url}
                          </div>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <div className="stat-val" style={{ fontSize: 28, color: `var(--${accent})` }}>
                            {health}
                          </div>
                          <div className="font-mono" style={{ fontSize: 9, color: "var(--paper-4)", letterSpacing: "0.1em" }}>
                            HEALTH
                          </div>
                        </div>
                      </div>

                      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginTop: 16 }}>
                        <Metric label="files" val={(r.files ?? 0).toLocaleString()} />
                        <Metric label="open PRs" val={String(r.open_prs ?? 0)} />
                        <Metric label="onboarded" val={`${r.onboarding_pct ?? 0}%`} />
                      </div>

                      <div style={{ display: "flex", gap: 6, marginTop: 14 }}>
                        <button
                          className="btn btn-ghost"
                          style={{ padding: "4px 8px", fontSize: 11 }}
                          onClick={(e) => {
                            e.stopPropagation();
                            router.push(`/onboarding?repo=${r.id}`);
                          }}
                        >
                          View pipeline
                        </button>
                        <button
                          className="btn btn-ghost"
                          style={{ padding: "4px 8px", fontSize: 11 }}
                          onClick={(e) => {
                            e.stopPropagation();
                            resync(r.id);
                          }}
                          disabled={!!action}
                        >
                          {action === "resync" ? (
                            <Loader2 size={11} className="animate-spin" />
                          ) : (
                            <RefreshCw size={11} />
                          )}
                          Resync
                        </button>
                        {confirmRemove === r.id ? (
                          <>
                            <button
                              className="btn"
                              style={{ padding: "4px 8px", fontSize: 11, color: "var(--rust)" }}
                              onClick={(e) => {
                                e.stopPropagation();
                                remove(r.id);
                              }}
                            >
                              Confirm
                            </button>
                            <button
                              className="btn btn-ghost"
                              style={{ padding: "4px 8px", fontSize: 11 }}
                              onClick={(e) => {
                                e.stopPropagation();
                                setConfirmRemove(null);
                              }}
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <button
                            className="btn btn-ghost"
                            style={{ padding: "4px 8px", fontSize: 11 }}
                            onClick={(e) => {
                              e.stopPropagation();
                              setConfirmRemove(r.id);
                            }}
                            disabled={!!action}
                          >
                            {action === "remove" ? (
                              <Loader2 size={11} className="animate-spin" />
                            ) : (
                              <Trash2 size={11} />
                            )}
                            Remove
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {selected && (
            <div className="card">
              <div className="card-head">
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div className="card-title">{selected.local_name}</div>
                  <span className="tag">{selected.default_branch || "main"}</span>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    className="btn btn-ghost"
                    style={{ padding: "4px 8px", fontSize: 11 }}
                    onClick={() => resync(selected.id)}
                  >
                    <RefreshCw size={11} /> Resync
                  </button>
                  <button className="btn btn-ghost" style={{ padding: "4px 8px", fontSize: 11 }} disabled>
                    <Settings size={11} /> Configure
                  </button>
                </div>
              </div>
              <div style={{ padding: 24, display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 20 }}>
                <Stat label="health" val={String(selected.health ?? 0)} color={`var(--${ACCENT_FOR_HEALTH(selected.health ?? 0)})`} />
                <Stat label="files" val={(selected.files ?? 0).toLocaleString()} />
                <Stat label="open PRs" val={String(selected.open_prs ?? 0)} />
                <Stat label="onboarded" val={`${selected.onboarding_pct ?? 0}%`} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Metric({ label, val }: { label: string; val: string }) {
  return (
    <div>
      <div className="font-mono" style={{ fontSize: 9, color: "var(--paper-4)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
        {label}
      </div>
      <div className="font-mono" style={{ fontSize: 13, color: "var(--paper-0)", marginTop: 2 }}>
        {val}
      </div>
    </div>
  );
}

function Stat({ label, val, color }: { label: string; val: string; color?: string }) {
  return (
    <div>
      <div className="stat-val" style={{ fontSize: 36, color: color || "var(--paper-0)" }}>{val}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
