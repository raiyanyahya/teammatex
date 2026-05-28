"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2 } from "lucide-react";

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
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--ink-0)",
        padding: 24,
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(ellipse at 20% 0%, rgba(212, 165, 116, 0.06), transparent 50%), radial-gradient(ellipse at 80% 100%, rgba(168, 136, 181, 0.04), transparent 50%)",
          pointerEvents: "none",
        }}
      />
      <div style={{ width: "100%", maxWidth: 360, position: "relative" }}>
        <div style={{ marginBottom: 28, textAlign: "center" }}>
          <div
            style={{
              fontFamily: "var(--serif)",
              fontSize: 40,
              lineHeight: 1,
              color: "var(--paper-0)",
              letterSpacing: "-0.02em",
            }}
          >
            teammate<em style={{ color: "var(--amber)", fontStyle: "italic" }}>X</em>
          </div>
          <div
            className="font-mono"
            style={{
              fontSize: 11,
              color: "var(--paper-3)",
              letterSpacing: "0.12em",
              textTransform: "uppercase",
              marginTop: 12,
            }}
          >
            sign in to your workspace
          </div>
        </div>

        <form
          onSubmit={login}
          className="card"
          style={{ padding: 24, display: "flex", flexDirection: "column", gap: 16 }}
        >
          <div>
            <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-3)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>
              Email
            </div>
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
            <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-3)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>
              Password
            </div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="input"
              required
            />
          </div>

          {error && (
            <div
              style={{
                padding: "8px 12px",
                border: "1px solid rgba(194, 116, 95, 0.3)",
                background: "rgba(194, 116, 95, 0.06)",
                borderRadius: 6,
                fontSize: 12,
                color: "var(--rust)",
              }}
            >
              {error}
            </div>
          )}

          <button type="submit" disabled={loading} className="btn btn-primary" style={{ width: "100%", justifyContent: "center" }}>
            {loading ? <Loader2 size={13} className="animate-spin" /> : <ArrowRight size={13} />}
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p
          className="font-mono"
          style={{ marginTop: 16, textAlign: "center", fontSize: 10, color: "var(--paper-4)" }}
        >
          First time? The default password prints in the terminal when the server starts.
        </p>
      </div>
    </div>
  );
}
