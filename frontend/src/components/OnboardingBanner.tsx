"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

type Summary = { total: number; ready: number; onboarding: string[] };

/**
 * Global banner shown while any repo is still onboarding, so it's obvious the
 * teammate is busy learning the codebase and answers may be incomplete. Polls
 * the lightweight summary endpoint and renders nothing once everything is ready.
 */
export default function OnboardingBanner() {
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      fetch("/api/repos/onboarding-summary")
        .then((r) => r.json())
        .then((s) => { if (!cancelled) setSummary(s); })
        .catch(() => {});
    };
    poll();
    const id = setInterval(poll, 20_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (!summary || !summary.onboarding?.length) return null;

  const names = summary.onboarding.join(", ");
  return (
    <div
      className="flex items-center gap-2.5 px-6 py-2 text-[13px]"
      style={{
        background: "rgba(212, 165, 116, 0.10)",
        borderBottom: "1px solid var(--line)",
        color: "var(--paper-1)",
      }}
    >
      <Loader2 size={14} className="animate-spin shrink-0" style={{ color: "var(--amber)" }} />
      <span>
        Onboarding <strong style={{ color: "var(--paper-0)" }}>{names}</strong> — the teammate is still
        learning your codebase, so some answers may be incomplete.
      </span>
      <span className="ml-auto font-mono text-[11px] shrink-0" style={{ color: "var(--paper-3)" }}>
        {summary.ready}/{summary.total} ready
      </span>
    </div>
  );
}
