"use client";

import { useEffect, useState } from "react";
import { Key, Webhook, Shield, Bot, Check, Loader2, RefreshCw, Github, Unplug, AlertTriangle } from "lucide-react";

const TABS = [
  { id: "llm", label: "LLM", icon: Key },
  { id: "integrations", label: "Integrations", icon: Webhook },
  { id: "update", label: "Updates", icon: RefreshCw },
  { id: "permissions", label: "Permissions", icon: Shield },
  { id: "persona", label: "Persona", icon: Bot },
];

type Model = { model: string; tier: string; note?: string };
type Providers = {
  providers: Record<string, Model[]>;
  default_provider: string;
  active: { provider: string; model: string } | null;
};
type GhVerify = {
  valid: boolean; configured?: boolean; login?: string;
  token_type?: string; can_push?: boolean | null; note?: string;
};
type Perm = { capability: string; label: string; enabled: boolean };

async function getJSON<T>(path: string): Promise<T | null> {
  try { const r = await fetch(`/api${path}`); return r.ok ? r.json() : null; } catch { return null; }
}
async function putConfig(key: string, value: any) {
  await fetch(`/api/config/${key}`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
}

function NotWired({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 flex items-start gap-2 rounded-md border border-[#3a3010] bg-[#2a2410] px-3 py-2">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#c0a040]" />
      <p className="text-[11px] text-[#c0a040]">{children}</p>
    </div>
  );
}

export default function AdminPage() {
  const [tab, setTab] = useState("llm");

  // LLM
  const [prov, setProv] = useState<Providers | null>(null);
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [storedKey, setStoredKey] = useState("");
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmSaved, setLlmSaved] = useState(false);

  // GitHub
  const [gh, setGh] = useState<GhVerify | null>(null);
  const [ghLoading, setGhLoading] = useState(true);
  const [githubToken, setGithubToken] = useState("");
  const [githubSaving, setGithubSaving] = useState(false);

  // Permissions
  const [perms, setPerms] = useState<Perm[]>([]);

  // Persona
  const [persona, setPersona] = useState("senior");

  async function loadLLM() {
    const p = await getJSON<Providers>("/config/llm/providers");
    setProv(p);
    if (p?.active) { setProvider(p.active.provider); setModel(p.active.model); }
    const cfg = await getJSON<{ config: Record<string, any> }>("/config");
    const llm = cfg?.config?.llm_config;
    if (llm?.api_key) setStoredKey(llm.api_key);
    if (llm?.provider && !p?.active) { setProvider(llm.provider); setModel(llm.model || ""); }
  }
  async function loadGh() {
    setGhLoading(true);
    try {
      const r = await fetch("/api/config/github_token/verify", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      setGh(r.ok ? await r.json() : null);
    } catch { setGh(null); }
    setGhLoading(false);
  }
  async function loadPerms() {
    const data = await getJSON<{ permissions: Perm[] }>("/permissions");
    if (data) setPerms(data.permissions);
  }
  async function togglePermission(capability: string, enabled: boolean) {
    setPerms((ps) => ps.map((p) => (p.capability === capability ? { ...p, enabled } : p)));
    await fetch(`/api/permissions/${capability}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
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
  useEffect(() => { loadLLM(); loadGh(); loadPerms(); loadPersona(); }, []);

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
      method: "POST", headers: { "Content-Type": "application/json" },
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
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-lg font-semibold text-[#cccccc]">Settings</h1>
        <p className="mt-0.5 text-xs text-[#6a6a6e]">Configure providers and integrations</p>
      </div>

      <div className="flex gap-8">
        <div className="w-44 space-y-0.5">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)} className={`flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-xs transition-colors ${tab === t.id ? "bg-[#2a2a30] text-[#cccccc]" : "text-[#6a6a6e] hover:text-[#cccccc] hover:bg-[#25252b]"}`}>
              <t.icon className="h-3.5 w-3.5" /> {t.label}
            </button>
          ))}
        </div>

        <div className="flex-1 max-w-lg">
          {tab === "llm" && (
            <div className="panel space-y-4 p-5">
              <div className="flex items-center justify-between">
                <p className="text-xs text-[#6a6a6e]">The provider your teammate thinks with.</p>
                {prov?.active ? (
                  <span className="badge border-[#2a4a3a] bg-[#1c2a22] text-[#6aaa8a]">
                    Active: {prov.active.provider} · {prov.active.model}
                  </span>
                ) : (
                  <span className="badge">Not configured</span>
                )}
              </div>

              <select value={provider} onChange={(e) => { setProvider(e.target.value); setModel(""); setLlmSaved(false); }} className="input">
                <option value="">Select provider...</option>
                {providerKeys.map((p) => <option key={p} value={p}>{p}{p === prov?.default_provider ? " (default)" : ""}</option>)}
              </select>

              {provider && (
                <>
                  <select value={model} onChange={(e) => { setModel(e.target.value); setLlmSaved(false); }} className="input text-xs">
                    <option value="">Select model...</option>
                    {providerModels.map((m) => <option key={m.model} value={m.model}>{m.model} — {m.tier}</option>)}
                  </select>
                  {model && providerModels.find((m) => m.model === model)?.note && (
                    <p className="text-[10px] text-[#6a6a6e]">{providerModels.find((m) => m.model === model)?.note}</p>
                  )}
                  <input
                    type="password" value={apiKey} onChange={(e) => { setApiKey(e.target.value); setLlmSaved(false); }}
                    placeholder={reuseKey ? "Using saved key — leave blank to keep it" : "API key (sk-...)"}
                    className="input text-xs"
                  />
                  <button onClick={saveLLM} disabled={!canSaveLLM || llmSaving} className="btn-primary text-xs disabled:opacity-50">
                    {llmSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : llmSaved ? <Check className="h-3.5 w-3.5" /> : null}
                    {llmSaving ? "Saving..." : llmSaved ? "Saved" : "Save configuration"}
                  </button>
                </>
              )}
              <p className="text-[10px] text-[#5a5a5e]">Fallback order: Anthropic → OpenAI → DeepSeek → Groq → Ollama</p>
            </div>
          )}

          {tab === "integrations" && (
            <div className="panel space-y-5 p-5">
              <div>
                <label className="mb-2 flex items-center gap-1.5 text-xs font-medium text-[#8a8a8e]"><Github className="h-3.5 w-3.5" /> GitHub</label>
                {ghLoading ? (
                  <div className="flex items-center gap-2 text-xs text-[#6a6a6e]"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Checking…</div>
                ) : gh?.valid ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between rounded-md border border-[#2a4a3a] bg-[#1c2a22] px-3 py-2">
                      <span className="text-xs text-[#cccccc]">
                        Connected as <span className="font-mono text-[#6aaa8a]">{gh.login}</span>
                        {gh.token_type ? <span className="ml-2 text-[10px] text-[#6a6a6e]">{gh.token_type}</span> : null}
                      </span>
                      <button onClick={disconnectGithub} disabled={githubSaving} className="btn-ghost text-[11px]">
                        <Unplug className="h-3 w-3" /> Disconnect
                      </button>
                    </div>
                    <p className={`text-[10px] ${gh.can_push === false ? "text-[#e0a060]" : "text-[#6a6a6e]"}`}>
                      {gh.can_push === true ? "Push access: yes — can open PRs."
                        : gh.can_push === false ? "Push access: no — this is read-only, so pushes/PRs will 403."
                        : gh.note}
                    </p>
                    <details className="text-[10px] text-[#6a6a6e]">
                      <summary className="cursor-pointer">Replace token</summary>
                      <div className="mt-2 flex gap-2">
                        <input type="password" value={githubToken} onChange={(e) => setGithubToken(e.target.value)} placeholder="github_pat_..." className="input text-xs" />
                        <button onClick={saveGithub} disabled={!githubToken || githubSaving} className="btn-primary text-xs disabled:opacity-50">Save</button>
                      </div>
                    </details>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {gh?.note && <p className="text-[10px] text-[#e0a060]">{gh.note}</p>}
                    <div className="flex gap-2">
                      <input type="password" value={githubToken} onChange={(e) => setGithubToken(e.target.value)} placeholder="github_pat_..." className="input text-xs" />
                      <button onClick={saveGithub} disabled={!githubToken || githubSaving} className="btn-primary text-xs disabled:opacity-50">
                        {githubSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null} Connect
                      </button>
                    </div>
                    <p className="text-[10px] text-[#6a6a6e]">Create at github.com/settings/tokens — needs Contents + Pull requests write to open PRs.</p>
                  </div>
                )}
              </div>

              <div className="border-t border-[#2a2a2e] pt-4">
                <NotWired>Slack and Jira aren&apos;t wired up yet — these inputs are disabled until the integrations are built.</NotWired>
                <label className="mb-1.5 block text-xs font-medium text-[#5a5a5e]">Slack Bot Token</label>
                <input type="password" disabled placeholder="xoxb-..." className="input text-xs opacity-50" />
                <label className="mb-1.5 mt-3 block text-xs font-medium text-[#5a5a5e]">Jira API Token</label>
                <input type="password" disabled placeholder="Token" className="input text-xs opacity-50" />
              </div>
            </div>
          )}

          {tab === "update" && (
            <div className="panel p-5">
              <NotWired>Auto-sync currently runs on a fixed schedule. Configurable scheduling and GitHub-webhook triggers aren&apos;t wired up yet.</NotWired>
              <div className="space-y-3 opacity-50 pointer-events-none">
                <label className="flex items-center gap-3 rounded bg-[#25252b] px-3 py-2.5">
                  <input type="radio" name="update" defaultChecked disabled className="h-3.5 w-3.5 accent-[#264f78]" />
                  <span className="text-sm text-[#cccccc]">Git pull on schedule</span>
                </label>
                <label className="flex items-center gap-3 rounded px-3 py-2.5">
                  <input type="radio" name="update" disabled className="h-3.5 w-3.5 accent-[#264f78]" />
                  <span className="text-sm text-[#cccccc]">GitHub webhooks</span>
                </label>
              </div>
            </div>
          )}

          {tab === "permissions" && (
            <div className="panel p-5">
              <p className="mb-4 text-xs text-[#6a6a6e]">
                What your teammate is allowed to do. Disabling a capability blocks its tools
                (read/write code, PRs); the agent gets a permission error if it tries.
              </p>
              <div className="space-y-1">
                {perms.map((p) => (
                  <label key={p.capability} className="flex cursor-pointer items-center justify-between rounded px-3 py-2.5 hover:bg-[#25252b]">
                    <span className="text-sm text-[#cccccc]">{p.label}</span>
                    <input
                      type="checkbox" checked={p.enabled}
                      onChange={(e) => togglePermission(p.capability, e.target.checked)}
                      className="h-3.5 w-3.5 accent-[#264f78]"
                    />
                  </label>
                ))}
                {perms.length === 0 && (
                  <p className="px-3 py-6 text-center text-xs text-[#5a5a5e]">Loading…</p>
                )}
              </div>
            </div>
          )}

          {tab === "persona" && (
            <div className="panel p-5">
              <p className="mb-4 text-xs text-[#6a6a6e]">
                How your teammate works. The choice is woven into its system prompt — it
                shifts tone and emphasis without changing what it&apos;s allowed to do.
              </p>
              <div className="space-y-1">
                {[
                  { key: "senior", label: "Senior", desc: "Thorough and pedagogical" },
                  { key: "junior", label: "Junior", desc: "Enthusiastic, asks for clarification" },
                  { key: "reviewer", label: "Reviewer", desc: "Strict about types and tests" },
                  { key: "pragmatic", label: "Pragmatic", desc: "Favors shipping over perfection" },
                  { key: "architect", label: "Architect", desc: "Thinks in systems and diagrams" },
                ].map((p) => (
                  <label key={p.key} className="flex cursor-pointer items-center gap-3 rounded px-3 py-2.5 hover:bg-[#25252b]">
                    <input
                      type="radio" name="persona" checked={persona === p.key}
                      onChange={() => savePersona(p.key)}
                      className="h-3.5 w-3.5 accent-[#264f78]"
                    />
                    <div><span className="text-sm text-[#cccccc]">{p.label}</span><span className="ml-2 text-[11px] text-[#6a6a6e]">{p.desc}</span></div>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
