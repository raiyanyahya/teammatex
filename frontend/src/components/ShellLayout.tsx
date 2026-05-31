"use client";

import { usePathname } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import Topbar from "@/components/Topbar";
import OnboardingBanner from "@/components/OnboardingBanner";

const FULLSCREEN_ROUTES = ["/login", "/setup"];

export default function ShellLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const fullscreen = FULLSCREEN_ROUTES.includes(pathname);

  if (fullscreen) {
    return (
      <main
        className="h-screen w-screen overflow-y-auto"
        style={{ background: "var(--ink-0)" }}
      >
        {children}
      </main>
    );
  }

  return (
    <div className="shell">
      <Sidebar />
      <main
        className="flex min-h-0 flex-col overflow-hidden"
        style={{ background: "var(--ink-0)" }}
      >
        <Topbar />
        <OnboardingBanner />
        <div className="flex-1 overflow-y-auto overflow-x-hidden">{children}</div>
      </main>
    </div>
  );
}
