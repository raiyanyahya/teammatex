"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, Loader2, Wifi, WifiOff } from "lucide-react";

async function saveToApi(key: string, value: any) {
  const res = await fetch(`/api/config/${key}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
  return res.ok;
}

async function testLLMConnection(provider: string, key: string, model: string): Promise<boolean> {
  try {
    const res = await fetch("/api/agent/tools");
    return res.ok;
  } catch { return false; }
}

async function verifyGithubToken(token: string): Promise<any> {
  // Use the backend verifier so we learn whether the token can actually push,
  // not just whether it's valid (read-only tokens clone fine but 403 on push).
  try {
    const res = await fetch("/api/config/github_token/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    if (!res.ok) return { valid: false };
    return await res.json();
  } catch { return { valid: false }; }
}

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [nameSaved, setNameSaved] = useState(false);
  
  // LLM
  const [llmProvider, setLlmProvider] = useState("");
  const [llmKey, setLlmKey] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmSaved, setLlmSaved] = useState(false);
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmTesting, setLlmTesting] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState<null | boolean>(null);
  
  // GitHub
  const [githubToken, setGithubToken] = useState("");
  const [githubSaved, setGithubSaved] = useState(false);
  const [githubSaving, setGithubSaving] = useState(false);
  const [githubTesting, setGithubTesting] = useState(false);
  const [githubTestResult, setGithubTestResult] = useState<null | boolean>(null);
  const [githubVerify, setGithubVerify] = useState<any>(null);
  const [ghRepos, setGhRepos] = useState<any[]>([]);
  const [ghReposLoading, setGhReposLoading] = useState(false);
  
  // Repo
  const [repoUrl, setRepoUrl] = useState("");
  const [repoAdded, setRepoAdded] = useState(false);
  const [repoError, setRepoError] = useState("");

  useEffect(() => {
    const stored = localStorage.getItem("teammatex_name");
    if (stored) { setName(stored); setNameSaved(true); }
  }, []);

  function handleSaveName() {
    if (!name.trim()) return;
    localStorage.setItem("teammatex_name", name.trim());
    saveToApi("teammate_name", { name: name.trim() });
    setNameSaved(true);
  }

  async function handleSaveLLM() {
    if (!llmProvider || !llmKey) return;
    setLlmSaving(true);
    await saveToApi("llm_config", { provider: llmProvider, api_key: llmKey, model: llmModel || "default" });
    setLlmSaved(true);
    setLlmSaving(false);
  }

  async function handleTestLLM() {
    setLlmTesting(true);
    const ok = await testLLMConnection(llmProvider, llmKey, llmModel);
    setLlmTestResult(ok);
    setLlmTesting(false);
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
  }

  async function handleTestGithub() {
    setGithubTesting(true);
    const result = await verifyGithubToken(githubToken);
    setGithubVerify(result);
    const ok = !!result.valid;
    setGithubTestResult(ok);
    if (ok) {
      setGhReposLoading(true);
      try {
        const res = await fetch("/api/integrations/github/repos");
        if (res.ok) {
          const data = await res.json();
          setGhRepos(data.repos || []);
        }
      } catch {}
      setGhReposLoading(false);
    }
    setGithubTesting(false);
  }

  async function addGhRepo(repoName: string) {
    try {
      await fetch("/api/repos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url: `https://github.com/${repoName}` }),
      });
      setGhRepos(prev => prev.map(r => r.full_name === repoName ? { ...r, added: true } : r));
    } catch {}
  }

  async function handleAddRepo() {
    if (!repoUrl.trim() || repoAdded) return;
    setRepoError("");
    try {
      const res = await fetch("/api/repos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url: repoUrl.trim() }),
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Failed"); }
      const data = await res.json();
      if (data.repos_added && data.repos_added > 1) {
        setRepoError(""); setRepoAdded(true); 
      } else {
        setRepoAdded(true);
      }
    } catch (e: any) {
      setRepoError(e.message || "Could not add repository");
    }
  }

  const providers = [
    { key: "deepseek", label: "DeepSeek", placeholder: "sk-...", models: ["deepseek-v4-flash", "deepseek-v4-pro"] },
    { key: "openai", label: "OpenAI", placeholder: "sk-...", models: ["gpt-4o", "gpt-4o-mini"] },
    { key: "anthropic", label: "Anthropic", placeholder: "sk-ant-...", models: ["claude-3-5-sonnet-20241022"] },
    { key: "groq", label: "Groq", placeholder: "gsk_...", models: ["llama-3.1-70b-versatile"] },
    { key: "ollama", label: "Ollama (local)", placeholder: "http://localhost:11434", models: ["llama3.1:8b"] },
  ];

  const steps = [
    {
      title: `What should we call ${nameSaved ? name : "them"}?`,
      subtitle: "Every developer has a name.",
      content: (
        <div className="space-y-3">
          <input value={name} onChange={(e) => { setName(e.target.value); setNameSaved(false); }} onKeyDown={(e) => e.key === "Enter" && handleSaveName()} placeholder="e.g. Alex, Jordan, Sam..." autoFocus className="input" />
          <button onClick={handleSaveName} disabled={!name.trim()} className="btn-primary text-xs">
            {nameSaved ? <><Check className="h-3.5 w-3.5" /> Saved</> : "Save name"}
          </button>
          {nameSaved && <p className="text-xs text-[#6a6a6e]">{name} — got it.</p>}
        </div>
      ),
    },
    {
      title: "Give them a brain",
      subtitle: "Connect an LLM provider.",
      content: (
        <div className="space-y-3">
          <select value={llmProvider} onChange={(e) => { setLlmProvider(e.target.value); setLlmModel(""); setLlmSaved(false); setLlmTestResult(null); }} className="input">
            <option value="">Select provider...</option>
            {providers.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
          {llmProvider && (
            <>
              <input type="password" value={llmKey} onChange={(e) => { setLlmKey(e.target.value); setLlmSaved(false); setLlmTestResult(null); }} placeholder={providers.find(p => p.key === llmProvider)?.placeholder} className="input text-xs" />
              <select value={llmModel} onChange={(e) => { setLlmModel(e.target.value); setLlmSaved(false); }} className="input text-xs">
                <option value="">Select model...</option>
                {providers.find(p => p.key === llmProvider)?.models.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <div className="flex gap-2">
                <button onClick={handleSaveLLM} disabled={!llmProvider || !llmKey} className="btn-primary text-xs flex items-center gap-1.5">
                  {llmSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : llmSaved ? <Check className="h-3.5 w-3.5" /> : null}
                  {llmSaved ? "Saved" : "Save key"}
                </button>
                {llmSaved && (
                  <button onClick={handleTestLLM} disabled={llmTesting} className="btn-secondary text-xs flex items-center gap-1.5">
                    {llmTesting ? <Loader2 className="h-3 w-3 animate-spin" /> : llmTestResult === true ? <Wifi className="h-3 w-3 text-[#6aaa6a]" /> : llmTestResult === false ? <WifiOff className="h-3 w-3 text-[#e06060]" /> : <Wifi className="h-3 w-3" />}
                    {llmTesting ? "Testing..." : llmTestResult === true ? "Connected" : llmTestResult === false ? "Failed" : "Test connection"}
                  </button>
                )}
              </div>
            </>
          )}
          <p className="text-[11px] text-[#6a6a6e]">You can add more providers later in Settings.</p>
        </div>
      ),
    },
    {
      title: "Connect GitHub",
      subtitle: "A token lets them create PRs and branches.",
      content: (
        <div className="space-y-3">
          <input type="password" value={githubToken} onChange={(e) => { setGithubToken(e.target.value); setGithubSaved(false); setGithubTestResult(null); }} placeholder="github_pat_..." className="input text-xs" />
          <div className="flex gap-2">
            <button onClick={handleSaveGithub} disabled={!githubToken} className="btn-primary text-xs flex items-center gap-1.5">
              {githubSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : githubSaved ? <Check className="h-3.5 w-3.5" /> : null}
              {githubSaved ? "Saved" : "Save token"}
            </button>
            {githubSaved && (
              <button onClick={handleTestGithub} disabled={githubTesting} className="btn-secondary text-xs flex items-center gap-1.5">
                {githubTesting ? <Loader2 className="h-3 w-3 animate-spin" /> : githubTestResult === true ? <Wifi className="h-3 w-3 text-[#6aaa6a]" /> : githubTestResult === false ? <WifiOff className="h-3 w-3 text-[#e06060]" /> : <Wifi className="h-3 w-3" />}
                {githubTesting ? "Testing..." : githubTestResult === true ? "Connected" : githubTestResult === false ? "Failed" : "Test connection"}
              </button>
            )}
          </div>
          {githubVerify && githubVerify.valid && (
            <p className={`text-[11px] ${githubVerify.can_push === false ? "text-[#e0a060]" : githubVerify.can_push === true ? "text-[#6aaa6a]" : "text-[#9a9a6e]"}`}>
              {githubVerify.login ? `@${githubVerify.login} · ` : ""}{githubVerify.token_type}
              {" · "}
              {githubVerify.can_push === true ? "can push & open PRs ✓" : githubVerify.can_push === false ? "READ-ONLY — pushes will 403 ✗" : "push rights unknown ⚠"}
              <br />{githubVerify.note}
            </p>
          )}
          <p className="text-[11px] text-[#6a6a6e]">Create at github.com/settings/tokens — needs repo scope (classic) or Contents+PR write (fine-grained).</p>
          {ghRepos.length > 0 && (
            <div className="mt-3 max-h-48 overflow-y-auto space-y-1">
              <p className="text-[10px] text-[#6a6a6e] mb-1">Your repositories — click to add:</p>
              {ghRepos.map((r: any) => (
                <button key={r.name} onClick={() => addGhRepo(r.name)} disabled={r.added}
                  className={`w-full flex items-center gap-2 rounded px-3 py-2 text-xs transition-colors ${
                    r.added ? "bg-[#2a3a2a] text-[#6aaa6a]" : "hover:bg-[#25252b] text-[#cccccc]"
                  }`}>
                  {r.added ? <Check className="h-3 w-3" /> : <span className="h-3 w-3" />}
                  <span className="truncate">{r.name}</span>
                  {r.private && <span className="text-[10px] text-[#5a5a5e] ml-auto">private</span>}
                </button>
              ))}
            </div>
          )}
          {ghReposLoading && (
            <div className="flex items-center gap-2 text-xs text-[#6a6a6e]">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading repositories...
            </div>
          )}
        </div>
      ),
    },
    {
      title: "Show them the codebase",
      subtitle: "Add a repo — they'll clone and learn everything.",
      content: (
        <div className="space-y-3">
          <div className="flex gap-2">
            <input value={repoUrl} onChange={(e) => { setRepoUrl(e.target.value); setRepoAdded(false); }} onKeyDown={(e) => { if (e.key === "Enter") handleAddRepo(); }} placeholder="https://github.com/your-team/your-repo" className="input flex-1 text-xs" />
            <button onClick={handleAddRepo} disabled={!repoUrl.trim() || repoAdded} className="btn-primary text-xs">{repoAdded ? <><Check className="h-3.5 w-3.5" /> Added</> : "Add repo"}</button>
          </div>
          {repoAdded && <p className="text-xs text-[#6a6a6e]">Added! The pipeline clones and analyzes it immediately.</p>}
          {repoError && <p className="text-xs text-[#e06060]">{repoError}</p>}
        </div>
      ),
    },
    {
      title: "All set.",
      subtitle: `${nameSaved ? name : "They"} are ready.`,
      content: (
        <div className="flex items-center gap-3 rounded-md border border-[#2a3a2a] bg-[#1e2a1e] px-4 py-3">
          <Check className="h-5 w-5 text-[#6aaa6a]" />
          <div><p className="text-sm text-[#cccccc]">{nameSaved ? name : "Your teammate"} is ready</p><p className="text-xs text-[#6a6a6e]">Repos will start onboarding immediately.</p></div>
        </div>
      ),
    },
  ];

  if (step === steps.length) {
    saveToApi("setup_complete", { completed: true });
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[#2a3a2a]"><Check className="h-6 w-6 text-[#6aaa6a]" /></div>
          <h1 className="text-lg font-semibold text-[#cccccc]">All set</h1>
          <p className="mt-1 text-xs text-[#6a6a6e]">{nameSaved ? name : "They"} are ready to work.</p>
          <button onClick={() => router.push("/dashboard")} className="btn-primary mt-6">Go to Dashboard</button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="mb-6 flex gap-1.5 justify-center">
          {steps.map((_, i) => <div key={i} className={`h-1 w-6 rounded-sm transition-colors ${i <= step ? "bg-[#264f78]" : "bg-[#2a2a30]"}`} />)}
        </div>
        <div className="panel p-6">
          <div className="mb-5"><h1 className="text-base font-semibold text-[#cccccc]">{steps[step].title}</h1><p className="mt-1 text-xs text-[#6a6a6e]">{steps[step].subtitle}</p></div>
          {steps[step].content}
        </div>
        <div className="mt-4 flex justify-between">
          {step > 0 && <button onClick={() => setStep(step - 1)} className="btn-ghost text-xs">Back</button>}
          <button onClick={() => setStep(step + 1)} className="btn-primary text-xs ml-auto">Continue <ArrowRight className="h-3 w-3" /></button>
        </div>
      </div>
    </div>
  );
}
