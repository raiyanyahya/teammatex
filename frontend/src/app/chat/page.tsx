"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Sources, { Source } from "../../components/chat/Sources";
import Markdown, { CopyButton } from "../../components/chat/Markdown";
import {
  Bug,
  Compass,
  FileText,
  GitPullRequest,
  ListChecks,
  Loader2,
  MessageSquare,
  Network,
  NotebookPen,
  Paperclip,
  Plus,
  Search,
  Send,
  Square,
  Trash2,
  Users,
  X,
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

interface ConvSummary {
  id: string;
  title: string | null;
  created_at: string | null;
}

interface UploadItem {
  id: string;
  filename: string;
  size_bytes: number;
}

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

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversations, setConversations] = useState<ConvSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamContent, setStreamContent] = useState("");
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [attachment, setAttachment] = useState<{ id: string; filename: string } | null>(null);
  const [showAttach, setShowAttach] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamContent]);

  useEffect(() => {
    taRef.current?.focus();
    loadConversations();
  }, []);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) {
      window.history.replaceState(null, "", "/chat");
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadConversations() {
    try {
      const r = await fetch("/api/conversations");
      if (r.ok) setConversations(await r.json());
    } catch {}
  }

  async function openConversation(id: string) {
    if (streaming || id === conversationId) return;
    try {
      const r = await fetch(`/api/conversations/${id}`);
      if (!r.ok) return;
      const data = await r.json();
      setMessages((data.messages || []).map((m: Message) => ({ role: m.role, content: m.content })));
      setConversationId(id);
    } catch {}
  }

  function newConversation() {
    if (streaming) return;
    setMessages([]);
    setConversationId(null);
    setInput("");
    setAttachment(null);
    setShowAttach(false);
    taRef.current?.focus();
  }

  async function deleteConversation(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await fetch(`/api/conversations/${id}`, { method: "DELETE" });
    } catch {}
    if (id === conversationId) newConversation();
    loadConversations();
  }

  async function toggleAttach() {
    if (!showAttach) {
      try {
        const r = await fetch("/api/uploads");
        if (r.ok) setUploads(await r.json());
      } catch {}
    }
    setShowAttach((v) => !v);
  }

  function stop() {
    abortRef.current?.abort();
  }

  async function send(text?: string) {
    const userMsg = (text ?? input).trim();
    if (!userMsg || streaming) return;
    setInput("");
    const att = attachment;
    setAttachment(null);
    setShowAttach(false);
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setStreaming(true);
    setStreamContent("");
    setActiveTool(null);

    let accumulated = "";
    const toolMessages: Message[] = [];
    let sources: Source[] = [];
    let newConvId: string | null = null;
    let aborted = false;

    const history = messages
      .filter((m) => m.role === "user" || m.role === "assistant")
      .slice(-20)
      .map((m) => ({ role: m.role, content: m.content }));

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMsg,
          history,
          conversation_id: conversationId,
          upload_id: att?.id,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`The server returned an error (HTTP ${response.status}).`);
      }

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
            if (data.type === "conversation") {
              newConvId = data.id;
            } else if (data.type === "text") {
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
    } catch (err) {
      if (controller.signal.aborted) {
        aborted = true;
      } else if (err instanceof Error && err.message.startsWith("The server returned")) {
        accumulated = accumulated || err.message;
      } else {
        accumulated = accumulated || "Error connecting to the server. Make sure everything is running.";
      }
    } finally {
      setStreaming(false);
      setActiveTool(null);
      abortRef.current = null;

      if (accumulated) {
        const content = aborted ? accumulated + "\n\n_(stopped)_" : accumulated;
        setMessages((prev) => [...prev, ...toolMessages, { role: "assistant", content, sources }]);
      } else if (aborted) {
        setMessages((prev) => [...prev, ...toolMessages, { role: "assistant", content: "_(stopped before a reply)_" }]);
      } else if (toolMessages.length > 0) {
        setMessages((prev) => [...prev, ...toolMessages, {
          role: "assistant",
          content: "(I checked the codebase but need you to be more specific — what exactly are you looking for?)",
        }]);
      }
      setStreamContent("");

      if (newConvId) {
        setConversationId(newConvId);
        loadConversations();
      }
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
          <button className="btn" style={{ width: "100%", justifyContent: "center" }} onClick={newConversation} disabled={streaming}>
            <Plus size={12} /> New conversation
          </button>
        </div>
        <div style={{ padding: "8px 0", flex: 1, overflowY: "auto" }}>
          <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)", letterSpacing: "0.12em", padding: "8px 16px" }}>
            HISTORY
          </div>
          {conversations.length === 0 && (
            <div style={{ padding: "4px 16px", fontSize: 12, color: "var(--paper-4)" }}>
              No conversations yet.
            </div>
          )}
          {conversations.map((c) => {
            const active = c.id === conversationId;
            return (
              <div
                key={c.id}
                onClick={() => openConversation(c.id)}
                className="convo-row"
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "9px 16px",
                  cursor: streaming ? "default" : "pointer",
                  background: active ? "rgba(212,165,116,0.06)" : "transparent",
                  borderLeft: active ? "2px solid var(--amber)" : "2px solid transparent",
                }}
              >
                <MessageSquare size={13} style={{ color: active ? "var(--amber)" : "var(--paper-4)", flexShrink: 0 }} />
                <span style={{ flex: 1, fontSize: 13, color: "var(--paper-1)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.title || "Untitled"}
                </span>
                <button
                  onClick={(e) => deleteConversation(c.id, e)}
                  title="Delete conversation"
                  className="convo-del"
                  style={{ background: "transparent", border: "none", color: "var(--paper-4)", cursor: "pointer", padding: 2, lineHeight: 0 }}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            );
          })}
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
                  Ready when you are<em style={{ color: "var(--amber)", fontStyle: "italic" }}>.</em>
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
          <div style={{ maxWidth: 820, margin: "0 auto", position: "relative" }}>
            {showAttach && (
              <div
                style={{
                  position: "absolute",
                  bottom: "calc(100% + 8px)",
                  left: 0,
                  width: 320,
                  maxHeight: 260,
                  overflowY: "auto",
                  background: "var(--ink-2)",
                  border: "1px solid var(--line-strong)",
                  borderRadius: 8,
                  boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
                  zIndex: 5,
                }}
              >
                <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)", letterSpacing: "0.1em", padding: "10px 12px 6px" }}>
                  ATTACH AN UPLOAD
                </div>
                {uploads.length === 0 && (
                  <div style={{ padding: "4px 12px 12px", fontSize: 12, color: "var(--paper-4)" }}>
                    No uploads yet. Add files on the Uploads page.
                  </div>
                )}
                {uploads.map((u) => (
                  <button
                    key={u.id}
                    onClick={() => {
                      setAttachment({ id: u.id, filename: u.filename });
                      setShowAttach(false);
                    }}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      width: "100%",
                      background: "transparent",
                      border: "none",
                      borderTop: "1px solid var(--line)",
                      padding: "9px 12px",
                      cursor: "pointer",
                      textAlign: "left",
                      color: "var(--paper-1)",
                    }}
                  >
                    <FileText size={13} style={{ color: "var(--paper-4)", flexShrink: 0 }} />
                    <span style={{ flex: 1, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {u.filename}
                    </span>
                    <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>
                      {Math.max(1, Math.round(u.size_bytes / 1024))} KB
                    </span>
                  </button>
                ))}
              </div>
            )}
            <div style={{ background: "var(--ink-2)", border: "1px solid var(--line-strong)", borderRadius: 8, padding: 12 }}>
              {attachment && (
                <div
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 6,
                    background: "var(--ink-3)",
                    border: "1px solid var(--line)",
                    borderRadius: 6,
                    padding: "4px 8px",
                    marginBottom: 8,
                    fontSize: 12,
                    color: "var(--paper-1)",
                  }}
                >
                  <FileText size={12} style={{ color: "var(--amber)" }} />
                  {attachment.filename}
                  <button
                    onClick={() => setAttachment(null)}
                    style={{ background: "transparent", border: "none", color: "var(--paper-4)", cursor: "pointer", padding: 0, lineHeight: 0 }}
                  >
                    <X size={12} />
                  </button>
                </div>
              )}
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
                <button
                  className="btn btn-ghost"
                  style={{ padding: "4px 8px", fontSize: 11, color: attachment ? "var(--amber)" : undefined }}
                  onClick={toggleAttach}
                  disabled={streaming}
                >
                  <Paperclip size={11} /> Attach
                </button>
                <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
                  <span className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>⌘ + ⏎</span>
                  {streaming ? (
                    <button className="btn" onClick={stop}>
                      <Square size={11} /> Stop
                    </button>
                  ) : (
                    <button className="btn btn-primary" onClick={() => send()} disabled={!input.trim()}>
                      <Send size={12} /> Send
                    </button>
                  )}
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
    <div style={{ display: "flex", gap: 14 }} className="assistant-row">
      <YujiAvatar />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span className="font-mono" style={{ fontSize: 11, color: "var(--amber)", letterSpacing: "0.06em" }}>
            YUJI
          </span>
          <span className="assistant-copy" style={{ marginLeft: "auto" }}>
            <CopyButton text={m.content} label="Copy" />
          </span>
        </div>
        <Markdown content={m.content} />
        <Sources sources={m.sources} />
      </div>
    </div>
  );
}

function AgentThinking({ content, tool }: { content: string; tool: string | null }) {
  return (
    <div style={{ display: "flex", gap: 14 }}>
      <YujiAvatar />
      <div style={{ flex: 1, minWidth: 0 }}>
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
          <div style={{ marginTop: 4 }}>
            <Markdown content={content} />
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
