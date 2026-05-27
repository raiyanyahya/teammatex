"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, User, Key, Code2, GitBranch, Loader2, Wifi, WifiOff } from "lucide-react";
import Overview from "@/components/dashboard/Overview";

async function saveToApi(key: string, value: any) {
  await fetch(`/api/config/${key}`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key, value }),
  });
}

export default function DashboardPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [nameSaved, setNameSaved] = useState(false);
  const [repos, setRepos] = useState(0);
  const [loading, setLoading] = useState(true);
  const [hasLLM, setHasLLM] = useState(false);
  const [hasGithub, setHasGithub] = useState(false);
  
  // Inline forms
  const [showLLM, setShowLLM] = useState(false);
  const [showGithub, setShowGithub] = useState(false);
  const [showRepo, setShowRepo] = useState(false);
  const [llmProvider, setLlmProvider] = useState("deepseek");
  const [llmKey, setLlmKey] = useState("");
  const [llmModel, setLlmModel] = useState("deepseek-v4-flash");
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmTesting, setLlmTesting] = useState(false);
  const [llmTestResult, setLlmTestResult] = useState<null | boolean>(null);
  const [githubToken, setGithubToken] = useState("");
  const [githubSaving, setGithubSaving] = useState(false);
  const [githubTesting, setGithubTesting] = useState(false);
  const [githubTestResult, setGithubTestResult] = useState<null | boolean>(null);
  const [ghRepos, setGhRepos] = useState<any[]>([]);
  const [repoUrl, setRepoUrl] = useState("");
  const [repoAdding, setRepoAdding] = useState(false);
  const [repoResult, setRepoResult] = useState("");

  useEffect(() => {
    const stored = localStorage.getItem("teammatex_name");
    if (stored) { setName(stored); setNameSaved(true); }
    
    async function load() {
      try {
        const [reposRes, cfgRes] = await Promise.all([
          fetch("/api/repos").then(r => r.json()),
          fetch("/api/config").then(r => r.json()),
        ]);
        setRepos(Array.isArray(reposRes) ? reposRes.length : 0);
        if (cfgRes.config?.llm_config?.provider) setHasLLM(true);
        if (cfgRes.config?.github_token?.token) setHasGithub(true);

        // Server is the source of truth for the name (localStorage is just a cache),
        // so it doesn't show "unset" on a fresh browser.
        const serverName = cfgRes.config?.teammate_name?.name;
        if (serverName) {
          setName(serverName);
          setNameSaved(true);
          localStorage.setItem("teammatex_name", serverName);
        } else if (!cfgRes.config?.llm_config && !cfgRes.config?.github_token) {
          // Fresh install (no config at all) — clear any stale cached name.
          localStorage.removeItem("teammatex_name");
          setName("");
          setNameSaved(false);
        }
      } catch {}
      setLoading(false);
    }
    load();
  }, []);

  function saveName() {
    if (!name.trim()) return;
    localStorage.setItem("teammatex_name", name.trim());
    saveToApi("teammate_name", { name: name.trim() });
    setNameSaved(true);
  }

  async function saveLLM() {
    if (!llmProvider || !llmKey) return;
    setLlmSaving(true);
    await saveToApi("llm_config", { provider: llmProvider, api_key: llmKey, model: llmModel });
    setHasLLM(true); setLlmSaving(false); setShowLLM(false);
  }

  async function testLLM() {
    setLlmTesting(true);
    try { const r = await fetch("/api/agent/validate", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({code:"x=1",file_path:"t.py"}) }); setLlmTestResult(r.ok); } catch { setLlmTestResult(false); }
    setLlmTesting(false);
  }

  async function saveGithub() {
    if (!githubToken) return;
    setGithubSaving(true);
    await saveToApi("github_token", { token: githubToken });
    await fetch("/api/integrations", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({provider:"github", credentials:{token:githubToken}, enabled:true}) });
    setHasGithub(true); setGithubSaving(false);
  }

  async function testGithub() {
    setGithubTesting(true);
    try {
      const r = await fetch("https://api.github.com/user", { headers: { Authorization: `Bearer ${githubToken}` } });
      setGithubTestResult(r.ok);
      if (r.ok) {
        const reposR = await fetch("https://api.github.com/user/repos?per_page=50&sort=updated", { headers: { Authorization: `Bearer ${githubToken}` } });
        if (reposR.ok) setGhRepos((await reposR.json()) || []);
      }
    } catch { setGithubTestResult(false); }
    setGithubTesting(false);
  }

  async function addRepo() {
    if (!repoUrl.trim()) return;
    setRepoAdding(true); setRepoResult("");
    try {
      const r = await fetch("/api/repos", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({github_url: repoUrl.trim()}) });
      const d = await r.json();
      if (r.ok) {
        setRepoResult(d.repos_added ? `Added ${d.repos_added} repos from ${d.org}` : "Repo added. Pipeline started.");
        setRepos(prev => d.repos_added ? prev + d.repos_added : prev + 1);
        setTimeout(() => setShowRepo(false), 2000);
      } else {
        setRepoResult(d.detail || "Failed");
      }
    } catch { setRepoResult("Error"); }
    setRepoAdding(false);
  }

  async function addGhRepo(fullName: string) {
    try {
      const r = await fetch("/api/repos", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({github_url: `https://github.com/${fullName}`}) });
      if (r.ok) setRepos(prev => prev + 1);
      setGhRepos(prev => prev.map(repo => repo.full_name === fullName ? {...repo, added: true} : repo));
    } catch {}
  }

  const done = [nameSaved, hasLLM, hasGithub, repos > 0].filter(Boolean).length;

  // "Set up" = the functional essentials. Naming is cosmetic (editable from the
  // overview), so it no longer keeps the page stuck on the checklist.
  const configured = hasLLM && hasGithub && repos > 0;

  async function renameTeammate(n: string) {
    const v = n.trim();
    if (!v) return;
    await saveToApi("teammate_name", { name: v });
    localStorage.setItem("teammatex_name", v);
    setName(v);
    setNameSaved(true);
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-[#6a6a6e]" />
      </div>
    );
  }

  if (configured) {
    return <Overview name={name} onRename={renameTeammate} />;
  }

  return (
    <div className="p-8">
      <div className="mb-10">
        <h1 className="text-lg font-semibold text-[#cccccc]">Dashboard</h1>
        <p className="mt-0.5 text-xs text-[#6a6a6e]">{done < 4 ? "Get started" : `${name || "Your teammate"} is ready`}</p>
      </div>

      <div className="mb-6 flex items-center gap-3">
        <div className="h-1 flex-1 rounded-sm bg-[#2a2a30] overflow-hidden">
          <div className="h-1 rounded-sm bg-[#264f78] transition-all" style={{ width: `${(done/4)*100}%` }} />
        </div>
        <span className="text-xs text-[#6a6a6e] font-mono">{done}/4</span>
      </div>

      <div className="space-y-1 max-w-xl">
        {/* Step 1: Name */}
        <div className={`rounded-md px-4 py-3.5 border ${nameSaved ? "bg-[#2a2a30] border-[#2a2a2e]" : "bg-[#222229] border-[#2a2a2e]"}`}>
          <div className="flex items-center gap-3">
            <div className={`flex h-7 w-7 items-center justify-center rounded-md ${nameSaved ? "bg-[#2a3a2a] text-[#6aaa6a]" : "bg-[#223040] text-[#7a9ec8]"}`}>
              {nameSaved ? <Check className="h-4 w-4" /> : <User className="h-4 w-4" />}
            </div>
            <div className="flex-1">
              <span className="text-sm text-[#cccccc]">
                {nameSaved ? name : "Name your teammate"}
              </span>
            </div>
            {!nameSaved ? (
              <div className="flex gap-1.5">
                <input value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && saveName()} placeholder="e.g. Alex" className="bg-[#1e1e24] border border-[#2a2a2e] rounded px-2 py-1 text-xs text-[#cccccc] w-24 outline-none" />
                <button onClick={saveName} className="bg-[#264f78] text-white rounded px-2 py-1 text-xs">Save</button>
              </div>
            ) : (
              <span className="text-xs text-[#6a6a6e]">Done</span>
            )}
          </div>
        </div>

        {/* Step 2: LLM */}
        <div className={`rounded-md px-4 py-3.5 border ${hasLLM ? "bg-[#2a2a30] border-[#2a2a2e]" : "bg-[#222229] border-[#2a2a2e]"}`}>
          <div className="flex items-center gap-3">
            <div className={`flex h-7 w-7 items-center justify-center rounded-md ${hasLLM ? "bg-[#2a3a2a] text-[#6aaa6a]" : "bg-[#223040] text-[#7a9ec8]"}`}>
              {hasLLM ? <Check className="h-4 w-4" /> : <Key className="h-4 w-4" />}
            </div>
            <div className="flex-1">
              <span className="text-sm text-[#cccccc]">{hasLLM ? "Brain connected" : "Give them a brain"}</span>
            </div>
            {!hasLLM ? (
              <button onClick={() => setShowLLM(!showLLM)} className="bg-[#264f78] text-white rounded px-2 py-1 text-xs">Configure</button>
            ) : (
              <span className="text-xs text-[#6a6a6e]">Done</span>
            )}
          </div>
          {showLLM && (
            <div className="mt-3 pl-10 space-y-2">
              <select value={llmProvider} onChange={(e) => setLlmProvider(e.target.value)} className="bg-[#1e1e24] border border-[#2a2a2e] rounded px-2 py-1 text-xs text-[#cccccc] w-full">
                <option value="deepseek">DeepSeek</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
              </select>
              <input type="password" value={llmKey} onChange={(e) => setLlmKey(e.target.value)} placeholder="sk-..." className="bg-[#1e1e24] border border-[#2a2a2e] rounded px-2 py-1 text-xs text-[#cccccc] w-full" />
              <select value={llmModel} onChange={(e) => setLlmModel(e.target.value)} className="bg-[#1e1e24] border border-[#2a2a2e] rounded px-2 py-1 text-xs text-[#cccccc] w-full">
                <option value="deepseek-v4-flash">deepseek-v4-flash</option>
                <option value="deepseek-v4-pro">deepseek-v4-pro</option>
              </select>
              <div className="flex gap-2">
                <button onClick={saveLLM} disabled={llmSaving} className="bg-[#264f78] text-white rounded px-2 py-1 text-xs">{llmSaving ? "..." : "Save"}</button>
                <button onClick={testLLM} disabled={llmTesting} className={`rounded px-2 py-1 text-xs border ${llmTestResult === true ? "border-[#3a6a3a] text-[#6aaa6a]" : llmTestResult === false ? "border-[#4a2020] text-[#e06060]" : "border-[#2a2a2e] text-[#8a8a8e]"}`}>
                  {llmTesting ? "..." : llmTestResult === true ? "✓ Connected" : llmTestResult === false ? "✗ Failed" : "Verify"}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Step 3: GitHub */}
        <div className={`rounded-md px-4 py-3.5 border ${hasGithub ? "bg-[#2a2a30] border-[#2a2a2e]" : "bg-[#222229] border-[#2a2a2e]"}`}>
          <div className="flex items-center gap-3">
            <div className={`flex h-7 w-7 items-center justify-center rounded-md ${hasGithub ? "bg-[#2a3a2a] text-[#6aaa6a]" : "bg-[#223040] text-[#7a9ec8]"}`}>
              {hasGithub ? <Check className="h-4 w-4" /> : <Code2 className="h-4 w-4" />}
            </div>
            <div className="flex-1">
              <span className="text-sm text-[#cccccc]">{hasGithub ? "GitHub connected" : "Connect GitHub"}</span>
            </div>
            {!hasGithub ? (
              <button onClick={() => setShowGithub(!showGithub)} className="bg-[#264f78] text-white rounded px-2 py-1 text-xs">Configure</button>
            ) : (
              <span className="text-xs text-[#6a6a6e]">Done</span>
            )}
          </div>
          {showGithub && (
            <div className="mt-3 pl-10 space-y-2">
              <input type="password" value={githubToken} onChange={(e) => setGithubToken(e.target.value)} placeholder="github_pat_..." className="bg-[#1e1e24] border border-[#2a2a2e] rounded px-2 py-1 text-xs text-[#cccccc] w-full" />
              <div className="flex gap-2">
                <button onClick={saveGithub} disabled={githubSaving} className="bg-[#264f78] text-white rounded px-2 py-1 text-xs">{githubSaving ? "..." : "Save"}</button>
                <button onClick={testGithub} disabled={githubTesting} className={`rounded px-2 py-1 text-xs border ${githubTestResult === true ? "border-[#3a6a3a] text-[#6aaa6a]" : githubTestResult === false ? "border-[#4a2020] text-[#e06060]" : "border-[#2a2a2e] text-[#8a8a8e]"}`}>
                  {githubTesting ? "..." : githubTestResult === true ? "✓ Connected" : githubTestResult === false ? "✗ Failed" : "Verify"}
                </button>
              </div>
              {ghRepos.length > 0 && (
                <div className="max-h-36 overflow-y-auto space-y-0.5 mt-2">
                  {ghRepos.map((r: any) => (
                    <button key={r.full_name} onClick={() => addGhRepo(r.full_name)} disabled={r.added}
                      className={`w-full text-left rounded px-2 py-1 text-xs ${r.added ? "text-[#6aaa6a] bg-[#2a3a2a]" : "text-[#cccccc] hover:bg-[#25252b]"}`}>
                      {r.added ? "✓ " : ""}{r.full_name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Step 4: Repos */}
        <div className={`rounded-md px-4 py-3.5 border ${repos > 0 ? "bg-[#2a2a30] border-[#2a2a2e]" : "bg-[#222229] border-[#2a2a2e]"}`}>
          <div className="flex items-center gap-3">
            <div className={`flex h-7 w-7 items-center justify-center rounded-md ${repos > 0 ? "bg-[#2a3a2a] text-[#6aaa6a]" : "bg-[#223040] text-[#7a9ec8]"}`}>
              {repos > 0 ? <Check className="h-4 w-4" /> : <GitBranch className="h-4 w-4" />}
            </div>
            <div className="flex-1">
              <span className="text-sm text-[#cccccc]">{repos > 0 ? `${repos} repos added` : "Add repositories"}</span>
            </div>
            <button onClick={() => setShowRepo(!showRepo)} className="bg-[#264f78] text-white rounded px-2 py-1 text-xs">{repos > 0 ? "+ Add more" : "Add repo"}</button>
          </div>
          {showRepo && (
            <div className="mt-3 pl-10 space-y-2">
              <input value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addRepo()} placeholder="github.com/owner/repo or org name" className="bg-[#1e1e24] border border-[#2a2a2e] rounded px-2 py-1 text-xs text-[#cccccc] w-full" />
              <button onClick={addRepo} disabled={repoAdding || !repoUrl.trim()} className="bg-[#264f78] text-white rounded px-2 py-1 text-xs">{repoAdding ? "Adding..." : "Add"}</button>
              {repoResult && <p className="text-xs text-[#6a6a6e]">{repoResult}</p>}
            </div>
          )}
        </div>
      </div>

      {done === 4 && (
        <div className="mt-8 panel p-6 max-w-xl animate-fade-in">
          <div className="flex items-center gap-3 mb-4">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[#2a3a2a]"><Check className="h-4 w-4 text-[#6aaa6a]" /></div>
            <div><h3 className="text-sm font-semibold text-[#cccccc]">All set</h3><p className="text-xs text-[#6a6a6e]">{name || "Your teammate"} is configured.</p></div>
          </div>
          <div className="flex gap-2">
            <button onClick={() => router.push("/chat")} className="btn-primary text-xs">Start chatting</button>
            <button onClick={() => router.push("/onboarding")} className="btn-secondary text-xs">View onboarding pipeline</button>
          </div>
        </div>
      )}

      {/* Optional: Slack & Jira */}
      {done === 4 && (
        <div className="mt-4 panel p-4 max-w-xl">
          <p className="text-xs font-medium text-[#8a8a8e] mb-3">Optional integrations</p>
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <input type="password" placeholder="Slack bot token (xoxb-...)" className="bg-[#1e1e24] border border-[#2a2a2e] rounded px-2 py-1 text-xs text-[#cccccc] flex-1" />
              <button className="bg-[#264f78] text-white rounded px-2 py-1 text-xs">Save</button>
            </div>
            <div className="flex items-center gap-2">
              <input type="password" placeholder="Jira API token" className="bg-[#1e1e24] border border-[#2a2a2e] rounded px-2 py-1 text-xs text-[#cccccc] flex-1" />
              <button className="bg-[#264f78] text-white rounded px-2 py-1 text-xs">Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
