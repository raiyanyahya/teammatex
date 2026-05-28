"use client";

import { useEffect, useMemo, useState } from "react";
import { MessageSquare, RefreshCw } from "lucide-react";

type Contributor = {
  name: string | null;
  email: string;
  files_owned: number;
  repos: string[];
  languages: string[];
};

type Member = {
  id: string;
  name: string;
  role: string;
  status: "online" | "offline";
  activity: string;
  isAgent: boolean;
  stats: Record<string, number>;
  expertise: string[];
  email?: string;
};

const AGENT_MEMBER: Member = {
  id: "yuji",
  name: "Yuji",
  role: "AI Teammate",
  status: "online",
  activity: "watching the knowledge graph",
  isAgent: true,
  stats: { repos: 0, files: 0, expertise: 0 },
  expertise: ["all surfaces"],
};

export default function TeamPage() {
  const [contributors, setContributors] = useState<Contributor[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string>("yuji");

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/knowledge/contributors");
      const data = await r.json();
      setContributors(data?.contributors ?? []);
    } catch {}
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const members: Member[] = useMemo(() => {
    const human: Member[] = contributors.map((c) => ({
      id: c.email,
      name: c.name || c.email,
      role: c.languages[0] ? `Engineer · ${c.languages[0]}` : "Engineer",
      status: "online",
      activity:
        c.files_owned === 0
          ? "no owned files yet"
          : `owns ${c.files_owned.toLocaleString()} ${c.files_owned === 1 ? "file" : "files"}`,
      isAgent: false,
      stats: {
        files: c.files_owned,
        repos: c.repos.length,
        languages: c.languages.length,
      },
      expertise: [...c.languages, ...c.repos],
      email: c.email,
    }));
    // Agent first, then contributors by file count.
    const agent = {
      ...AGENT_MEMBER,
      stats: {
        repos: new Set(contributors.flatMap((c) => c.repos)).size,
        contributors: contributors.length,
        files: contributors.reduce((s, c) => s + c.files_owned, 0),
      },
    };
    return [agent, ...human];
  }, [contributors]);

  const onlineCount = members.filter((m) => m.status === "online").length;
  const selected = members.find((m) => m.id === selectedId) || members[0];

  return (
    <div style={{ padding: 40 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", marginBottom: 28 }}>
        <div>
          <h1 className="page-title">
            Team<em>.</em>
          </h1>
          <div className="page-sub">
            {members.length} {members.length === 1 ? "member" : "members"} · 1 AI · {onlineCount} online
          </div>
        </div>
        <button className="btn" onClick={load} disabled={loading}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {members.length === 1 && contributors.length === 0 && (
        <div className="card" style={{ padding: 24, marginBottom: 20 }}>
          <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-3)", letterSpacing: "0.1em", marginBottom: 8 }}>
            STILL INDEXING
          </div>
          <div style={{ fontFamily: "var(--serif)", fontSize: 18, color: "var(--paper-1)" }}>
            Contributors appear once a repository is onboarded and its git history is indexed.
          </div>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: 20 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {members.map((m) => {
            const active = selectedId === m.id;
            return (
              <div
                key={m.id}
                onClick={() => setSelectedId(m.id)}
                style={{
                  padding: 14,
                  background: active ? "var(--ink-2)" : "var(--ink-1)",
                  border: "1px solid " + (active ? "var(--line-strong)" : "var(--line)"),
                  borderRadius: 6,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <MemberAvatar member={m} cardBg={active ? "var(--ink-2)" : "var(--ink-1)"} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontFamily: "var(--serif)", fontSize: 16, color: "var(--paper-0)" }}>{m.name}</span>
                    {m.isAgent && <span className="tag tag-amber" style={{ fontSize: 9 }}>AI</span>}
                  </div>
                  <div
                    className="font-mono"
                    style={{ fontSize: 10, marginTop: 2, color: "var(--paper-4)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  >
                    {m.activity}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {selected && (
          <div className="card">
            <div style={{ padding: "24px 28px", borderBottom: "1px solid var(--line)", display: "flex", alignItems: "flex-start", gap: 20 }}>
              <MemberAvatar member={selected} cardBg="var(--ink-1)" size={72} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <span style={{ fontFamily: "var(--serif)", fontSize: 32, color: "var(--paper-0)" }}>{selected.name}</span>
                  {selected.isAgent && <span className="tag tag-amber">AI TEAMMATE</span>}
                  <span className="tag tag-sage">
                    <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--sage)", display: "inline-block" }} />
                    {selected.status}
                  </span>
                </div>
                <div className="font-mono" style={{ fontSize: 12, color: "var(--paper-3)", marginTop: 6, letterSpacing: "0.04em" }}>
                  {selected.role}
                </div>
                {selected.email && !selected.isAgent && (
                  <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)", marginTop: 4 }}>
                    {selected.email}
                  </div>
                )}
                <div style={{ fontFamily: "var(--serif)", fontSize: 15, color: "var(--paper-1)", marginTop: 10, fontStyle: "italic" }}>
                  Currently · {selected.activity}
                </div>
              </div>
              {!selected.isAgent && (
                <button className="btn" disabled>
                  <MessageSquare size={12} /> Message
                </button>
              )}
            </div>

            <div
              style={{
                padding: 24,
                display: "grid",
                gridTemplateColumns: `repeat(${Object.keys(selected.stats).length}, 1fr)`,
                borderBottom: "1px solid var(--line)",
              }}
            >
              {Object.entries(selected.stats).map(([k, v], i, arr) => (
                <div
                  key={k}
                  style={{
                    borderRight: i < arr.length - 1 ? "1px solid var(--line)" : "none",
                    paddingLeft: i === 0 ? 0 : 20,
                  }}
                >
                  <div style={{ fontFamily: "var(--serif)", fontSize: 30, color: "var(--paper-0)", lineHeight: 1 }}>
                    {v.toLocaleString()}
                  </div>
                  <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-3)", letterSpacing: "0.1em", textTransform: "uppercase", marginTop: 6 }}>
                    {k}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ padding: 24 }}>
              <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-3)", letterSpacing: "0.1em", marginBottom: 10 }}>
                EXPERTISE · INFERRED FROM HISTORY
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {selected.expertise.length === 0 ? (
                  <span className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)" }}>—</span>
                ) : (
                  selected.expertise.map((e) => (
                    <span key={e} className="tag tag-plum">
                      {e}
                    </span>
                  ))
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function MemberAvatar({ member, cardBg, size = 32 }: { member: Member; cardBg: string; size?: number }) {
  if (member.isAgent) {
    return (
      <div
        style={{
          width: size,
          height: size,
          flexShrink: 0,
          borderRadius: "50%",
          background: "radial-gradient(circle at 30% 30%, var(--amber), var(--amber-dim) 60%, var(--ink-3))",
          boxShadow: "0 0 0 1px var(--line-strong), 0 0 12px rgba(212, 165, 116, 0.2)",
          position: "relative",
        }}
      >
        <span
          style={{
            position: "absolute",
            bottom: -1,
            right: -1,
            width: size > 40 ? 12 : 8,
            height: size > 40 ? 12 : 8,
            borderRadius: "50%",
            background: "var(--sage)",
            border: `2px solid ${cardBg}`,
          }}
        />
      </div>
    );
  }
  const initial = (member.name || "?").trim().charAt(0).toUpperCase();
  return (
    <div
      style={{
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: "50%",
        background: "var(--ink-3)",
        border: "1px solid var(--line-strong)",
        display: "grid",
        placeItems: "center",
        fontFamily: "var(--serif)",
        fontSize: size > 40 ? 32 : 14,
        color: "var(--paper-0)",
        position: "relative",
      }}
    >
      {initial}
      <span
        style={{
          position: "absolute",
          bottom: -1,
          right: -1,
          width: size > 40 ? 12 : 8,
          height: size > 40 ? 12 : 8,
          borderRadius: "50%",
          background: member.status === "online" ? "var(--sage)" : "var(--paper-5)",
          border: `2px solid ${cardBg}`,
        }}
      />
    </div>
  );
}
