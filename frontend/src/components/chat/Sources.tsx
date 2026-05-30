type Source = { path: string; tool: string; lines?: string };

export default function Sources({ sources }: { sources?: Source[] }) {
  if (!sources || sources.length === 0) return null;
  return (
    <div style={{ marginTop: 10, borderTop: "1px dashed var(--line-strong)", paddingTop: 8 }}>
      <div className="font-mono" style={{ fontSize: 10, letterSpacing: "0.1em", color: "var(--paper-4)", marginBottom: 6 }}>
        SOURCES
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {sources.map((s, i) => (
          <div key={i} className="font-mono" style={{ fontSize: 11, color: "var(--paper-2)" }}>
            <span style={{ color: "var(--sky)" }}>{s.path}</span>
            {s.lines ? <span style={{ color: "var(--paper-4)" }}>:{s.lines}</span> : null}
            <span style={{ color: "var(--paper-4)" }}> · {s.tool}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
