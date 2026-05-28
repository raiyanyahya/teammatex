"use client";

import { useEffect, useMemo, useState } from "react";
import { BookOpen, GitBranch, RefreshCw, Search } from "lucide-react";

type Stats = { files: number; modules: number; functions: number; classes: number; concepts: number };

type Concept = {
  id: string;
  name: string;
  cat: "subsystem" | "note" | string;
  repos?: string[];
  repo_count?: number;
  files_seen?: number;
  summary?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
};

const CATS: { id: "all" | Concept["cat"]; label: string }[] = [
  { id: "all", label: "All" },
  { id: "subsystem", label: "Subsystems" },
  { id: "note", label: "Notes" },
];

const CAT_COLOR: Record<string, string> = {
  subsystem: "sky",
  note: "amber",
};

export default function KnowledgePage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [cat, setCat] = useState<(typeof CATS)[number]["id"]>("all");

  async function load() {
    setLoading(true);
    try {
      const [s, c] = await Promise.all([
        fetch("/api/knowledge/graph/stats").then((r) => r.json()),
        fetch("/api/knowledge/concepts?limit=400").then((r) => r.json()),
      ]);
      setStats(s);
      setConcepts(Array.isArray(c?.concepts) ? c.concepts : []);
    } catch {}
    setLoading(false);
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
      const hay = `${c.name} ${c.summary || ""} ${c.repos?.join(" ") || ""}`.toLowerCase();
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
        <button className="btn" onClick={load} disabled={loading}>
          <RefreshCw size={13} /> Resync
        </button>
      </div>

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
            placeholder="Search concepts, modules, notes…"
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
      ) : filtered.length === 0 ? (
        <div style={{ padding: 60, textAlign: "center" }}>
          <div className="font-mono" style={{ fontSize: 12, color: "var(--paper-4)" }}>
            {query ? `No matches for “${query}”.` : "No concepts indexed yet."}
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12 }}>
          {filtered.map((c) => (
            <ConceptCard key={c.id} concept={c} />
          ))}
        </div>
      )}
    </div>
  );
}

function ConceptCard({ concept }: { concept: Concept }) {
  const accent = CAT_COLOR[concept.cat] || "amber";
  const isNote = concept.cat === "note";
  return (
    <div
      style={{
        background: "var(--ink-1)",
        border: "1px solid var(--line)",
        borderRadius: 8,
        padding: 18,
        display: "flex",
        flexDirection: "column",
        gap: 10,
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

      {concept.summary && (
        <div
          style={{
            fontSize: 13,
            lineHeight: 1.5,
            color: "var(--paper-2)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            display: "-webkit-box",
            WebkitLineClamp: 3,
            WebkitBoxOrient: "vertical",
            minHeight: 40,
          }}
        >
          {concept.summary}
        </div>
      )}

      {isNote ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: "auto" }}>
          <span className="tag" style={{ fontSize: 9 }}>
            <BookOpen size={9} /> note
          </span>
          {concept.entity_type && (
            <span className="tag" style={{ fontSize: 9 }}>
              ↳ {concept.entity_type}
            </span>
          )}
        </div>
      ) : (
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
              REPOS
            </div>
            <div className="font-mono" style={{ fontSize: 12, color: "var(--paper-0)", marginTop: 4, display: "flex", flexWrap: "wrap", gap: 4 }}>
              {concept.repos && concept.repos.length > 0 ? (
                concept.repos.slice(0, 3).map((r) => (
                  <span key={r} className="tag" style={{ fontSize: 9 }}>
                    <GitBranch size={9} /> {r}
                  </span>
                ))
              ) : (
                <span style={{ color: "var(--paper-4)" }}>—</span>
              )}
              {concept.repos && concept.repos.length > 3 && (
                <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>
                  +{concept.repos.length - 3}
                </span>
              )}
            </div>
          </div>
          <div>
            <div className="font-mono" style={{ fontSize: 9, color: "var(--paper-4)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
              SURFACE AREA
            </div>
            <div className="font-mono" style={{ fontSize: 12, color: "var(--paper-0)", marginTop: 4 }}>
              {(concept.files_seen || 0).toLocaleString()} files
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
