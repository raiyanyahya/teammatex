"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Check, Github, Loader2, Unplug } from "lucide-react";

type Model = { model: string; tier: string; note?: string };
type Providers = {
  providers: Record<string, Model[]>;
  default_provider: string;
  active: { provider: string; model: string } | null;
};
type GhVerify = {
  valid: boolean;
  configured?: boolean;
  login?: string;
  token_type?: string;
  can_push?: boolean | null;
  note?: string;
};
type Perm = { capability: string; label: string; enabled: boolean };

const SECTIONS = [
  { id: "model", label: "Model" },
  { id: "integrations", label: "Integrations" },
  { id: "permissions", label: "Permissions" },
  { id: "persona", label: "Persona" },
  { id: "updates", label: "Updates" },
];

async function getJSON<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(`/api${path}`);
    return r.ok ? r.json() : null;
  } catch {
    return null;
  }
}
async function putConfig(key: string, value: any) {
  await fetch(`/api/config/${key}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
}

export default function AdminPage() {
  const [section, setSection] = useState<string>("model");

  const [prov, setProv] = useState<Providers | null>(null);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [storedKey, setStoredKey] = useState("");
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmSaved, setLlmSaved] = useState(false);

  const [gh, setGh] = useState<GhVerify | null>(null);
  const [ghLoading, setGhLoading] = useState(true);
  const [githubToken, setGithubToken] = useState("");
  const [githubSaving, setGithubSaving] = useState(false);

  const [perms, setPerms] = useState<Perm[]>([]);
  const [persona, setPersona] = useState("senior");

  async function loadLLM() {
    const p = await getJSON<Providers>("/config/llm/providers");
    setProv(p);
    if (p?.active) {
      setProvider(p.active.provider);
      setModel(p.active.model);
    }
    const cfg = await getJSON<{ config: Record<string, any> }>("/config");
    const llm = cfg?.config?.llm_config;
    if (llm?.api_key) setStoredKey(llm.api_key);
    if (llm?.provider && !p?.active) {
      setProvider(llm.provider);
      setModel(llm.model || "");
    }
  }
  async function loadGh() {
    setGhLoading(true);
    try {
      const r = await fetch("/api/config/github_token/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      setGh(r.ok ? await r.json() : null);
    } catch {
      setGh(null);
    }
    setGhLoading(false);
  }
  async function loadPerms() {
    const data = await getJSON<{ permissions: Perm[] }>("/permissions");
    if (data) setPerms(data.permissions);
  }
  async function togglePermission(capability: string, enabled: boolean) {
    setPerms((ps) => ps.map((p) => (p.capability === capability ? { ...p, enabled } : p)));
    await fetch(`/api/permissions/${capability}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
  }
  async function loadPersona() {
    const data = await getJSON<{ value: { persona?: string } | null }>("/config/persona");
    if (data?.value?.persona) setPersona(data.value.persona);
  }
  async function savePersona(key: string) {
    setPersona(key);
    await putConfig("persona", { persona: key });
  }

  useEffect(() => {
    loadLLM();
    loadGh();
    loadPerms();
    loadPersona();
  }, []);

  const providerKeys = prov ? Object.keys(prov.providers) : [];
  const providerModels = (prov && provider && prov.providers[provider]) || [];
  const reuseKey = !!prov?.active && provider === prov.active.provider && !!storedKey;
  const canSaveLLM = !!provider && !!model && (!!apiKey || reuseKey);

  async function saveLLM() {
    const key = apiKey || (reuseKey ? storedKey : "");
    if (!provider || !model || !key) return;
    setLlmSaving(true);
    await putConfig("llm_config", { provider, model, api_key: key });
    setStoredKey(key);
    setApiKey("");
    await loadLLM();
    setLlmSaving(false);
    setLlmSaved(true);
    setTimeout(() => setLlmSaved(false), 2000);
  }

  async function saveGithub() {
    if (!githubToken) return;
    setGithubSaving(true);
    await putConfig("github_token", { token: githubToken });
    await fetch("/api/integrations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: "github", credentials: { token: githubToken }, enabled: true }),
    });
    setGithubToken("");
    await loadGh();
    setGithubSaving(false);
  }
  async function disconnectGithub() {
    setGithubSaving(true);
    await fetch("/api/config/github_token", { method: "DELETE" });
    await fetch("/api/integrations/github", { method: "DELETE" });
    await loadGh();
    setGithubSaving(false);
  }

  return (
    <div style={{ padding: 40, maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ marginBottom: 28 }}>
        <h1 className="page-title">
          Settings<em>.</em>
        </h1>
        <div className="page-sub">Configure the agent · self-hosted</div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 32 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {SECTIONS.map((s) => (
            <div
              key={s.id}
              onClick={() => setSection(s.id)}
              style={{
                padding: "8px 12px",
                cursor: "pointer",
                borderRadius: 4,
                color: section === s.id ? "var(--paper-0)" : "var(--paper-2)",
                background: section === s.id ? "var(--ink-2)" : "transparent",
                fontSize: 13,
                borderLeft: section === s.id ? "2px solid var(--amber)" : "2px solid transparent",
                marginLeft: section === s.id ? 0 : 2,
              }}
            >
              {s.label}
            </div>
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {section === "model" && (
            <Section title="Model" desc="The provider your teammate thinks with.">
              <Field label="Provider">
                <select
                  value={provider}
                  onChange={(e) => {
                    setProvider(e.target.value);
                    setModel("");
                    setLlmSaved(false);
                  }}
                  className="input"
                >
                  <option value="">Select provider…</option>
                  {providerKeys.map((p) => (
                    <option key={p} value={p}>
                      {p}
                      {p === prov?.default_provider ? " (default)" : ""}
                    </option>
                  ))}
                </select>
              </Field>

              {provider && (
                <>
                  <Field label="Model" hint="Bigger model = better reasoning, slower + costlier">
                    <select
                      value={model}
                      onChange={(e) => {
                        setModel(e.target.value);
                        setLlmSaved(false);
                      }}
                      className="input"
                    >
                      <option value="">Select model…</option>
                      {providerModels.map((m) => (
                        <option key={m.model} value={m.model}>
                          {m.model} — {m.tier}
                        </option>
                      ))}
                    </select>
                    {model && providerModels.find((m) => m.model === model)?.note && (
                      <div className="font-mono" style={{ fontSize: 10, marginTop: 6, color: "var(--paper-4)" }}>
                        {providerModels.find((m) => m.model === model)?.note}
                      </div>
                    )}
                  </Field>
                  <Field label="API key" hint={reuseKey ? "Saved key in use — leave blank to keep it" : "Plaintext from the provider"}>
                    <input
                      type="password"
                      value={apiKey}
                      onChange={(e) => {
                        setApiKey(e.target.value);
                        setLlmSaved(false);
                      }}
                      placeholder={reuseKey ? "Using saved key" : "sk-…"}
                      className="input"
                    />
                  </Field>
                  <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, alignItems: "center" }}>
                    {prov?.active && (
                      <span className="tag tag-sage" style={{ fontSize: 10 }}>
                        Active: {prov.active.provider} · {prov.active.model}
                      </span>
                    )}
                    <button onClick={saveLLM} disabled={!canSaveLLM || llmSaving} className="btn btn-primary">
                      {llmSaving ? <Loader2 size={12} className="animate-spin" /> : llmSaved ? <Check size={12} /> : null}
                      {llmSaving ? "Saving…" : llmSaved ? "Saved" : "Save"}
                    </button>
                  </div>
                </>
              )}

              <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)" }}>
                Fallback order: Anthropic → OpenAI → DeepSeek → Groq → Ollama
              </div>
            </Section>
          )}

          {section === "integrations" && (
            <>
              <Section title="GitHub" desc="Required to clone repos and open PRs.">
                {ghLoading ? (
                  <div className="font-mono" style={{ fontSize: 12, color: "var(--paper-3)", display: "inline-flex", alignItems: "center", gap: 8 }}>
                    <Loader2 size={12} className="animate-spin" /> Checking…
                  </div>
                ) : gh?.valid ? (
                  <>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        padding: "12px 14px",
                        border: "1px solid rgba(138, 171, 142, 0.3)",
                        background: "rgba(138, 171, 142, 0.06)",
                        borderRadius: 6,
                      }}
                    >
                      <div>
                        <div style={{ fontSize: 13, color: "var(--paper-0)" }}>
                          Connected as <span className="font-mono" style={{ color: "var(--sage)" }}>{gh.login}</span>
                          {gh.token_type && (
                            <span className="font-mono" style={{ marginLeft: 8, fontSize: 10, color: "var(--paper-4)" }}>
                              {gh.token_type}
                            </span>
                          )}
                        </div>
                        <div className="font-mono" style={{ fontSize: 10, marginTop: 4, color: gh.can_push === false ? "var(--amber)" : "var(--paper-4)" }}>
                          {gh.can_push === true
                            ? "Push access: yes — can open PRs."
                            : gh.can_push === false
                              ? "Push access: no — read-only token; pushes/PRs will 403."
                              : gh.note}
                        </div>
                      </div>
                      <button onClick={disconnectGithub} disabled={githubSaving} className="btn btn-ghost">
                        <Unplug size={11} /> Disconnect
                      </button>
                    </div>
                    <Field label="Replace token" hint="Leave blank to keep the existing token.">
                      <div style={{ display: "flex", gap: 8 }}>
                        <input
                          type="password"
                          value={githubToken}
                          onChange={(e) => setGithubToken(e.target.value)}
                          placeholder="github_pat_…"
                          className="input"
                          style={{ fontFamily: "var(--mono)" }}
                        />
                        <button onClick={saveGithub} disabled={!githubToken || githubSaving} className="btn btn-primary">
                          Save
                        </button>
                      </div>
                    </Field>
                  </>
                ) : (
                  <>
                    {gh?.note && (
                      <div className="font-mono" style={{ fontSize: 11, color: "var(--amber)" }}>
                        {gh.note}
                      </div>
                    )}
                    <Field label="GitHub token" hint="Needs Contents + Pull requests (write) to open PRs">
                      <div style={{ display: "flex", gap: 8 }}>
                        <input
                          type="password"
                          value={githubToken}
                          onChange={(e) => setGithubToken(e.target.value)}
                          placeholder="github_pat_…"
                          className="input"
                          style={{ fontFamily: "var(--mono)" }}
                        />
                        <button onClick={saveGithub} disabled={!githubToken || githubSaving} className="btn btn-primary">
                          {githubSaving ? <Loader2 size={12} className="animate-spin" /> : <Github size={12} />} Connect
                        </button>
                      </div>
                    </Field>
                  </>
                )}
              </Section>

              <Section title="Other integrations" desc="Slack and Jira are not wired up yet — these inputs are disabled until the integrations are built.">
                <NotWired>Slack and Jira aren&rsquo;t wired up yet — these inputs are disabled until the integrations are built.</NotWired>
                <Field label="Slack Bot Token">
                  <input type="password" disabled placeholder="xoxb-…" className="input" />
                </Field>
                <Field label="Jira API Token">
                  <input type="password" disabled placeholder="Token" className="input" />
                </Field>
              </Section>
            </>
          )}

          {section === "permissions" && (
            <Section title="Permissions" desc="What the agent is allowed to do without human approval. Disabling a capability blocks its tools at runtime.">
              {perms.length === 0 ? (
                <div className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)" }}>
                  Loading…
                </div>
              ) : (
                perms.map((p) => (
                  <div
                    key={p.capability}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      padding: "8px 0",
                      borderBottom: "1px dashed var(--line)",
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, color: "var(--paper-0)" }}>{p.label}</div>
                      <div className="font-mono" style={{ fontSize: 10, marginTop: 2, color: "var(--paper-4)" }}>
                        capability · {p.capability}
                      </div>
                    </div>
                    <Toggle value={p.enabled} onChange={(v) => togglePermission(p.capability, v)} />
                  </div>
                ))
              )}
            </Section>
          )}

          {section === "persona" && (
            <Section title="Persona" desc="How the agent works. The choice is woven into its system prompt — shifts tone and emphasis without changing what it's allowed to do.">
              {[
                { key: "senior", label: "Senior", desc: "Thorough and pedagogical" },
                { key: "junior", label: "Junior", desc: "Enthusiastic, asks for clarification" },
                { key: "reviewer", label: "Reviewer", desc: "Strict about types and tests" },
                { key: "pragmatic", label: "Pragmatic", desc: "Favors shipping over perfection" },
                { key: "architect", label: "Architect", desc: "Thinks in systems and diagrams" },
              ].map((p) => {
                const active = persona === p.key;
                return (
                  <div
                    key={p.key}
                    onClick={() => savePersona(p.key)}
                    style={{
                      padding: "10px 14px",
                      border: "1px solid " + (active ? "var(--amber-dim)" : "var(--line)"),
                      background: active ? "rgba(212, 165, 116, 0.06)" : "transparent",
                      borderRadius: 6,
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                    }}
                  >
                    <span
                      style={{
                        width: 16,
                        height: 16,
                        borderRadius: "50%",
                        border: "1.5px solid " + (active ? "var(--amber)" : "var(--line-strong)"),
                        display: "grid",
                        placeItems: "center",
                      }}
                    >
                      {active && <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--amber)" }} />}
                    </span>
                    <span style={{ fontSize: 13, color: "var(--paper-0)" }}>{p.label}</span>
                    <span className="font-mono" style={{ fontSize: 11, color: "var(--paper-4)", marginLeft: "auto" }}>
                      {p.desc}
                    </span>
                  </div>
                );
              })}
            </Section>
          )}

          {section === "updates" && (
            <Section title="Updates" desc="How fresh the agent's view of your repos stays.">
              <NotWired>Auto-sync currently runs on a fixed schedule. Configurable scheduling and GitHub-webhook triggers aren&rsquo;t wired up yet.</NotWired>
              <div style={{ display: "flex", flexDirection: "column", gap: 10, opacity: 0.6, pointerEvents: "none" }}>
                <div
                  style={{
                    padding: "10px 14px",
                    border: "1px solid var(--line)",
                    background: "var(--ink-2)",
                    borderRadius: 6,
                  }}
                >
                  <div style={{ fontSize: 13, color: "var(--paper-0)" }}>Git pull on schedule</div>
                  <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)", marginTop: 4 }}>
                    every 6 hours
                  </div>
                </div>
                <div
                  style={{
                    padding: "10px 14px",
                    border: "1px solid var(--line)",
                    borderRadius: 6,
                  }}
                >
                  <div style={{ fontSize: 13, color: "var(--paper-0)" }}>GitHub webhooks</div>
                  <div className="font-mono" style={{ fontSize: 10, color: "var(--paper-4)", marginTop: 4 }}>
                    react to push/PR events
                  </div>
                </div>
              </div>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({ title, desc, children }: { title: string; desc?: string; children: React.ReactNode }) {
  return (
    <div className="card" style={{ padding: 24 }}>
      <div style={{ marginBottom: 18, paddingBottom: 14, borderBottom: "1px solid var(--line)" }}>
        <div style={{ fontFamily: "var(--serif)", fontSize: 24, color: "var(--paper-0)" }}>{title}</div>
        {desc && (
          <div className="font-mono" style={{ fontSize: 12, marginTop: 4, color: "var(--paper-4)" }}>
            {desc}
          </div>
        )}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>{children}</div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 24, alignItems: "start" }}>
      <div>
        <div style={{ fontSize: 13, color: "var(--paper-0)" }}>{label}</div>
        {hint && (
          <div className="font-mono" style={{ fontSize: 10, marginTop: 4, color: "var(--paper-4)", letterSpacing: "0.04em" }}>
            {hint}
          </div>
        )}
      </div>
      <div>{children}</div>
    </div>
  );
}

function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!value)}
      style={{
        width: 36,
        height: 20,
        borderRadius: 10,
        background: value ? "var(--amber)" : "var(--ink-3)",
        border: "1px solid " + (value ? "var(--amber)" : "var(--line-strong)"),
        cursor: "pointer",
        position: "relative",
        padding: 0,
      }}
    >
      <span
        style={{
          position: "absolute",
          top: 1,
          left: value ? 17 : 1,
          width: 16,
          height: 16,
          borderRadius: "50%",
          background: value ? "var(--ink-0)" : "var(--paper-1)",
          transition: "left 0.15s",
        }}
      />
    </button>
  );
}

function NotWired({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 8,
        padding: "10px 12px",
        border: "1px solid rgba(212, 165, 116, 0.3)",
        background: "rgba(212, 165, 116, 0.06)",
        borderRadius: 6,
        fontSize: 11,
        color: "var(--amber)",
      }}
    >
      <AlertTriangle size={12} style={{ marginTop: 2, flexShrink: 0 }} />
      <span>{children}</span>
    </div>
  );
}
