"use client";

import { Settings } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import NotificationsBell from "./NotificationsBell";

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

      <div className="ml-auto" />
      <NotificationsBell />
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
