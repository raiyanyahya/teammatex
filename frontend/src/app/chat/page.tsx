"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Sources, { Source } from "../../components/chat/Sources";
import {
  Bug,
  Compass,
  FileText,
  GitPullRequest,
  ListChecks,
  Loader2,
  Network,
  NotebookPen,
  Paperclip,
  Plus,
  Search,
  Send,
  Trash2,
  Users,
} from "lucide-react";

type Role = "user" | "assistant" | "tool";

interface Message {
  role: Role;
  content: string;
  tool?: string;
  args?: string;
  result?: string;
  sources?: Source[];
}

const STORAGE_KEY = "teammatex_chat";
const MAX_STORED = 50;

const CAPABILITIES = [
  { label: "Understand the architecture", Icon: Compass, example: "Explain how this codebase is structured." },
  { label: "Trace dependencies", Icon: Network, example: "What calls the login function, and what does it depend on?" },
  { label: "Find the owner", Icon: Users, example: "Who owns the auth module and should review changes to it?" },
  { label: "Find & fix issues", Icon: Bug, example: "Find security bugs in our codebase and fix them." },
  { label: "Remember a decision", Icon: NotebookPen, example: "Remember that we use snake_case for all API field names." },
  { label: "Recall what we agreed", Icon: Search, example: "What conventions have we agreed on so far?" },
  { label: "Open a pull request", Icon: GitPullRequest, example: "Add rate limiting to the login endpoint and open a PR." },
  { label: "Write docs", Icon: FileText, example: "Write module docs for the auth package." },
  { label: "Standup", Icon: ListChecks, example: "Give me a standup of recent activity." },
];

