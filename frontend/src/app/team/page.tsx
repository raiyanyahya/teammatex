"use client";

import { useEffect, useState } from "react";
import { Users, Plus } from "lucide-react";
import { api } from "@/lib/api";

export default function TeamPage() {
  const [members, setMembers] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [github, setGithub] = useState("");

  async function load() {
    try {
      const data = await api.get<any[]>("/auth/users");
      setMembers(data);
    } catch {}
  }

  useEffect(() => { load(); }, []);

  async function addMember(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !name) return;
    try {
      await api.post("/auth/register", { email, name, password: "changeme123456" });
      setName(""); setEmail(""); setGithub("");
      await load();
    } catch {}
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-lg font-semibold text-[#cccccc]">Team</h1>
        <p className="mt-0.5 text-xs text-[#6a6a6e]">People working alongside your teammate</p>
      </div>

      <form onSubmit={addMember} className="mb-6 flex gap-2 max-w-xl">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="input flex-1 text-xs" />
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" type="email" className="input flex-1 text-xs" />
        <input value={github} onChange={(e) => setGithub(e.target.value)} placeholder="GitHub (optional)" className="input text-xs w-40" />
        <button type="submit" className="btn-primary text-xs"><Plus className="h-3.5 w-3.5" /> Add</button>
      </form>

      <div className="space-y-1 max-w-xl">
        {members.map((m: any) => (
          <div key={m.id} className="panel flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-md bg-[#2a2a30] text-xs font-medium text-[#6a6a6e]">
                {m.name?.[0]?.toUpperCase() || "?"}
              </div>
              <div>
                <p className="text-sm text-[#cccccc]">{m.name}</p>
                <p className="text-[11px] text-[#6a6a6e]">{m.email}</p>
              </div>
            </div>
            {m.github_username && (
              <span className="text-[11px] text-[#5a5a5e]">{m.github_username}</span>
            )}
          </div>
        ))}
        {members.length === 0 && (
          <p className="py-8 text-center text-xs text-[#5a5a5e]">No team members added yet.</p>
        )}
      </div>
    </div>
  );
}
