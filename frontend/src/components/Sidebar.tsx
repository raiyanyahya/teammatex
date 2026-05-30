"use client";

import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  MessageSquare,
  ListChecks,
  Rocket,
  BookOpen,
  ListTodo,
  GitBranch,
  Users,
  BarChart3,
  ScrollText,
  Terminal,
  Settings,
  LogOut,
  type LucideIcon,
} from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import pkg from "../../package.json";
import { logout } from "../lib/session";

const HIDDEN_ROUTES = ["/login", "/setup"];

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: string;
};

const NAV_GROUPS: { section: string; items: NavItem[] }[] = [
  {
    section: "WORKSPACE",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/chat", label: "Chat", icon: MessageSquare },
      { href: "/standup", label: "Standup", icon: ListChecks },
    ],
  },
  {
    section: "AGENT",
    items: [
      { href: "/onboarding", label: "Onboarding", icon: Rocket },
      { href: "/marketplace", label: "Knowledge", icon: BookOpen },
      { href: "/tasks", label: "Tasks", icon: ListTodo },
    ],
  },
  {
    section: "OBSERVE",
    items: [
      { href: "/repos", label: "Repos", icon: GitBranch },
      { href: "/team", label: "Team", icon: Users },
      { href: "/costs", label: "Costs", icon: BarChart3 },
      { href: "/audit", label: "Audit", icon: ScrollText },
      { href: "/logs", label: "Logs", icon: Terminal },
    ],
  },
  {
    section: "SYSTEM",
    items: [{ href: "/admin", label: "Settings", icon: Settings }],
  },
];

