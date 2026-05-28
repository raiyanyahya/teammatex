"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Loader2, Wrench, ChevronRight, Check, X, Shield, Trash2,
  Compass, Network, Bug, NotebookPen, Search, GitPullRequest, FileText, ListChecks, Users } from "lucide-react";

interface Message {
  role: "user" | "assistant" | "tool";
  content: string;
  tool?: string;
  args?: string;
  result?: string;
  expanded?: boolean;
  permission?: boolean;
}

const STORAGE_KEY = "teammatex_chat";
const MAX_STORED = 50;

const CAPABILITIES = [
  { label: "Understand the architecture", icon: Compass,
    example: "Explain how this codebase is structured." },
  { label: "Trace dependencies", icon: Network,
    example: "What calls the login function, and what does it depend on?" },
  { label: "Find the owner", icon: Users,
    example: "Who owns the auth module and should review changes to it?" },
  { label: "Find & fix issues", icon: Bug,
    example: "Find security bugs in our codebase and fix them." },
  { label: "Remember a decision", icon: NotebookPen,
    example: "Remember that we use snake_case for all API field names." },
  { label: "Recall what we agreed", icon: Search,
    example: "What conventions have we agreed on so far?" },
  { label: "Open a pull request", icon: GitPullRequest,
    example: "Add rate limiting to the login endpoint and open a PR." },
  { label: "Write docs", icon: FileText,
    example: "Write module docs for the auth package." },
  { label: "Standup", icon: ListChecks,
    example: "Give me a standup of recent activity." },
];

