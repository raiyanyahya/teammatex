"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("token");

    if (!token) {
      if (pathname !== "/login" && pathname !== "/setup") {
        router.replace("/login");
        return;
      }
      setReady(true);
      return;
    }

    fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => {
        if (!res.ok) {
          localStorage.removeItem("token");
          localStorage.removeItem("user");
          if (pathname !== "/login") router.replace("/login");
        }
      })
      .catch(() => {});

    if (pathname === "/login") {
      router.replace("/dashboard");
    }

    setReady(true);
  }, [pathname, router]);

  if (!ready && pathname !== "/login") {
    return (
      <div
        className="flex h-screen items-center justify-center"
        style={{ background: "var(--ink-0)" }}
      >
        <div
          className="h-4 w-4 animate-spin rounded-full border-2 border-t-transparent"
          style={{ borderColor: "var(--amber)", borderTopColor: "transparent" }}
        />
      </div>
    );
  }

  return <>{children}</>;
}
