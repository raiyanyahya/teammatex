"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Check, GitBranch, Github, Loader2, Pause, Plus, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import RepoSelector from "@/components/RepoSelector";

type Repo = { id: string; local_name: string; github_url?: string };
type StageRow = { stage: string; status: string; error?: string };

const STAGES: { label: string; desc: string }[] = [
  { label: "Repository Discovery", desc: "Cloning, language detect, build-system inference" },
  { label: "History Mining", desc: "Walking commits across branches" },
  { label: "Code Analysis", desc: "AST parsing, symbol graph, callsite extraction" },
  { label: "People Profiling", desc: "Authorship patterns, expertise mapping" },
  { label: "Feature Extraction", desc: "Inferring product surfaces from code + commits" },
  { label: "Graph Building", desc: "Linking code ↔ people ↔ concepts ↔ history" },
  { label: "Vector Embeddings", desc: "Semantic indexing for retrieval" },
  { label: "Knowledge Synthesis", desc: "Generating module summaries & cross-refs" },
  { label: "Tech Debt Scan", desc: "Hotspots, churn, brittle areas" },
  { label: "Style Learning", desc: "Code conventions, PR voice, naming patterns" },
  { label: "Dependency Scan", desc: "Vuln check, license audit, version drift" },
  { label: "Introduction Report", desc: "First written summary for the team" },
];

function statusFor(row: any): "completed" | "running" | "failed" | "pending" {
  const status = row?.status ?? row;
  if (status === "completed") return "completed";
  if (status === "running") return "running";
  if (status === "failed") return "failed";
  return "pending";
}

