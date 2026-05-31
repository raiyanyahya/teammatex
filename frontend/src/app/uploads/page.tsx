"use client";

import { useEffect, useRef, useState } from "react";
import { Upload as UploadIcon, Download, Trash2, FileText } from "lucide-react";
import { api } from "@/lib/api";

type Up = {
  id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  created_at: string | null;
};

function fmtSize(n: number): string {
  if (n >= 1048576) return `${(n / 1048576).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

export default function UploadsPage() {
  const [files, setFiles] = useState<Up[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      setFiles(await api.get<Up[]>("/uploads"));
    } catch {}
  }
  useEffect(() => {
    load();
  }, []);

  async function upload(file: globalThis.File) {
    setBusy(true);
    setErr("");
    const fd = new FormData();
    fd.append("file", file);
    // Multipart: don't set Content-Type (browser sets the boundary). The api
    // client forces JSON, so use raw fetch with the Bearer token.
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    try {
      const res = await fetch("/api/uploads", {
        method: "POST",
        body: fd,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        setErr(j.detail || `Upload failed (${res.status})`);
      } else {
        await load();
      }
    } catch {
      setErr("Upload failed");
    }
    setBusy(false);
  }

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) await upload(f);
    if (inputRef.current) inputRef.current.value = "";
  }
  async function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) await upload(f);
  }
  async function remove(id: string) {
    try {
      await api.delete(`/uploads/${id}`);
      await load();
    } catch {}
  }

  return (
    <div className="p-10">
      <h1 className="mb-6 font-serif text-[28px] leading-none" style={{ color: "var(--paper-0)" }}>
        Uploads
      </h1>

      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        className="mb-6 flex flex-col items-center justify-center gap-3 rounded-[6px] border border-dashed px-6 py-10 text-center"
        style={{ borderColor: "var(--line)", background: "var(--ink-1)" }}
      >
        <UploadIcon size={20} style={{ color: "var(--amber)" }} />
        <div className="text-[13px]" style={{ color: "var(--paper-2)" }}>Drag a file here, or</div>
        <button className="btn btn-primary" disabled={busy} onClick={() => inputRef.current?.click()}>
          {busy ? "Uploading…" : "Choose file"}
        </button>
        <input ref={inputRef} type="file" className="hidden" onChange={onPick} />
        <div className="font-mono text-[11px]" style={{ color: "var(--paper-4)" }}>
          Stored privately. Max 25 MB. Files are not executed.
        </div>
        {err && <div className="text-[12px]" style={{ color: "#e8a0a0" }}>{err}</div>}
      </div>

      {files.length === 0 ? (
        <div className="font-mono text-[12px]" style={{ color: "var(--paper-4)" }}>No uploads yet.</div>
      ) : (
        <div className="flex flex-col gap-2">
          {files.map((f) => (
            <div
              key={f.id}
              className="flex items-center gap-3 rounded-[4px] px-4 py-3"
              style={{ background: "var(--ink-1)", border: "1px solid var(--line)" }}
            >
              <FileText size={14} style={{ color: "var(--paper-3)" }} />
              <div className="min-w-0 flex-1">
                <div className="truncate font-mono text-[13px]" style={{ color: "var(--paper-0)" }}>{f.filename}</div>
                <div className="font-mono text-[11px]" style={{ color: "var(--paper-4)" }}>
                  {fmtSize(f.size_bytes)} · {f.content_type || "unknown"} · {f.created_at?.slice(0, 10)}
                </div>
              </div>
              <a href={`/api/uploads/${f.id}/download`} download className="btn" title="Download">
                <Download size={13} />
              </a>
              <button className="btn" title="Delete" onClick={() => remove(f.id)}>
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