function loadMessages(): Message[] {
  if (typeof window === "undefined") return [];
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved ? JSON.parse(saved) : [];
  } catch {
    return [];
  }
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>(loadMessages);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamContent, setStreamContent] = useState("");
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-MAX_STORED)));
    }
  }, [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamContent]);

  useEffect(() => {
    taRef.current?.focus();
  }, []);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      window.history.replaceState(null, "", "/chat");
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function clear() {
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
    const toolMessages: Message[] = [];
    let sources: Source[] = [];

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
      if (!reader) {
        setStreaming(false);
        return;
      }

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
                  preview = String(parsed.error).slice(0, 80);
                }
              } catch {}
              toolMessages.push({
                role: "tool",
                content: "",
                tool: data.tool,
                args: preview,
                result: raw.slice(0, 1000),
              });
              setActiveTool(null);
            } else if (data.type === "sources") {
              sources = Array.isArray(data.sources) ? data.sources : [];
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
        setMessages((prev) => [...prev, ...toolMessages, { role: "assistant", content: accumulated, sources }]);
      } else if (toolMessages.length > 0) {
        setMessages((prev) => [...prev, ...toolMessages, {
          role: "assistant",
          content: "(I checked the codebase but need you to be more specific — what exactly are you looking for?)",
        }]);
      }
      setStreamContent("");
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      send();
    } else if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  const messageCount = useMemo(
    () => messages.filter((m) => m.role !== "tool").length,
    [messages],
  );
  const toolCount = useMemo(() => messages.filter((m) => m.role === "tool").length, [messages]);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", height: "100%", overflow: "hidden" }}>
      <aside style={{ borderRight: "1px solid var(--line)", background: "var(--ink-1)", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: 16, borderBottom: "1px solid var(--line)" }}>
          <button className="btn" style={{ width: "100%", justifyContent: "center" }} onClick={clear} disabled={streaming}>
            <Plus size={12} /> New conversation
          </button>
        </div>
        <div style={{ padding: "8px 0", flex: 1, overflowY: "auto" }}>
          <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)", letterSpacing: "0.12em", padding: "8px 16px" }}>
            CURRENT
          </div>
          <div
            style={{
              padding: "10px 16px",
              background: "rgba(212,165,116,0.06)",
              borderLeft: "2px solid var(--amber)",
              cursor: "default",
            }}
          >
            <div style={{ fontSize: 13, color: "var(--paper-0)" }}>
              {messages.length === 0 ? "Ready when you are" : "This conversation"}
            </div>
            <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)", marginTop: 3 }}>
              {messageCount} {messageCount === 1 ? "msg" : "msgs"} · {toolCount} tool {toolCount === 1 ? "call" : "calls"}
            </div>
          </div>
        </div>
        <div style={{ padding: 16, borderTop: "1px solid var(--line)" }}>
          <button
            className="btn btn-ghost"
            style={{ width: "100%", justifyContent: "center" }}
            onClick={clear}
            disabled={streaming || messages.length === 0}
          >
            <Trash2 size={12} /> Clear history
          </button>
        </div>
      </aside>

      <section style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div
          style={{
            padding: "14px 28px",
            borderBottom: "1px solid var(--line)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div>
            <div style={{ fontFamily: "var(--serif)", fontSize: 20, lineHeight: 1.2 }}>
              {messages.length === 0 ? "Ask about your codebase" : "This conversation"}
            </div>
            <div className="font-mono" style={{ fontSize: 11, marginTop: 3, color: "var(--paper-4)" }}>
              {messageCount} {messageCount === 1 ? "message" : "messages"} · {toolCount} tool{toolCount === 1 ? "" : "s"} used
            </div>
          </div>
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px" }}>
          <div style={{ maxWidth: 820, margin: "0 auto", display: "flex", flexDirection: "column", gap: 24 }}>
            {messages.length === 0 && !streaming && (
              <div>
                <div style={{ fontFamily: "var(--serif)", fontSize: 28, color: "var(--paper-0)", marginBottom: 6 }}>
                  Pick a thread to start<em style={{ color: "var(--amber)", fontStyle: "italic" }}>.</em>
                </div>
                <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-3)", letterSpacing: "0.06em", marginBottom: 16 }}>
                  Yuji knows your codebase, your team, and your history. Click one to start.
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  {CAPABILITIES.map((c) => (
                    <button
                      key={c.label}
                      onClick={() => {
                        setInput(c.example);
                        taRef.current?.focus();
                      }}
                      style={{
                        background: "var(--ink-1)",
                        border: "1px solid var(--line)",
                        borderRadius: 6,
                        padding: 12,
                        cursor: "pointer",
                        textAlign: "left",
                        color: "var(--paper-0)",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                        <c.Icon size={14} style={{ color: "var(--amber)" }} />
                        {c.label}
                      </div>
                      <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)", marginTop: 6 }}>
                        “{c.example}”
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) => (
              <MessageRow key={i} m={m} />
            ))}

            {streaming && (streamContent || activeTool) && (
              <AgentThinking content={streamContent} tool={activeTool} />
            )}
            {streaming && !streamContent && !activeTool && <AgentThinking content="" tool={null} />}

            <div ref={bottomRef} />
          </div>
        </div>

        <div style={{ padding: "16px 28px 22px", borderTop: "1px solid var(--line)", background: "var(--ink-1)" }}>
          <div style={{ maxWidth: 820, margin: "0 auto" }}>
            <div style={{ background: "var(--ink-2)", border: "1px solid var(--line-strong)", borderRadius: 8, padding: 12 }}>
              <textarea
                ref={taRef}
                placeholder="Ask Yuji about your codebase, team, or history…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKey}
                disabled={streaming}
                style={{
                  width: "100%",
                  background: "transparent",
                  border: "none",
                  color: "var(--paper-0)",
                  fontFamily: "var(--sans)",
                  fontSize: 14,
                  outline: "none",
                  resize: "none",
                  minHeight: 50,
                }}
              />
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
                <button className="btn btn-ghost" style={{ padding: "4px 8px", fontSize: 11 }} disabled>
                  <Paperclip size={11} /> Attach
                </button>
                <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
                  <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>⌘ + ⏎</span>
                  <button className="btn btn-primary" onClick={() => send()} disabled={streaming || !input.trim()}>
                    {streaming ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />} Send
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

function MessageRow({ m }: { m: Message }) {
  if (m.role === "tool") {
    return (
      <div
        style={{
          background: "var(--ink-1)",
          border: "1px solid var(--line)",
          borderRadius: 6,
          padding: "8px 12px",
          fontFamily: "var(--mono)",
          fontSize: 11,
          marginLeft: 42,
        }}
      >
        <span style={{ color: "var(--sky)" }}>→ {m.tool}</span>
        <span style={{ color: "var(--paper-4)" }}> · </span>
        <span style={{ color: "var(--sage)" }}>{m.args}</span>
      </div>
    );
  }
  if (m.role === "user") {
    return (
      <div style={{ display: "flex", gap: 14, justifyContent: "flex-end" }}>
        <div
          style={{
            maxWidth: 520,
            background: "var(--ink-2)",
            border: "1px solid var(--line-strong)",
            borderRadius: "10px 10px 2px 10px",
            padding: "12px 14px",
          }}
        >
          <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-3)", letterSpacing: "0.06em", marginBottom: 4 }}>
            @you
          </div>
          <div style={{ fontSize: 14, color: "var(--paper-0)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{m.content}</div>
        </div>
        <UserAvatar />
      </div>
    );
  }
  return (
    <div style={{ display: "flex", gap: 14 }}>
      <YujiAvatar />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span className="font-mono" style={{ fontSize: 11, color: "var(--amber)", letterSpacing: "0.06em" }}>
            YUJI
          </span>
        </div>
        <div style={{ fontSize: 14, color: "var(--paper-0)", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{m.content}</div>
        <Sources sources={m.sources} />
      </div>
    </div>
  );
}

function AgentThinking({ content, tool }: { content: string; tool: string | null }) {
  return (
    <div style={{ display: "flex", gap: 14 }}>
      <YujiAvatar />
      <div>
        <div className="font-mono" style={{ fontSize: 11, color: "var(--amber)", letterSpacing: "0.06em" }}>
          YUJI
        </div>
        {tool && !content && (
          <div
            style={{
              marginTop: 8,
              fontFamily: "var(--mono)",
              fontSize: 11,
              color: "var(--paper-3)",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <Loader2 size={11} className="animate-spin" />
            <span style={{ color: "var(--sky)" }}>{tool}</span>
            <span className="thinking" style={{ color: "var(--paper-4)" }}>
              running
            </span>
          </div>
        )}
        {content && (
          <div style={{ marginTop: 4, fontSize: 14, color: "var(--paper-0)", lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
            {content}
            <span
              style={{
                marginLeft: 2,
                display: "inline-block",
                width: 4,
                height: 14,
                background: "var(--paper-3)",
                verticalAlign: -2,
                animation: "pulse 1s ease-in-out infinite",
              }}
            />
          </div>
        )}
        {!tool && !content && (
          <div
            style={{
              marginTop: 4,
              fontFamily: "var(--serif)",
              fontSize: 16,
              color: "var(--paper-2)",
              fontStyle: "italic",
            }}
          >
            <span className="thinking">thinking</span>
          </div>
        )}
      </div>
    </div>
  );
}

function YujiAvatar() {
  return (
    <span
      style={{
        width: 28,
        height: 28,
        flexShrink: 0,
        borderRadius: "50%",
        background: "radial-gradient(circle at 30% 30%, var(--amber), var(--amber-dim) 60%, var(--ink-3))",
        boxShadow: "0 0 0 1px var(--line-strong), 0 0 12px rgba(212, 165, 116, 0.2)",
        display: "inline-block",
      }}
    />
  );
}

function UserAvatar() {
  return (
    <span
      style={{
        width: 28,
        height: 28,
        flexShrink: 0,
        borderRadius: "50%",
        background: "var(--ink-3)",
        display: "grid",
        placeItems: "center",
        fontFamily: "var(--serif)",
        fontSize: 13,
        color: "var(--paper-1)",
        border: "1px solid var(--line-strong)",
      }}
    >
      Y
    </span>
  );
}