export default function OnboardingPage() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [stages, setStages] = useState<Record<number, StageRow>>({});
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [browsing, setBrowsing] = useState(false);

  const loadRepos = useCallback(async () => {
    try {
      const data = await api.get<Repo[]>("/repos");
      setRepos(data);
      if (data.length > 0 && !selectedId) {
        const wanted = new URLSearchParams(window.location.search).get("repo");
        const match = wanted && data.find((r) => r.id === wanted);
        setSelectedId(match ? wanted! : data[0].id);
      }
    } catch {}
  }, [selectedId]);

  const loadStages = useCallback(async (id: string) => {
    try {
      const data = await api.get<{ stages: StageRow[] }>(`/repos/${id}/onboarding`);
      const map: Record<number, StageRow> = {};
      data.stages.forEach((s, i) => {
        map[i] = s;
      });
      setStages(map);
    } catch {}
  }, []);

  useEffect(() => {
    loadRepos();
  }, [loadRepos]);

  useEffect(() => {
    if (!selectedId) return;
    loadStages(selectedId);
    const id = setInterval(() => loadStages(selectedId), 3000);
    return () => clearInterval(id);
  }, [selectedId, loadStages]);

  async function addRepo() {
    if (!url.trim()) return;
    setAdding(true);
    setError("");
    try {
      const d = await api.post<{ repo_id: string }>("/repos", { github_url: url.trim() });
      setUrl("");
      await loadRepos();
      setSelectedId(d.repo_id);
    } catch (e: any) {
      setError(e.message || "Failed");
    }
    setAdding(false);
  }

  async function retry() {
    if (!selectedId) return;
    setRetrying(true);
    try {
      await api.post(`/repos/${selectedId}/retry`, {});
      setStages({});
      await loadStages(selectedId);
    } catch (e: any) {
      setError(e.message || "Retry failed");
    }
    setRetrying(false);
  }

  const completedCount = Object.values(stages).filter((s) => statusFor(s) === "completed").length;
  const failedCount = Object.values(stages).filter((s) => statusFor(s) === "failed").length;
  const pct = STAGES.length ? Math.round((completedCount / STAGES.length) * 100) : 0;
  const activeRepo = repos.find((r) => r.id === selectedId);
  const repoStatus = failedCount > 0 ? "failed" : pct === 100 ? "complete" : pct > 0 ? "running" : "queued";

  return (
    <div style={{ padding: 40 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 28 }}>
        <div>
          <h1 className="page-title">
            Onboarding<em>.</em>
          </h1>
          <div className="page-sub">Pipeline · ingesting your team&rsquo;s history into the agent&rsquo;s brain</div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {!browsing && (
            <button className="btn" onClick={() => setBrowsing(true)}>
              <Github size={13} /> Browse my repos
            </button>
          )}
          <button className="btn btn-primary" onClick={() => document.getElementById("onb-url-input")?.focus()}>
            <Plus size={13} /> Add repository
          </button>
        </div>
      </div>

      {browsing ? (
        <RepoSelector
          existing={repos}
          onDone={() => {
            setBrowsing(false);
            loadRepos();
          }}
          onCancel={() => setBrowsing(false)}
        />
      ) : repos.length === 0 ? (
        <div className="card" style={{ padding: 48, textAlign: "center", maxWidth: 520, margin: "0 auto" }}>
          <GitBranch size={32} style={{ color: "var(--paper-4)", margin: "0 auto 12px" }} />
          <div style={{ fontFamily: "var(--serif)", fontSize: 22, color: "var(--paper-0)", marginBottom: 8 }}>
            No repositories yet
          </div>
          <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-3)", marginBottom: 16 }}>
            Pick from your GitHub account, or add a repository by URL.
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
            <input
              id="onb-url-input"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addRepo()}
              placeholder="https://github.com/owner/repo"
              className="input"
              style={{ maxWidth: 280, fontFamily: "var(--mono)" }}
            />
            <button onClick={addRepo} disabled={adding} className="btn btn-primary">
              {adding ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />} Add
            </button>
          </div>
          {error && (
            <div className="font-mono" style={{ marginTop: 10, fontSize: 11, color: "var(--rust)" }}>
              {error}
            </div>
          )}
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 24 }}>
          <div>
            <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-3)", letterSpacing: "0.12em", marginBottom: 8 }}>
              REPOSITORIES · {repos.length}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {repos.map((r) => {
                const active = selectedId === r.id;
                return (
                  <div
                    key={r.id}
                    onClick={() => setSelectedId(r.id)}
                    style={{
                      padding: "12px 14px",
                      background: active ? "var(--ink-2)" : "var(--ink-1)",
                      border: "1px solid " + (active ? "var(--line-strong)" : "var(--line)"),
                      borderRadius: 6,
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <GitBranch size={12} style={{ color: "var(--paper-3)" }} />
                      <span className="font-mono" style={{ fontSize: 13, color: "var(--paper-0)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {r.local_name}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
            <div style={{ marginTop: 16 }}>
              <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-3)", letterSpacing: "0.12em", marginBottom: 8 }}>
                QUICK ADD
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <input
                  className="input"
                  placeholder="https://github.com/org/repo"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addRepo()}
                  style={{ flex: 1, fontFamily: "var(--mono)", fontSize: 12 }}
                />
                <button className="btn btn-primary" style={{ padding: "6px 10px" }} onClick={addRepo} disabled={adding}>
                  {adding ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                </button>
              </div>
              {error && (
                <div className="font-mono" style={{ marginTop: 8, fontSize: 11, color: "var(--rust)" }}>
                  {error}
                </div>
              )}
            </div>
          </div>

          <div className="card">
            <div style={{ padding: "20px 24px", borderBottom: "1px solid var(--line)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <GitBranch size={16} style={{ color: "var(--paper-2)" }} />
                    <span style={{ fontFamily: "var(--serif)", fontSize: 24, color: "var(--paper-0)" }}>
                      {activeRepo?.local_name || "Select a repo"}
                    </span>
                    <span
                      className={`tag ${
                        repoStatus === "complete" ? "tag-sage" : repoStatus === "failed" ? "tag-rust" : repoStatus === "running" ? "tag-amber" : ""
                      }`}
                    >
                      {repoStatus}
                    </span>
                  </div>
                  <div
                    className="font-mono"
                    style={{ fontSize: 11, marginTop: 6, color: "var(--paper-4)", letterSpacing: "0.04em" }}
                  >
                    {completedCount}/{STAGES.length} stages complete
                    {failedCount > 0 ? ` · ${failedCount} failed` : ""}
                  </div>
                </div>
                <div style={{ textAlign: "right", display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
                  <div className="stat-val" style={{ fontSize: 32 }}>
                    {pct}
                    <span className="unit">%</span>
                  </div>
                  {(failedCount > 0 || (completedCount === 0 && Object.keys(stages).length === 0)) && (
                    <button className="btn btn-primary" style={{ padding: "5px 12px", fontSize: 12 }} onClick={retry} disabled={retrying}>
                      {retrying ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
                      {failedCount > 0 ? "Retry" : "Start"}
                    </button>
                  )}
                </div>
              </div>

              <div
                style={{
                  marginTop: 18,
                  height: 6,
                  background: "var(--ink-3)",
                  borderRadius: 3,
                  overflow: "hidden",
                  position: "relative",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${pct}%`,
                    background: "linear-gradient(90deg, var(--amber), var(--paper-1))",
                    borderRadius: 3,
                  }}
                />
              </div>
            </div>

            <div>
              {STAGES.map((s, i) => {
                const status = statusFor(stages[i]);
                const isDone = status === "completed";
                const isRunning = status === "running";
                const isFailed = status === "failed";
                return (
                  <div
                    key={i}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "28px 24px 1fr auto",
                      gap: 14,
                      alignItems: "center",
                      padding: "14px 24px",
                      borderBottom: "1px solid var(--line)",
                      background: isRunning ? "rgba(212, 165, 116, 0.04)" : "transparent",
                    }}
                  >
                    <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    {isDone ? (
                      <Check size={14} style={{ color: "var(--sage)" }} />
                    ) : isRunning ? (
                      <span
                        style={{
                          width: 12,
                          height: 12,
                          border: "1.5px solid var(--amber)",
                          borderTopColor: "transparent",
                          borderRadius: "50%",
                          display: "inline-block",
                          animation: "spin 0.8s linear infinite",
                        }}
                      />
                    ) : isFailed ? (
                      <AlertCircle size={14} style={{ color: "var(--rust)" }} />
                    ) : (
                      <span
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: "50%",
                          background: "var(--ink-4)",
                          display: "inline-block",
                          marginLeft: 3,
                        }}
                      />
                    )}
                    <div>
                      <div
                        style={{
                          fontSize: 13,
                          color: isDone || isRunning ? "var(--paper-0)" : isFailed ? "var(--rust)" : "var(--paper-4)",
                        }}
                      >
                        {s.label}
                      </div>
                      <div className="font-mono" style={{ fontSize: 10, marginTop: 2, color: "var(--paper-4)" }}>
                        {stages[i]?.error || s.desc}
                      </div>
                    </div>
                    <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>
                      {isDone ? "done" : isRunning ? "…" : isFailed ? "error" : ""}
                    </span>
                  </div>
                );
              })}
            </div>

            {repoStatus === "running" && (
              <div
                style={{
                  padding: "16px 24px",
                  borderTop: "1px solid var(--line)",
                  background: "var(--ink-0)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)" }}>
                  <span style={{ color: "var(--amber)" }}>●</span> indexing · stage {completedCount + 1} of {STAGES.length}
                </div>
                <button className="btn btn-ghost" disabled>
                  <Pause size={12} /> Pause
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
