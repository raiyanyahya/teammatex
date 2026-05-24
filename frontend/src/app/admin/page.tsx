"use client";

import { useState } from "react";
import { Key, Webhook, Shield, Bot, Check, Loader2, RefreshCw, GitBranch } from "lucide-react";

const TABS = [
  { id: "llm", label: "LLM", icon: Key },
  { id: "integrations", label: "Integrations", icon: Webhook },
  { id: "update", label: "Updates", icon: RefreshCw },
  { id: "permissions", label: "Permissions", icon: Shield },
  { id: "persona", label: "Persona", icon: Bot },
];

const PROVIDERS = [
  { key: "deepseek", label: "DeepSeek", placeholder: "sk-...", models: ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat"] },
  { key: "openai", label: "OpenAI", placeholder: "sk-...", models: ["gpt-4o", "gpt-4o-mini"] },
  { key: "anthropic", label: "Anthropic", placeholder: "sk-ant-...", models: ["claude-3-5-sonnet-20241022"] },
  { key: "groq", label: "Groq", placeholder: "gsk_...", models: ["llama-3.1-70b-versatile"] },
  { key: "ollama", label: "Ollama (local)", placeholder: "http://localhost:11434", models: ["llama3.1:8b"] },
];

async function saveToApi(key: string, value: any) {
  await fetch(`/api/config/${key}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
}

export default function AdminPage() {
  const [tab, setTab] = useState("llm");
  const [provider, setProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [githubToken, setGithubToken] = useState("");
  const [githubSaving, setGithubSaving] = useState(false);
  const [githubSaved, setGithubSaved] = useState(false);

  async function handleSaveLLM() {
    if (!provider || !apiKey) return;
    setSaving(true);
    await saveToApi("llm_config", { provider, api_key: apiKey, model: model || "default" });
    setSaved(true);
    setSaving(false);
    setTimeout(() => setSaved(false), 2000);
  }

  async function handleSaveGithub() {
    if (!githubToken) return;
    setGithubSaving(true);
    await saveToApi("github_token", { token: githubToken });
    await fetch("/api/integrations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: "github", credentials: { token: githubToken }, enabled: true }),
    });
    setGithubSaved(true);
    setGithubSaving(false);
    setTimeout(() => setGithubSaved(false), 2000);
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
            <div className="panel p-5 space-y-4">
              <p className="text-xs text-[#6a6a6e]">Connect a provider so your teammate can think.</p>
              <select value={provider} onChange={(e) => { setProvider(e.target.value); setModel(""); setSaved(false); }} className="input">
                <option value="">Select provider...</option>
                {PROVIDERS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
              </select>
              {provider && (
                <>
                  <input type="password" value={apiKey} onChange={(e) => { setApiKey(e.target.value); setSaved(false); }} placeholder={PROVIDERS.find(p => p.key === provider)?.placeholder} className="input text-xs" />
                  <select value={model} onChange={(e) => { setModel(e.target.value); setSaved(false); }} className="input text-xs">
                    <option value="">Select model...</option>
                    {PROVIDERS.find(p => p.key === provider)?.models.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <button onClick={handleSaveLLM} disabled={!provider || !apiKey || saving} className="btn-primary text-xs">
                    {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : saved ? <Check className="h-3.5 w-3.5" /> : null}
                    {saving ? "Saving..." : saved ? "Saved" : "Save configuration"}
                  </button>
                </>
              )}
              <p className="text-[10px] text-[#5a5a5e]">Fallback: Anthropic → OpenAI → DeepSeek → Groq → Ollama</p>
            </div>
          )}

          {tab === "integrations" && (
            <div className="panel p-5 space-y-4">
              <div>
                <label className="block mb-1.5 text-xs font-medium text-[#8a8a8e]">GitHub Token</label>
                <input type="password" value={githubToken} onChange={(e) => { setGithubToken(e.target.value); setGithubSaved(false); }} placeholder="github_pat_..." className="input text-xs" />
                <button onClick={handleSaveGithub} disabled={!githubToken || githubSaving} className="btn-primary text-xs mt-2">
                  {githubSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : githubSaved ? <Check className="h-3.5 w-3.5" /> : null}
                  {githubSaving ? "Saving..." : githubSaved ? "Saved" : "Save token"}
                </button>
                <p className="text-[10px] text-[#6a6a6e] mt-1">Create at github.com/settings/tokens — needs repo scope.</p>
              </div>
              <div>
                <label className="block mb-1.5 text-xs font-medium text-[#8a8a8e]">Slack Bot Token</label>
                <input type="password" placeholder="xoxb-..." className="input text-xs" />
              </div>
              <div>
                <label className="block mb-1.5 text-xs font-medium text-[#8a8a8e]">Jira API Token</label>
                <input type="password" placeholder="Token" className="input text-xs" />
              </div>
            </div>
          )}

          {tab === "update" && (
            <div className="panel p-5 space-y-4">
              <p className="text-xs text-[#6a6a6e]">How should the teammate stay up to date with your repositories?</p>
              <div className="space-y-3">
                <label className="flex items-center gap-3 rounded px-3 py-2.5 bg-[#25252b] cursor-pointer">
                  <input type="radio" name="update" defaultChecked className="h-3.5 w-3.5 accent-[#264f78]" />
                  <div>
                    <span className="text-sm text-[#cccccc]">Git pull on schedule</span>
                    <span className="ml-2 text-[11px] text-[#6a6a6e]">git pull + rebase to keep repos synced</span>
                  </div>
                </label>
                <div className="pl-10 flex items-center gap-2">
                  <span className="text-xs text-[#6a6a6e]">Every</span>
                  <input type="number" defaultValue={2} min={1} max={60} className="bg-[#1e1e24] border border-[#2a2a2e] rounded px-2 py-1 text-xs text-[#cccccc] w-16 outline-none" />
                  <span className="text-xs text-[#6a6a6e]">minutes</span>
                </div>
                <label className="flex items-center gap-3 rounded px-3 py-2.5 cursor-pointer">
                  <input type="radio" name="update" className="h-3.5 w-3.5 accent-[#264f78]" />
                  <div>
                    <span className="text-sm text-[#cccccc]">GitHub webhooks</span>
                    <span className="ml-2 text-[11px] text-[#6a6a6e]">Push events trigger instant re-sync</span>
                    <span className="ml-2 text-[10px] text-[#5a5a5e]">(coming soon)</span>
                  </div>
                </label>
              </div>
              <button className="btn-primary text-xs mt-2">Save update settings</button>
            </div>
          )}

          {tab === "permissions" && (
            <div className="panel p-5 space-y-1">
              {[
                { key: "read_code", label: "Read code", desc: "Read and analyze repository code" },
                { key: "write_code", label: "Write code", desc: "Create branches and commits" },
                { key: "create_pr", label: "Create PRs", desc: "Open pull requests" },
                { key: "merge_pr", label: "Merge PRs", desc: "Merge approved PRs" },
                { key: "autonomous", label: "Autonomous mode", desc: "Act without per-action approval" },
              ].map((p) => (
                <label key={p.key} className="flex items-center justify-between rounded px-3 py-2.5 hover:bg-[#25252b] cursor-pointer">
                  <div><span className="text-sm text-[#cccccc]">{p.label}</span><span className="ml-2 text-[11px] text-[#6a6a6e]">{p.desc}</span></div>
                  <input type="checkbox" defaultChecked={p.key !== "merge_pr"} className="h-3.5 w-3.5 accent-[#264f78]" />
                </label>
              ))}
            </div>
          )}

          {tab === "persona" && (
            <div className="panel p-5 space-y-1">
              {[
                { key: "senior", label: "Senior", desc: "Thorough and pedagogical" },
                { key: "junior", label: "Junior", desc: "Enthusiastic, asks for clarification" },
                { key: "reviewer", label: "Reviewer", desc: "Strict about types and tests" },
                { key: "pragmatic", label: "Pragmatic", desc: "Favors shipping over perfection" },
                { key: "architect", label: "Architect", desc: "Thinks in systems and diagrams" },
              ].map((p) => (
                <label key={p.key} className={`flex items-center gap-3 rounded px-3 py-2.5 cursor-pointer hover:bg-[#25252b] ${p.key === "senior" ? "bg-[#25252b]" : ""}`}>
                  <input type="radio" name="persona" defaultChecked={p.key === "senior"} className="h-3.5 w-3.5 accent-[#264f78]" />
                  <div><span className="text-sm text-[#cccccc]">{p.label}</span><span className="ml-2 text-[11px] text-[#6a6a6e]">{p.desc}</span></div>
                </label>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
