"use client";

import { useEffect, useMemo, useState } from "react";
import { GitBranch, Loader2, RefreshCw, Search, Sparkles } from "lucide-react";

type Stats = { files: number; modules: number; functions: number; classes: number; concepts: number };

type Expert = { name: string; email?: string | null; weight?: number };

type Concept = {
  id: string;
  name: string;
  cat: "module" | "subsystem" | "project" | "concept" | string;
  summary: string;
  files: number;
  refs: number;
  experts: Expert[];
  repo?: string | null;
  repo_id?: string | null;
};

const CATS: { id: "all" | Concept["cat"]; label: string }[] = [
  { id: "all", label: "All" },
  { id: "module", label: "Modules" },
  { id: "subsystem", label: "Subsystems" },
  { id: "project", label: "Projects" },
  { id: "concept", label: "Concepts" },
];

const CAT_COLOR: Record<string, string> = {
  module: "sky",
  subsystem: "plum",
  project: "amber",
  concept: "sage",
};

export default function KnowledgePage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [cat, setCat] = useState<(typeof CATS)[number]["id"]>("all");
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");

  async function load() {
    setLoading(true);
    try {
      const [s, c] = await Promise.all([
        fetch("/api/knowledge/graph/stats").then((r) => r.json()),
        fetch("/api/knowledge/concepts").then((r) => r.json()),
      ]);
      setStats(s);
      setConcepts(Array.isArray(c?.concepts) ? c.concepts : []);
    } catch {}
    setLoading(false);
  }

  async function generate() {
    setGenerating(true);
    setGenError("");
    try {
      const r = await fetch("/api/knowledge/concepts/generate", { method: "POST" });
      if (!r.ok) {
        const data = await r.json().catch(() => ({}));
        throw new Error(data?.detail || `Status ${r.status}`);
      }
      await load();
    } catch (e: any) {
      setGenError(e.message || "Generation failed");
    }
    setGenerating(false);
  }

  useEffect(() => {
    load();
  }, []);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: concepts.length };
    for (const x of concepts) c[x.cat] = (c[x.cat] || 0) + 1;
    return c;
  }, [concepts]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return concepts.filter((c) => {
      if (cat !== "all" && c.cat !== cat) return false;
      if (!q) return true;
      const hay = `${c.name} ${c.summary || ""} ${c.repo || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [concepts, query, cat]);

  return (
    <div style={{ padding: 40 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 24 }}>
        <div>
          <h1 className="page-title">
            Knowledge<em>.</em>
          </h1>
          <div className="page-sub">
            {stats
              ? `${stats.concepts.toLocaleString()} graph nodes · ${concepts.length} concepts indexed`
              : "loading…"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" onClick={load} disabled={loading || generating}>
            <RefreshCw size={13} /> Refresh
          </button>
          <button className="btn btn-primary" onClick={generate} disabled={generating}>
            {generating ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
            {generating ? "Generating…" : concepts.length === 0 ? "Generate concepts" : "Regenerate"}
          </button>
        </div>
      </div>

      {genError && (
        <div
          style={{
            marginBottom: 16,
            padding: "10px 14px",
            border: "1px solid rgba(194, 116, 95, 0.3)",
            background: "rgba(194, 116, 95, 0.06)",
            borderRadius: 6,
            fontSize: 12,
            color: "var(--rust)",
          }}
        >
          {genError}
        </div>
      )}

      <div style={{ display: "flex", gap: 10, marginBottom: 24 }}>
        <div style={{ flex: 1, position: "relative" }}>
          <Search
            size={14}
            style={{
              position: "absolute",
              top: "50%",
              left: 14,
              transform: "translateY(-50%)",
              color: "var(--paper-3)",
            }}
          />
          <input
            className="input"
            placeholder="Search concepts, summaries, repos…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ paddingLeft: 38, fontSize: 14, fontFamily: "var(--serif)" }}
          />
        </div>
        <div style={{ display: "flex", gap: 4, padding: 3, background: "var(--ink-2)", borderRadius: 6, border: "1px solid var(--line)" }}>
          {CATS.map((c) => {
            const active = cat === c.id;
            return (
              <button
                key={c.id}
                onClick={() => setCat(c.id)}
                className="btn btn-ghost"
                style={{
                  padding: "4px 10px",
                  fontSize: 11,
                  background: active ? "var(--ink-3)" : "transparent",
                }}
              >
                {c.label}{" "}
                <span className="font-mono" style={{ color: "var(--paper-4)", marginLeft: 4 }}>
                  {counts[c.id] ?? 0}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {loading ? (
        <div className="font-mono" style={{ fontSize: 12, color: "var(--paper-3)" }}>
          loading…
        </div>
      ) : concepts.length === 0 ? (
        <EmptyState onGenerate={generate} generating={generating} />
      ) : filtered.length === 0 ? (
        <div style={{ padding: 60, textAlign: "center" }}>
          <div className="font-mono" style={{ fontSize: 12, color: "var(--paper-4)" }}>
            No concepts matching that filter.
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 12 }}>
          {filtered.map((c) => (
            <ConceptCard key={c.id} concept={c} />
          ))}
        </div>
      )}
    </div>
  );
}

function EmptyState({ onGenerate, generating }: { onGenerate: () => void; generating: boolean }) {
  return (
    <div className="card" style={{ padding: 40, textAlign: "center", maxWidth: 560, margin: "60px auto" }}>
      <Sparkles size={28} style={{ color: "var(--amber)", margin: "0 auto 14px" }} />
      <div style={{ fontFamily: "var(--serif)", fontSize: 24, color: "var(--paper-0)", marginBottom: 8 }}>
        No concepts indexed yet
      </div>
      <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-3)", marginBottom: 20, lineHeight: 1.6 }}>
        The agent reads each onboarded repo and names the concepts that live inside —
        modules, subsystems, in-flight projects, and recurring patterns. One LLM pass per repo.
      </div>
      <button className="btn btn-primary" onClick={onGenerate} disabled={generating} style={{ margin: "0 auto" }}>
        {generating ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
        {generating ? "Generating…" : "Generate concepts"}
      </button>
    </div>
  );
}

function ConceptCard({ concept }: { concept: Concept }) {
  const accent = CAT_COLOR[concept.cat] || "amber";
  return (
    <div
      style={{
        background: "var(--ink-1)",
        border: "1px solid var(--line)",
        borderRadius: 8,
        padding: 18,
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
        <span
          style={{
            fontFamily: "var(--serif)",
            fontSize: 22,
            color: "var(--paper-0)",
            lineHeight: 1.15,
            overflow: "hidden",
            textOverflow: "ellipsis",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
          }}
        >
          {concept.name}
        </span>
        <span className={`tag tag-${accent}`}>{concept.cat}</span>
      </div>

      <div
        style={{
          fontSize: 13,
          lineHeight: 1.5,
          color: "var(--paper-2)",
          display: "-webkit-box",
          WebkitLineClamp: 4,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
          minHeight: 56,
        }}
      >
        {concept.summary}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 8,
          marginTop: "auto",
          paddingTop: 12,
          borderTop: "1px dashed var(--line-strong)",
        }}
      >
        <div>
          <div className="font-mono" style={{ fontSize: 9, color: "var(--paper-4)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            REFS
          </div>
          <div className="font-mono" style={{ fontSize: 12, color: "var(--paper-0)", marginTop: 4 }}>
            {concept.refs.toLocaleString()} · {concept.files} {concept.files === 1 ? "file" : "files"}
          </div>
        </div>
        <div>
          <div className="font-mono" style={{ fontSize: 9, color: "var(--paper-4)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            EXPERTS
          </div>
          <div className="font-mono" style={{ fontSize: 12, color: "var(--paper-0)", marginTop: 4 }}>
            {concept.experts.length === 0
              ? "—"
              : concept.experts.slice(0, 3).map((e) => `@${(e.name || "").split(" ")[0].toLowerCase()}`).join(", ")}
          </div>
        </div>
      </div>

      {concept.repo && (
        <div style={{ display: "flex", gap: 6 }}>
          <span className="tag" style={{ fontSize: 9 }}>
            <GitBranch size={9} /> {concept.repo}
          </span>
        </div>
      )}
    </div>
  );
}