function BrandMark() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
      <circle cx="9" cy="12" r="6.5" stroke="var(--paper-0)" strokeWidth="1.4" />
      <circle cx="15" cy="12" r="6.5" stroke="var(--amber)" strokeWidth="1.4" />
      <circle cx="12" cy="12" r="1.4" fill="var(--amber)" />
    </svg>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [agentName, setAgentName] = useState("Yuji");
  const [uptime, setUptime] = useState<string>("…");

  useEffect(() => {
    const cached = typeof window !== "undefined" ? localStorage.getItem("teammatex_name") : null;
    if (cached) setAgentName(cached);
    fetch("/api/config")
      .then((r) => r.json())
      .then((cfg) => {
        const n = cfg?.config?.teammate_name?.name;
        if (n) setAgentName(n);
      })
      .catch(() => {});

    let cancelled = false;
    const refresh = () => {
      fetch("/api/health")
        .then((r) => r.json())
        .then((h) => {
          if (cancelled) return;
          const s = Number(h?.uptime_seconds);
          if (Number.isFinite(s)) setUptime(formatUptime(s));
        })
        .catch(() => {});
    };
    refresh();
    const id = setInterval(refresh, 60_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (HIDDEN_ROUTES.includes(pathname)) return null;

  return (
    <aside
      className="flex flex-col gap-1 px-3.5 pb-3.5 pt-[18px]"
      style={{
        background: "var(--ink-1)",
        borderRight: "1px solid var(--line)",
      }}
    >
      <div className="mb-1 flex items-center gap-2.5 px-2 pb-[18px] pt-1.5">
        <div className="relative h-6 w-6">
          <BrandMark />
        </div>
        <div
          className="font-serif text-[22px] leading-none tracking-[-0.01em]"
          style={{ color: "var(--paper-0)" }}
        >
          teammate<em className="italic font-normal" style={{ color: "var(--amber)" }}>X</em>
        </div>
      </div>

      {NAV_GROUPS.map((group) => (
        <div key={group.section}>
          <div
            className="px-2 pb-1.5 pt-3.5 font-mono text-[10px] uppercase tracking-[0.12em]"
            style={{ color: "var(--paper-4)" }}
          >
            {group.section}
          </div>
          {group.items.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            const Icon = item.icon;
            return (
              <button
                key={item.href}
                onClick={() => router.push(item.href)}
                className={`group relative flex w-full items-center gap-2.5 rounded-[4px] px-2 py-[7px] text-left text-[13px] font-medium leading-none transition-colors`}
                style={{
                  color: active ? "var(--paper-0)" : "var(--paper-2)",
                  background: active ? "rgba(212, 165, 116, 0.08)" : "transparent",
                }}
                onMouseEnter={(e) => {
                  if (!active) {
                    e.currentTarget.style.background = "rgba(244, 237, 224, 0.03)";
                    e.currentTarget.style.color = "var(--paper-0)";
                  }
                }}
                onMouseLeave={(e) => {
                  if (!active) {
                    e.currentTarget.style.background = "transparent";
                    e.currentTarget.style.color = "var(--paper-2)";
                  }
                }}
              >
                {active && (
                  <span
                    aria-hidden
                    className="absolute -left-3.5 top-1/2 h-[14px] w-[2px] -translate-y-1/2 rounded-r-[2px]"
                    style={{ background: "var(--amber)" }}
                  />
                )}
                <Icon
                  className="shrink-0"
                  size={14}
                  color={active ? "var(--amber)" : "var(--paper-3)"}
                />
                <span className="flex-1 truncate">{item.label}</span>
                {item.badge && (
                  <span
                    className="ml-auto font-mono text-[10px]"
                    style={{ color: active ? "var(--paper-2)" : "var(--paper-4)" }}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      ))}

      <PresenceCard name={agentName} uptime={uptime} version={pkg.version} />

      <button
        onClick={async () => {
          await logout();
          router.push("/login");
        }}
        className="mt-2 flex w-full items-center gap-2.5 rounded-[4px] px-2 py-[7px] text-left text-[13px] font-medium leading-none transition-colors"
        style={{ color: "var(--paper-3)" }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = "rgba(244, 237, 224, 0.03)";
          e.currentTarget.style.color = "var(--paper-0)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = "transparent";
          e.currentTarget.style.color = "var(--paper-3)";
        }}
      >
        <LogOut className="shrink-0" size={14} color="var(--paper-3)" />
        <span className="flex-1 truncate">Sign out</span>
      </button>
    </aside>
  );
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  return `${d}d`;
}

function PresenceCard({ name, uptime, version }: { name: string; uptime: string; version: string }) {
  return (
    <div
      className="relative mt-auto p-3"
      style={{
        border: "1px solid var(--line)",
        borderRadius: "var(--radius)",
        background:
          "linear-gradient(180deg, rgba(212, 165, 116, 0.04), transparent)",
      }}
    >
      <div className="flex items-center gap-2.5">
        <div
          className="relative h-7 w-7 shrink-0 rounded-full"
          style={{
            background:
              "radial-gradient(circle at 30% 30%, var(--amber), var(--amber-dim) 60%, var(--ink-3))",
            boxShadow:
              "0 0 0 1px var(--line-strong), 0 0 12px rgba(212, 165, 116, 0.2)",
          }}
        >
          <span
            className="absolute -bottom-px -right-px h-2 w-2 rounded-full"
            style={{
              background: "var(--sage)",
              border: "2px solid var(--ink-1)",
            }}
          />
        </div>
        <div className="min-w-0">
          <div
            className="font-serif text-[16px] leading-none"
            style={{ color: "var(--paper-0)" }}
          >
            {name}
          </div>
          <div
            className="mt-[3px] flex items-center gap-1.5 font-mono text-[10px] tracking-[0.06em]"
            style={{ color: "var(--paper-3)" }}
          >
            <span
              className="h-[5px] w-[5px] rounded-full"
              style={{
                background: "var(--sage)",
                animation: "pulse 2s ease-in-out infinite",
              }}
            />
            ONLINE
          </div>
        </div>
      </div>
      <div
        className="mt-2.5 flex gap-3 border-t pt-2.5"
        style={{ borderTop: "1px dashed var(--line-strong)" }}
      >
        <div className="font-mono text-[10px]" style={{ color: "var(--paper-3)" }}>
          uptime <span className="text-[11px]" style={{ color: "var(--paper-0)" }}>{uptime}</span>
        </div>
        <div className="font-mono text-[10px]" style={{ color: "var(--paper-3)" }}>
          v<span className="text-[11px]" style={{ color: "var(--paper-0)" }}>{version}</span>
        </div>
      </div>
    </div>
  );
}