function loadMessages(): Message[] {
  if (typeof window === "undefined") return [];
  try { const saved = localStorage.getItem(STORAGE_KEY); return saved ? JSON.parse(saved) : []; }
  catch { return []; }
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>(loadMessages);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamContent, setStreamContent] = useState("");
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (messages.length > 0) {
      const visible = messages.filter(m => m.role !== "tool" || m.expanded);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(visible.slice(-MAX_STORED)));
    }
  }, [messages]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, streamContent]);
  useEffect(() => { inputRef.current?.focus(); }, []);
  // Auto-send a question passed from the dashboard's "Ask" box (?q=...).
  // Read from window.location to avoid a useSearchParams Suspense boundary.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      window.history.replaceState(null, "", "/chat");
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function clearHistory() {
    localStorage.removeItem(STORAGE_KEY);
    setMessages([]);
  }

  async function send(text?: string) {
    const userMsg = (text ?? input).trim();
    if (!userMsg || streaming) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setStreaming(true);
    setStreamContent("");
    setActiveTool(null);

    let accumulated = "";
    let toolMessages: Message[] = [];

    const history = messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .slice(-20)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const response = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg, history }),
      });

      const reader = response.body?.getReader();
      if (!reader) { setStreaming(false); return; }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6);
          if (payload === "[DONE]") break;

          try {
            const data = JSON.parse(payload);
            if (data.type === "text") {
              accumulated += data.content;
              setStreamContent(accumulated);
            } else if (data.type === "tool_start") {
              setActiveTool(data.tool);
              setStreamContent("");
            } else if (data.type === "tool_end") {
              const raw = data.result || "{}";
              let preview = raw;
              try {
                const parsed = JSON.parse(raw);
                if (parsed.success === true && parsed.data) {
                  const d = parsed.data;
                  if (d.matches) preview = `Found ${d.matches.length || 0} matches`;
                  else if (d.content) preview = `Read ${d.lines || 0} lines`;
                  else if (Array.isArray(d)) preview = `Found ${d.length} results`;
                  else preview = `Found ${Object.keys(d).length} results`;
                } else if (parsed.error) {
                  preview = parsed.error.slice(0, 80);
                }
              } catch {}
              toolMessages.push({
                role: "tool", content: "", tool: data.tool,
                args: preview, result: raw.slice(0, 1000),
                expanded: false,
              });
              setActiveTool(null);
            }
          } catch {}
        }
      }
    } catch {
      accumulated = "Error connecting to the server. Make sure everything is running.";
    } finally {
      setStreaming(false);
      setActiveTool(null);

      if (accumulated) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: accumulated },
        ]);
      } else if (toolMessages.length > 0 && accumulated === "") {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "(I checked the codebase but need you to be more specific — what exactly are you looking for?)" },
        ]);
      }
      setStreamContent("");
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-6 py-8">
          {messages.length === 0 && !streaming && (
            <div className="mt-20">
              <div className="text-center">
                <h1 className="text-lg font-semibold text-[#e4e4e7]">TeammateX</h1>
                <p className="mt-1 text-sm text-[#a1a1aa]">
                  An AI teammate that knows your codebase. Here&apos;s what you can ask — click one to start.
                </p>
              </div>
              <div className="mt-8 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {CAPABILITIES.map((c) => (
                  <button
                    key={c.label}
                    onClick={() => { setInput(c.example); inputRef.current?.focus(); }}
                    className="rounded-md border border-[#262626] bg-[#1a1a1a] px-3 py-2.5 text-left transition-colors hover:border-[#3b82f6] hover:bg-[#202020]"
                  >
                    <div className="flex items-center gap-2 text-[13px] font-medium text-[#e4e4e7]">
                      <c.icon className="h-3.5 w-3.5 text-[#60a5fa]" />
                      {c.label}
                    </div>
                    <div className="mt-1 text-xs text-[#a1a1aa]">&ldquo;{c.example}&rdquo;</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-5">
            {messages.map((msg, i) => {
              if (msg.role === "tool") {
                return null;
              }

              return (
                <div key={i} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                  <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-medium ${
                    msg.role === "assistant" ? "bg-[#262626] text-[#a1a1aa]" : "bg-[#3b82f6]/30 text-[#60a5fa]"
                  }`}>
                    {msg.role === "assistant" ? "T" : "U"}
                  </div>
                  <div className={`max-w-[80%] rounded-md px-4 py-2.5 text-sm leading-relaxed ${
                    msg.role === "assistant" ? "bg-[#202020] text-[#e4e4e7]" : "bg-[#3b82f6]/15 text-[#bfdbfe]"
                  }`}>
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>
                </div>
              );
            })}

            {streaming && activeTool && (
              <div className="flex justify-center">
                <div className="rounded-full border border-[#262626] bg-[#141414] px-3 py-1 text-[11px] text-[#71717a]">
                  <span className="inline-flex items-center gap-1">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span className="font-medium">{activeTool}</span>
                    <span className="opacity-60">running...</span>
                  </span>
                </div>
              </div>
            )}

            {streaming && streamContent && (
              <div className="flex gap-3">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#262626] text-xs font-medium text-[#a1a1aa]">T</div>
                <div className="max-w-[80%] rounded-md bg-[#202020] px-4 py-2.5 text-sm leading-relaxed text-[#e4e4e7]">
                  <div className="whitespace-pre-wrap">
                    {streamContent}
                    <span className="ml-0.5 inline-block h-4 w-1 animate-pulse rounded-sm bg-[#a1a1aa]" />
                  </div>
                </div>
              </div>
            )}

            {streaming && !streamContent && !activeTool && (
              <div className="flex gap-3">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-[#262626] text-xs font-medium text-[#a1a1aa]">T</div>
                <div className="flex items-center gap-1 rounded-md bg-[#202020] px-4 py-2.5">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-[#a1a1aa]" />
                  <span className="text-xs text-[#a1a1aa]">Thinking</span>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        </div>
      </div>

      <div className="border-t border-[#2b2b2e] bg-[#161616]">
        <div className="mx-auto max-w-2xl px-6 py-3">
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about your codebase..."
              disabled={streaming}
              className="flex-1 rounded-md border border-[#2b2b2e] bg-[#1a1a1a] px-3 py-2 text-sm text-[#e4e4e7] outline-none placeholder:text-[#71717a] focus:border-[#3b82f6]"
            />
            {messages.length > 0 && (
              <button
                onClick={clearHistory}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[#2b2b2e] bg-transparent text-[#a1a1aa] hover:text-[#f87171] hover:border-[#f87171]/30 transition-colors"
                title="Clear chat"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
            <button
              onClick={() => send()}
              disabled={streaming || !input.trim()}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#3b82f6] text-white hover:bg-[#3574e0] disabled:opacity-30 transition-colors"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
