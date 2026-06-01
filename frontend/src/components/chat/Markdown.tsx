"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { codeToHtml } from "shiki";
import { Check, Copy } from "lucide-react";

// Shiki highlights asynchronously; cache results so re-renders during streaming
// don't re-highlight the same block over and over.
const _cache = new Map<string, string>();

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1400);
        } catch {}
      }}
      title="Copy"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        background: "transparent",
        border: "1px solid var(--line)",
        borderRadius: 4,
        color: copied ? "var(--sage)" : "var(--paper-4)",
        padding: "2px 6px",
        fontSize: 10,
        fontFamily: "var(--mono)",
        cursor: "pointer",
      }}
    >
      {copied ? <Check size={11} /> : <Copy size={11} />}
      {label ? (copied ? "Copied" : label) : null}
    </button>
  );
}

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const key = `${lang}::${code}`;
  const [html, setHtml] = useState<string | null>(() => _cache.get(key) ?? null);

  useEffect(() => {
    let alive = true;
    if (_cache.has(key)) {
      setHtml(_cache.get(key)!);
      return;
    }
    codeToHtml(code, { lang, theme: "github-dark" })
      .catch(() => codeToHtml(code, { lang: "text", theme: "github-dark" }))
      .then((out) => {
        if (!alive) return;
        _cache.set(key, out);
        setHtml(out);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [key, code, lang]);

  return (
    <div style={{ position: "relative", margin: "10px 0" }}>
      <div style={{ position: "absolute", top: 6, right: 6, zIndex: 1 }}>
        <CopyButton text={code} />
      </div>
      {html ? (
        <div className="md-code" dangerouslySetInnerHTML={{ __html: html }} />
      ) : (
        <pre className="md-code md-code-plain">
          <code>{code}</code>
        </pre>
      )}
    </div>
  );
}

export default function Markdown({ content }: { content: string }) {
  return (
    <div className="md-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          // Block code is wrapped in <pre><code>; pass <pre> through so our
          // CodeBlock (which renders its own <pre>) isn't nested inside one.
          pre: ({ children }) => <>{children}</>,
          code({ className, children, ...rest }) {
            const text = String(children ?? "");
            const match = /language-(\w+)/.exec(className || "");
            const isBlock = Boolean(match) || text.includes("\n");
            if (isBlock) {
              return <CodeBlock code={text.replace(/\n$/, "")} lang={match?.[1] || "text"} />;
            }
            return (
              <code className="md-inline" {...rest}>
                {children}
              </code>
            );
          },
          a: ({ children, ...props }) => (
            <a {...props} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export { CopyButton };
