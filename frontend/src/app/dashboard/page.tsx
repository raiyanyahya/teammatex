"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, User, Key, Code2, GitBranch, Loader2 } from "lucide-react";
import Overview from "@/components/dashboard/Overview";

async function saveToApi(key: string, value: any) {
  await fetch(`/api/config/${key}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
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
          fetch("/api/repos").then((r) => r.json()),
          fetch("/api/config").then((r) => r.json()),
        ]);
        setRepos(Array.isArray(reposRes) ? reposRes.length : 0);
        if (cfgRes.config?.llm_config?.provider) setHasLLM(true);
        if (cfgRes.config?.github_token?.token) setHasGithub(true);

        const serverName = cfgRes.config?.teammate_name?.name;
        if (serverName) {
          setName(serverName);
          setNameSaved(true);
          localStorage.setItem("teammatex_name", serverName);
        } else if (!cfgRes.config?.llm_config && !cfgRes.config?.github_token) {
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
    try {
      const r = await fetch("/api/agent/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: "x=1", file_path: "t.py" }),
      });
      setLlmTestResult(r.ok);
    } catch { setLlmTestResult(false); }
    setLlmTesting(false);
  }

  async function saveGithub() {
    if (!githubToken) return;
    setGithubSaving(true);
    await saveToApi("github_token", { token: githubToken });
    await fetch("/api/integrations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: "github", credentials: { token: githubToken }, enabled: true }),
    });
    setHasGithub(true); setGithubSaving(false);
  }

  async function testGithub() {
    setGithubTesting(true);
    try {
      const r = await fetch("https://api.github.com/user", { headers: { Authorization: `Bearer ${githubToken}` } });
      setGithubTestResult(r.ok);
      if (r.ok) {
        const reposR = await fetch("https://api.github.com/user/repos?per_page=50&sort=updated", {
          headers: { Authorization: `Bearer ${githubToken}` },
        });
        if (reposR.ok) setGhRepos((await reposR.json()) || []);
      }
    } catch { setGithubTestResult(false); }
    setGithubTesting(false);
  }

  async function addRepo() {
    if (!repoUrl.trim()) return;
    setRepoAdding(true); setRepoResult("");
    try {
      const r = await fetch("/api/repos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url: repoUrl.trim() }),
      });
      const d = await r.json();
      if (r.ok) {
        setRepoResult(d.repos_added ? `Added ${d.repos_added} repos from ${d.org}` : "Repo added. Pipeline started.");
        setRepos((prev) => (d.repos_added ? prev + d.repos_added : prev + 1));
        setTimeout(() => setShowRepo(false), 2000);
      } else {
        setRepoResult(d.detail || "Failed");
      }
    } catch { setRepoResult("Error"); }
    setRepoAdding(false);
  }

  async function addGhRepo(fullName: string) {
    try {
      const r = await fetch("/api/repos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url: `https://github.com/${fullName}` }),
      });
      if (r.ok) setRepos((prev) => prev + 1);
      setGhRepos((prev) => prev.map((repo) => (repo.full_name === fullName ? { ...repo, added: true } : repo)));
    } catch {}
  }

  const done = [nameSaved, hasLLM, hasGithub, repos > 0].filter(Boolean).length;
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
        <Loader2 className="h-5 w-5 animate-spin" style={{ color: "var(--paper-3)" }} />
      </div>
    );
  }

  if (configured) {
    return <Overview name={name || "Your teammate"} onRename={renameTeammate} />;
  }

  return (
    <div className="p-10">
      <div className="page-head" style={{ padding: 0, paddingBottom: 24, marginBottom: 28 }}>
        <div>
          <h1 className="page-title">
            Let&rsquo;s <em>onboard</em> them.
          </h1>
          <div className="page-sub">
            {done < 4 ? `Step ${done} of 4` : `${name || "Your teammate"} is ready`}
          </div>
        </div>
        <div className="flex items-center gap-3" style={{ paddingBottom: 8 }}>
          <div className="h-[3px] w-40 overflow-hidden rounded-sm" style={{ background: "var(--ink-3)" }}>
            <div
              className="h-full rounded-sm transition-all"
              style={{ width: `${(done / 4) * 100}%`, background: "var(--amber)" }}
            />
          </div>
          <span className="font-mono text-[11px]" style={{ color: "var(--paper-3)" }}>{done}/4</span>
        </div>
      </div>

      <div className="max-w-xl space-y-1.5">
        <SetupRow
          done={nameSaved}
          icon={nameSaved ? Check : User}
          title={nameSaved ? name : "Name your teammate"}
        >
          {!nameSaved && (
            <div className="flex gap-1.5">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && saveName()}
                placeholder="e.g. Yuji"
                className="input"
                style={{ width: 120 }}
              />
              <button onClick={saveName} className="btn btn-primary">Save</button>
            </div>
          )}
        </SetupRow>

        <SetupRow
          done={hasLLM}
          icon={hasLLM ? Check : Key}
          title={hasLLM ? "Brain connected" : "Give them a brain"}
        >
          {!hasLLM && (
            <button onClick={() => setShowLLM(!showLLM)} className="btn btn-primary">Configure</button>
          )}
          {showLLM && (
            <div className="mt-3 w-full space-y-2 pl-[42px]">
              <select
                value={llmProvider}
                onChange={(e) => setLlmProvider(e.target.value)}
                className="input"
              >
                <option value="deepseek">DeepSeek</option>
                <option value="openai">OpenAI</option>
                <option value="anthropic">Anthropic</option>
              </select>
              <input
                type="password"
                value={llmKey}
                onChange={(e) => setLlmKey(e.target.value)}
                placeholder="sk-..."
                className="input"
              />
              <select
                value={llmModel}
                onChange={(e) => setLlmModel(e.target.value)}
                className="input"
              >
                <option value="deepseek-v4-flash">deepseek-v4-flash</option>
                <option value="deepseek-v4-pro">deepseek-v4-pro</option>
              </select>
              <div className="flex gap-2">
                <button onClick={saveLLM} disabled={llmSaving} className="btn btn-primary">
                  {llmSaving ? "..." : "Save"}
                </button>
                <button
                  onClick={testLLM}
                  disabled={llmTesting}
                  className="btn"
                  style={{
                    color:
                      llmTestResult === true
                        ? "var(--sage)"
                        : llmTestResult === false
                          ? "var(--rust)"
                          : "var(--paper-2)",
                  }}
                >
                  {llmTesting ? "..." : llmTestResult === true ? "✓ Connected" : llmTestResult === false ? "✗ Failed" : "Verify"}
                </button>
              </div>
            </div>
          )}
        </SetupRow>

        <SetupRow
          done={hasGithub}
          icon={hasGithub ? Check : Code2}
          title={hasGithub ? "GitHub connected" : "Connect GitHub"}
        >
          {!hasGithub && (
            <button onClick={() => setShowGithub(!showGithub)} className="btn btn-primary">Configure</button>
          )}
          {showGithub && (
            <div className="mt-3 w-full space-y-2 pl-[42px]">
              <input
                type="password"
                value={githubToken}
                onChange={(e) => setGithubToken(e.target.value)}
                placeholder="github_pat_..."
                className="input"
              />
              <div className="flex gap-2">
                <button onClick={saveGithub} disabled={githubSaving} className="btn btn-primary">
                  {githubSaving ? "..." : "Save"}
                </button>
                <button
                  onClick={testGithub}
                  disabled={githubTesting}
                  className="btn"
                  style={{
                    color:
                      githubTestResult === true
                        ? "var(--sage)"
                        : githubTestResult === false
                          ? "var(--rust)"
                          : "var(--paper-2)",
                  }}
                >
                  {githubTesting ? "..." : githubTestResult === true ? "✓ Connected" : githubTestResult === false ? "✗ Failed" : "Verify"}
                </button>
              </div>
              {ghRepos.length > 0 && (
                <div className="mt-2 max-h-36 space-y-0.5 overflow-y-auto">
                  {ghRepos.map((r: any) => (
                    <button
                      key={r.full_name}
                      onClick={() => addGhRepo(r.full_name)}
                      disabled={r.added}
                      className="w-full rounded px-2 py-1 text-left text-xs"
                      style={{
                        color: r.added ? "var(--sage)" : "var(--paper-1)",
                        background: r.added ? "rgba(138, 171, 142, 0.08)" : "transparent",
                      }}
                    >
                      {r.added ? "✓ " : ""}
                      {r.full_name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </SetupRow>

        <SetupRow
          done={repos > 0}
          icon={repos > 0 ? Check : GitBranch}
          title={repos > 0 ? `${repos} repos added` : "Add repositories"}
        >
          <button onClick={() => setShowRepo(!showRepo)} className="btn btn-primary">
            {repos > 0 ? "+ Add more" : "Add repo"}
          </button>
          {showRepo && (
            <div className="mt-3 w-full space-y-2 pl-[42px]">
              <input
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addRepo()}
                placeholder="github.com/owner/repo or org name"
                className="input"
              />
              <button onClick={addRepo} disabled={repoAdding || !repoUrl.trim()} className="btn btn-primary">
                {repoAdding ? "Adding..." : "Add"}
              </button>
              {repoResult && (
                <p className="font-mono text-[11px]" style={{ color: "var(--paper-3)" }}>{repoResult}</p>
              )}
            </div>
          )}
        </SetupRow>
      </div>

      {done === 4 && (
        <div className="mt-7 card max-w-xl animate-fade-in">
          <div className="card-body flex items-center gap-3">
            <div
              className="grid h-8 w-8 place-items-center rounded-md"
              style={{ background: "rgba(138, 171, 142, 0.12)", color: "var(--sage)" }}
            >
              <Check className="h-4 w-4" />
            </div>
            <div className="flex-1">
              <h3 className="font-serif text-[18px]" style={{ color: "var(--paper-0)" }}>All set</h3>
              <p className="font-mono text-[11px]" style={{ color: "var(--paper-3)" }}>
                {name || "Your teammate"} is configured.
              </p>
            </div>
            <div className="flex gap-2">
              <button onClick={() => router.push("/chat")} className="btn btn-primary">Start chatting</button>
              <button onClick={() => router.push("/onboarding")} className="btn">View pipeline</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SetupRow({
  done,
  icon: Icon,
  title,
  children,
}: {
  done: boolean;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div
      className="rounded-md border px-4 py-3.5"
      style={{
        background: done ? "var(--ink-2)" : "var(--ink-1)",
        borderColor: "var(--line)",
      }}
    >
      <div className="flex items-center gap-3 flex-wrap">
        <div
          className="grid h-7 w-7 place-items-center rounded-md"
          style={{
            background: done ? "rgba(138, 171, 142, 0.12)" : "rgba(212, 165, 116, 0.12)",
            color: done ? "var(--sage)" : "var(--amber)",
          }}
        >
          <Icon className="h-4 w-4" />
        </div>
        <div className="flex-1 min-w-0">
          <span className="text-[13px]" style={{ color: "var(--paper-0)" }}>{title}</span>
        </div>
        {children}
      </div>
    </div>
  );
}
