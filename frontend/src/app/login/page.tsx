"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Key, ArrowRight } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function login(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Login failed");
      }

      const data = await res.json();
      localStorage.setItem("token", data.token);
      localStorage.setItem("user", JSON.stringify(data.user));
      router.push("/dashboard");
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#1a1a1a]">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-lg font-semibold text-[#e4e4e7]">TeammateX</h1>
          <p className="mt-1 text-xs text-[#a1a1aa]">Sign in to your workspace</p>
        </div>

        <form onSubmit={login} className="panel p-6 space-y-4">
          <div>
            <label className="block mb-1.5 text-[11px] font-semibold text-[#a1a1aa] uppercase tracking-wide">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@teammatex.local"
              className="input"
              autoFocus
              required
            />
          </div>

          <div>
            <label className="block mb-1.5 text-[11px] font-semibold text-[#a1a1aa] uppercase tracking-wide">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              className="input"
              required
            />
          </div>

          {error && (
            <div className="rounded border border-[#3a1818] bg-[#1f1010] px-3 py-2 text-xs text-[#f87171]">
              {error}
            </div>
          )}

          <button type="submit" disabled={loading} className="btn-primary w-full justify-center">
            {loading ? "Signing in..." : "Sign in"} <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </form>

        <p className="mt-4 text-center text-[11px] text-[#71717a]">
          First time? The default password is shown in the terminal when the server starts.
        </p>
      </div>
    </div>
  );
}
