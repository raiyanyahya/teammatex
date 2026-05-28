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
  const [collapsed, setCollapsed] = useState(false);

  if (HIDDEN_ROUTES.includes(pathname)) return null;

  return (
    <aside
      className={`flex flex-col border-r border-[#262626] bg-[#161616] transition-all duration-200 ${collapsed ? "w-[52px]" : "w-[216px]"}`}
    >
      <div className="flex h-12 items-center border-b border-[#262626] px-3.5">
        {!collapsed && (
          <span className="text-[13px] font-semibold tracking-tight text-[#e4e4e7]">TeammateX</span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className={`ml-auto rounded-md p-1 text-[#71717a] hover:text-[#e4e4e7] hover:bg-[#262626] ${collapsed ? "mx-auto" : ""}`}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className={`transition-transform ${collapsed ? "rotate-180" : ""}`}>
            <path d="M9 3L5 7L9 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>

      <nav className="flex-1 space-y-0.5 p-2">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <button
              key={item.href}
              onClick={() => router.push(item.href)}
              className={`flex w-full items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors
                ${active
                  ? "bg-[#262626] text-[#e4e4e7] font-medium"
                  : "text-[#a1a1aa] hover:text-[#e4e4e7] hover:bg-[#212121]"
                }
                ${collapsed ? "justify-center px-0" : ""}`}
            >
              <item.icon className={`h-[18px] w-[18px] shrink-0 ${active ? "text-[#60a5fa]" : "text-[#71717a]"}`} />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </button>
          );
        })}
      </nav>

      <div className="border-t border-[#262626] p-2">
        <div className={`flex items-center gap-2 rounded px-2.5 py-1.5 text-[11px] text-[#71717a] ${collapsed ? "justify-center" : ""}`}>
          <span className="h-2 w-2 rounded-full bg-[#22c55e]" />
          {!collapsed && <span>Online</span>}
        </div>
      </div>
    </aside>
  );
}
