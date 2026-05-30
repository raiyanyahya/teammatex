"use client";

import { useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";
import { useRouter } from "next/navigation";

type AuditItem = {
  action: string;
  entity_type?: string;
  summary?: string | null;
  status?: string | null;
  completed_at?: string | null;
};

const LAST_SEEN_KEY = "notif_last_seen";

function parseTs(iso?: string | null): number {
  if (!iso) return 0;
  const t = Date.parse(iso.replace(" ", "T"));
  return Number.isNaN(t) ? 0 : t;
}

function relativeTime(iso?: string | null): string {
  const t = parseTs(iso);
  if (!t) return "";
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function labelForAction(action: string): string {
  const map: Record<string, string> = {
    chat_query: "Answered a chat",
    pr_review: "Reviewed a PR",
    check_pr: "Reviewed a PR",
    onboarding: "Onboarded a repo",
    repo_onboarded: "Onboarded a repo",
    auto_sync: "Synced repositories",
  };
  if (map[action]) return map[action];
  return action.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function statusColor(status?: string | null): string {
  if (status === "success") return "var(--sage)";
  if (status === "failed" || status === "error") return "var(--rust)";
  return "var(--amber)";
}

export default function NotificationsBell() {
  const router = useRouter();
  const [items, setItems] = useState<AuditItem[]>([]);
  const [open, setOpen] = useState(false);
  const [lastSeen, setLastSeen] = useState(0);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setLastSeen(parseTs(typeof window !== "undefined" ? localStorage.getItem(LAST_SEEN_KEY) : null));
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await fetch("/api/knowledge/audit?limit=10").then((r) => r.json());
        if (!cancelled) setItems(Array.isArray(data) ? data : []);
      } catch {}
    };
    load();
    const id = setInterval(load, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // Close on outside click while open.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const unread = items.filter((i) => parseTs(i.completed_at) > lastSeen).length;

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) {
      const now = Date.now();
      try {
        localStorage.setItem(LAST_SEEN_KEY, new Date(now).toISOString());
      } catch {}
      setLastSeen(now);
    }
  };

  return (
    <div ref={wrapRef} style={{ position: "relative" }}>
      <button
        title="Notifications"
        onClick={toggle}
        className="grid h-[30px] w-[30px] place-items-center rounded-[var(--radius)] transition-colors"
        style={{
          border: "1px solid " + (open ? "var(--line-strong)" : "var(--line)"),
          background: "var(--ink-1)",
          color: open ? "var(--paper-0)" : "var(--paper-3)",
          cursor: "pointer",
        }}
      >
        <Bell size={14} />
        {unread > 0 && (
          <span
            className="font-mono"
            style={{
              position: "absolute",
              top: -5,
              right: -5,
              minWidth: 15,
              height: 15,
              padding: "0 3px",
              borderRadius: 8,
              background: "var(--rust)",
              color: "var(--ink-0)",
              fontSize: 9,
              lineHeight: "15px",
              textAlign: "center",
              fontWeight: 700,
            }}
          >
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            top: 38,
            right: 0,
            width: 320,
            zIndex: 50,
            background: "var(--ink-1)",
            border: "1px solid var(--line-strong)",
            borderRadius: "var(--radius)",
            boxShadow: "0 8px 28px rgba(0,0,0,0.4)",
            overflow: "hidden",
          }}
        >
          <div
            className="font-mono"
            style={{
              padding: "10px 14px",
              fontSize: 10,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--paper-4)",
              borderBottom: "1px solid var(--line)",
            }}
          >
            Notifications
          </div>

          <div style={{ maxHeight: 360, overflowY: "auto" }}>
            {items.length === 0 ? (
              <div className="font-mono" style={{ padding: "20px 14px", fontSize: 11, color: "var(--paper-4)" }}>
                No recent activity.
              </div>
            ) : (
              items.slice(0, 8).map((it, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    gap: 10,
                    padding: "10px 14px",
                    borderBottom: "1px solid var(--line)",
                    alignItems: "flex-start",
                  }}
                >
                  <span
                    style={{
                      marginTop: 4,
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      background: statusColor(it.status),
                      flexShrink: 0,
                    }}
                  />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                      <span style={{ fontSize: 12, color: "var(--paper-0)" }}>{labelForAction(it.action)}</span>
                      <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)", whiteSpace: "nowrap" }}>
                        {relativeTime(it.completed_at)}
                      </span>
                    </div>
                    {it.summary && (
                      <div
                        className="font-mono"
                        style={{
                          fontSize: 10,
                          color: "var(--paper-3)",
                          marginTop: 2,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {it.summary}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          <button
            onClick={() => {
              setOpen(false);
              router.push("/audit");
            }}
            className="font-mono"
            style={{
              width: "100%",
              padding: "10px 14px",
              fontSize: 11,
              color: "var(--amber)",
              background: "var(--ink-2)",
              border: "none",
              borderTop: "1px solid var(--line)",
              cursor: "pointer",
              textAlign: "left",
            }}
          >
            View all activity →
          </button>
        </div>
      )}
    </div>
  );
}
