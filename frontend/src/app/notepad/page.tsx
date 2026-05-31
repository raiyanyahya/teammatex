"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

/**
 * A single always-saved scratchpad per user. Loads on open and autosaves on a
 * debounce — no Save button. A black, full-height textarea.
 */
export default function NotepadPage() {
  const [content, setContent] = useState("");
  const [status, setStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [loaded, setLoaded] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const n = await api.get<{ content: string }>("/notepad");
        setContent(n.content || "");
      } catch {}
      setLoaded(true);
    })();
  }, []);

  // Autosave on a ~800ms debounce after typing stops. Skip the initial load so
  // we don't immediately re-save what we just fetched.
  useEffect(() => {
    if (!loaded) return;
    setStatus("saving");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        await api.post("/notepad", { content });
        setStatus("saved");
      } catch {
        setStatus("idle");
      }
    }, 800);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [content, loaded]);

  return (
    <div className="flex h-full flex-col">
      <div
        className="flex items-center justify-between px-6 py-4"
        style={{ borderBottom: "1px solid var(--line)" }}
      >
        <h1 className="font-serif text-[20px] leading-none" style={{ color: "var(--paper-0)" }}>
          Notepad
        </h1>
        <span className="font-mono text-[11px]" style={{ color: "var(--paper-4)" }}>
          {status === "saving" ? "Saving…" : status === "saved" ? "Saved" : ""}
        </span>
      </div>
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        spellCheck={false}
        placeholder="Type here. Everything is saved automatically."
        className="flex-1 w-full resize-none p-6 font-mono text-[14px] leading-relaxed outline-none"
        style={{ background: "#000", color: "var(--paper-0)" }}
      />
    </div>
  );
}
