"use client";

import { Bell, Search, Settings } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";

const HIDDEN_ROUTES = ["/login", "/setup"];

const TITLES: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/chat": "Chat",
  "/standup": "Standup",
  "/onboarding": "Onboarding",
  "/marketplace": "Knowledge",
  "/tasks": "Tasks",
  "/repos": "Repos",
  "/team": "Team",
  "/costs": "Costs",
  "/audit": "Audit",
  "/logs": "Logs",
  "/admin": "Settings",
  "/settings": "Settings",
  "/tech-debt": "Tech Debt",
};

function titleFor(pathname: string) {
  if (TITLES[pathname]) return TITLES[pathname];
  const match = Object.keys(TITLES).find((k) => pathname.startsWith(k + "/"));
  return match ? TITLES[match] : "";
}

export default function Topbar() {
  const pathname = usePathname();
  const router = useRouter();
  if (HIDDEN_ROUTES.includes(pathname)) return null;
  const current = titleFor(pathname);

  return (
    <div
      className="flex h-[52px] shrink-0 items-center gap-3.5 px-6"
      style={{
        background: "var(--ink-0)",
        borderBottom: "1px solid var(--line)",
      }}
    >
      <div
        className="flex items-center gap-2 font-mono text-[11px] tracking-[0.04em]"
        style={{ color: "var(--paper-3)" }}
      >
        <span>teammateX</span>
        <span style={{ color: "var(--paper-5)" }}>/</span>
        <span>workspace</span>
        {current && (
          <>
            <span style={{ color: "var(--paper-5)" }}>/</span>
            <span style={{ color: "var(--paper-0)" }}>{current}</span>
          </>
        )}
      </div>

      <button
        className="ml-auto flex cursor-pointer items-center gap-2 rounded-[var(--radius)] px-2.5 py-[5px] font-mono text-[11px]"
        style={{
          border: "1px solid var(--line-strong)",
          color: "var(--paper-3)",
          background: "var(--ink-1)",
        }}
      >
        <Search size={12} />
        <span>Ask {""}or jump to…</span>
        <kbd
          className="rounded-[3px] border px-1.5 py-px font-mono text-[10px]"
          style={{
            background: "var(--ink-3)",
            borderColor: "var(--line-strong)",
            color: "var(--paper-2)",
          }}
        >
          ⌘K
        </kbd>
      </button>

      <TopbarIcon label="Notifications">
        <Bell size={14} />
      </TopbarIcon>
      <TopbarIcon label="Settings" onClick={() => router.push("/admin")}>
        <Settings size={14} />
      </TopbarIcon>
    </div>
  );
}

function TopbarIcon({ children, label, onClick }: { children: React.ReactNode; label: string; onClick?: () => void }) {
  return (
    <button
      title={label}
      onClick={onClick}
      className="grid h-[30px] w-[30px] place-items-center rounded-[var(--radius)] transition-colors"
      style={{
        border: "1px solid var(--line)",
        background: "var(--ink-1)",
        color: "var(--paper-3)",
        cursor: onClick ? "pointer" : "default",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.color = "var(--paper-0)";
        e.currentTarget.style.borderColor = "var(--line-strong)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.color = "var(--paper-3)";
        e.currentTarget.style.borderColor = "var(--line)";
      }}
    >
      {children}
    </button>
  );
}
