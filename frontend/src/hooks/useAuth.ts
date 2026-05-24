"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";

interface User {
  id: string;
  email: string;
  name: string;
}

export function useAuth() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("token");
    const stored = localStorage.getItem("user");

    if (!token) {
      if (pathname !== "/login" && pathname !== "/setup") {
        router.push("/login");
      }
      setLoading(false);
      return;
    }

    if (stored) {
      try {
        setUser(JSON.parse(stored));
      } catch {}
    }

    fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => {
        if (res.status === 401) {
          localStorage.removeItem("token");
          localStorage.removeItem("user");
          if (pathname !== "/login" && pathname !== "/setup") {
            router.push("/login");
          }
        }
      })
      .catch(() => {});

    setLoading(false);
  }, [pathname, router]);

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setUser(null);
    router.push("/login");
  }

  return { user, loading, logout, isAuthenticated: !!user };
}
