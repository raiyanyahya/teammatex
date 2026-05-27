"use client";

import { useEffect, useState } from "react";
import { MessageSquare, LayoutDashboard, Rocket, FolderGit2, ListTodo, ListChecks, Settings, Users, BarChart3, ScrollText, Terminal } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";

const HIDDEN_ROUTES = ["/login", "/setup"];

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/standup", label: "Standup", icon: ListChecks },
  { href: "/onboarding", label: "Onboarding", icon: Rocket },
  { href: "/repos", label: "Repos", icon: FolderGit2 },
  { href: "/tasks", label: "Tasks", icon: ListTodo },
  { href: "/team", label: "Team", icon: Users },
  { href: "/costs", label: "Costs", icon: BarChart3 },
  { href: "/audit", label: "Audit", icon: ScrollText },
  { href: "/logs", label: "Logs", icon: Terminal },
  { href: "/admin", label: "Settings", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(true);

  if (HIDDEN_ROUTES.includes(pathname)) return null;

  return (
    <aside
      className={`flex flex-col border-r border-[#2a2a2e] bg-[#212127] transition-all duration-200 ${collapsed ? "w-[48px]" : "w-[208px]"}`}
    >
      <div className="flex h-10 items-center border-b border-[#2a2a2e] px-3">
        {!collapsed && (
          <span className="text-xs font-semibold tracking-wide text-[#8a8a8e] uppercase">TeammateX</span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className={`ml-auto rounded p-0.5 text-[#5a5a5e] hover:text-[#8a8a8e] hover:bg-[#2a2a30] ${collapsed ? "mx-auto" : ""}`}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className={`transition-transform ${collapsed ? "rotate-180" : ""}`}>
            <path d="M9 3L5 7L9 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>

      <nav className="flex-1 space-y-0.5 p-1.5">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <button
              key={item.href}
              onClick={() => router.push(item.href)}
              className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors
                ${active
                  ? "bg-[#2a2a30] text-[#cccccc]"
                  : "text-[#6a6a6e] hover:text-[#cccccc] hover:bg-[#25252b]"
                }
                ${collapsed ? "justify-center px-0" : ""}`}
            >
              <item.icon className="h-3.5 w-3.5 shrink-0" />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-[#2a2a2e] p-1.5">
        <div className={`flex items-center gap-1.5 rounded px-2 py-1.5 text-[10px] text-[#5a5a5e] ${collapsed ? "justify-center" : ""}`}>
          <span className="h-1.5 w-1.5 rounded-full bg-[#4a9e4a]" />
          {!collapsed && <span>Online</span>}
        </div>
      </div>
    </aside>
  );
}
