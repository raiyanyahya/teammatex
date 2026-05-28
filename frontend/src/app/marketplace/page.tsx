"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw, Search } from "lucide-react";

type Stats = { files: number; modules: number; functions: number; classes: number; concepts: number };
type Node = { type: string; properties: Record<string, any> };

const CATS = ["all", "File", "Module", "Function", "Class"] as const;
const CAT_COLOR: Record<string, string> = {
  File: "sky",
  Module: "plum",
  Function: "amber",
  Class: "sage",
};

export default function KnowledgePage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Node[]>([]);
  const [cat, setCat] = useState<(typeof CATS)[number]>("all");
  const [searching, setSearching] = useState(false);

  async function loadStats() {
    try {
      const r = await fetch("/api/knowledge/graph/stats");
      if (r.ok) setStats(await r.json());
    } catch {}
  }

  useEffect(() => {
    loadStats();
  }, []);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    const id = setTimeout(async () => {
      setSearching(true);
      try {
        const r = await fetch(`/api/knowledge/graph/search?query=${encodeURIComponent(query.trim())}&limit=40`);
        if (r.ok) {
          const data = await r.json();
          setResults(data?.results ?? []);
        }
      } catch {}
      setSearching(false);
    }, 250);
    return () => clearTimeout(id);
  }, [query]);

  const filtered = useMemo(
    () => (cat === "all" ? results : results.filter((n) => n.type === cat)),
    [results, cat],
  );

  return (
    <div style={{ padding: 40 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 24 }}>
        <div>
          <h1 className="page-title">
            Knowledge<em>.</em>
          </h1>
          <div className="page-sub">
            {stats
              ? `${stats.concepts.toLocaleString()} concepts · ${stats.files.toLocaleString()} files · ${stats.functions.toLocaleString()} functions`
              : "loading…"}
          </div>
        </div>
        <button className="btn" onClick={loadStats}>
          <RefreshCw size={13} /> Resync graph
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
            placeholder="Search concepts, modules, files, functions…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            style={{ paddingLeft: 38, fontSize: 14, fontFamily: "var(--serif)" }}
          />
        </div>
        <div style={{ display: "flex", gap: 4, padding: 3, background: "var(--ink-2)", borderRadius: 6, border: "1px solid var(--line)" }}>
          {CATS.map((c) => (
            <button
              key={c}
              onClick={() => setCat(c)}
              className="btn btn-ghost"
              style={{
                padding: "4px 10px",
                fontSize: 11,
                textTransform: "capitalize",
                background: cat === c ? "var(--ink-3)" : "transparent",
              }}
            >
              {c === "all" ? "all" : c}
            </button>
          ))}
        </div>
      </div>

      {!query.trim() ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
          {(["files", "modules", "functions", "classes"] as const).map((k) => {
            const accent = CAT_COLOR[k[0].toUpperCase() + k.slice(1, -1)] || "amber";
            return (
              <div key={k} className="card" style={{ padding: 24 }}>
                <div className="stat-val" style={{ color: `var(--${accent})` }}>
                  {(stats?.[k] ?? 0).toLocaleString()}
                </div>
                <div className="stat-label">{k}</div>
              </div>
            );
          })}
        </div>
      ) : searching && results.length === 0 ? (
        <div className="font-mono" style={{ fontSize: 12, color: "var(--paper-3)" }}>
          searching…
        </div>
      ) : filtered.length === 0 ? (
        <div style={{ padding: 60, textAlign: "center" }}>
          <div className="font-mono" style={{ fontSize: 12, color: "var(--paper-4)" }}>
            No matches for “{query}”.
          </div>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12 }}>
          {filtered.map((n, i) => {
            const accent = CAT_COLOR[n.type] || "amber";
            const name = n.properties?.name || n.properties?.path || n.properties?.title || "(unnamed)";
            const sub =
              n.properties?.path && n.properties?.name
                ? n.properties.path
                : n.properties?.file_path || n.properties?.repo_id || "";
            return (
              <div
                key={i}
                style={{
                  background: "var(--ink-1)",
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                  padding: 18,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
                  <span
                    style={{
                      fontFamily: "var(--serif)",
                      fontSize: 22,
                      color: "var(--paper-0)",
                      lineHeight: 1.1,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      maxWidth: 240,
                    }}
                  >
                    {name}
                  </span>
                  <span className={`tag tag-${accent}`}>{n.type.toLowerCase()}</span>
                </div>
                <div
                  className="font-mono"
                  style={{
                    fontSize: 11,
                    lineHeight: 1.5,
                    color: "var(--paper-3)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {sub}
                </div>
                {(n.properties?.language || n.properties?.lines) && (
                  <div
                    style={{
                      display: "flex",
                      gap: 8,
                      marginTop: 12,
                      paddingTop: 10,
                      borderTop: "1px dashed var(--line-strong)",
                    }}
                  >
                    {n.properties?.language && (
                      <span className="tag" style={{ fontSize: 9 }}>
                        {n.properties.language}
                      </span>
                    )}
                    {n.properties?.lines != null && (
                      <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>
                        {n.properties.lines} lines
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
