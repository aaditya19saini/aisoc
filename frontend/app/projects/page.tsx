"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, Outbound, Project, timeAgo } from "@/lib/api";

type Draft = { project: string; to: string; subject: string; body: string; autoSend: boolean };

const statusTone = (s = "") =>
  /block/i.test(s) ? "text-urgent" : /risk/i.test(s) ? "text-high" : /done|complete/i.test(s) ? "text-muted" : "text-normal";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [history, setHistory] = useState<Outbound[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [instructions, setInstructions] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadHistory = () => api<Outbound[]>("/api/outbound").then(setHistory).catch(() => {});
  useEffect(() => {
    api<Project[]>("/api/projects").then(setProjects).catch((e) => setError(e.message));
    loadHistory();
  }, []);

  async function generate(p: Project) {
    setBusy(`gen:${p.project}`);
    setError("");
    setNotice("");
    try {
      const r = await api<{ to: string; subject: string; body: string }>("/api/projects/compose", {
        method: "POST",
        json: { project: p.project, instructions },
      });
      setDraft({ project: p.project, autoSend: p.auto_send, ...r });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function submit(mode: "draft" | "send") {
    if (!draft) return;
    if (mode === "send" && !confirm(`Send this email to ${draft.to} now?`)) return;
    setBusy(mode);
    setError("");
    try {
      await api("/api/outbound", { method: "POST", json: { project: draft.project, to: draft.to, subject: draft.subject, body: draft.body, mode } });
      setNotice(mode === "draft" ? "Saved to your Gmail Drafts." : `Sent to ${draft.to}.`);
      setDraft(null);
      loadHistory();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Projects</h1>
        <p className="text-sm text-muted">Pulled from your Google Sheet. Generate a status email for each project&apos;s stakeholder.</p>
      </div>
      {error && (
        <p className="rounded-md border border-urgent px-3 py-2 text-sm text-urgent">
          {error}{" "}
          {/settings|sheet|connect/i.test(error) && (
            <Link href="/settings" className="underline">
              Open Settings
            </Link>
          )}
        </p>
      )}
      {notice && <p className="text-sm text-normal">{notice}</p>}

      <input
        className="input"
        placeholder="Optional instructions for the AI, e.g. 'keep it under 100 words' or 'mention the demo next week'"
        value={instructions}
        onChange={(e) => setInstructions(e.target.value)}
      />

      <div className="grid gap-3 md:grid-cols-2">
        {projects === null && !error && <p className="text-sm text-muted">Loading projects…</p>}
        {projects?.length === 0 && <p className="text-sm text-muted">No project rows found in the sheet.</p>}
        {projects?.map((p) => (
          <div key={p.project} className="card flex flex-col gap-2 p-4">
            <div className="flex items-start justify-between gap-2">
              <h2 className="font-semibold">{p.project}</h2>
              <span className={`text-sm font-medium ${statusTone(p.status)}`}>{p.status}</span>
            </div>
            {p.progress && <p className="text-sm text-muted">Progress: {p.progress}</p>}
            {p.updates && <p className="text-sm">{p.updates}</p>}
            {p.blockers && <p className="text-sm text-high">Blockers: {p.blockers}</p>}
            <p className="text-xs text-muted">
              To: {p.stakeholder_name || "—"} {p.stakeholder_email && `<${p.stakeholder_email}>`} · Auto-send: {p.auto_send ? "on" : "off"}
            </p>
            <button className="btn mt-auto self-start" onClick={() => generate(p)} disabled={!!busy || !p.stakeholder_email}>
              {busy === `gen:${p.project}` ? "Writing…" : p.stakeholder_email ? "Generate status email" : "No stakeholder email"}
            </button>
          </div>
        ))}
      </div>

      {draft && (
        <section className="card space-y-3 p-4">
          <h2 className="font-semibold">Draft: {draft.project}</h2>
          <label className="block text-sm">
            To
            <input className="input mt-1" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} />
          </label>
          <label className="block text-sm">
            Subject
            <input className="input mt-1" value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} />
          </label>
          <label className="block text-sm">
            Body
            <textarea className="input mt-1 h-64 font-mono" value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
          </label>
          <div className="flex flex-wrap gap-2">
            <button className="btn-primary" onClick={() => submit("draft")} disabled={!!busy}>
              {busy === "draft" ? "Saving…" : "Save to Gmail Drafts"}
            </button>
            <button
              className="btn"
              onClick={() => submit("send")}
              disabled={!!busy || !draft.autoSend}
              title={draft.autoSend ? "" : "Set Auto-send = Y for this project in the sheet to enable"}
            >
              {busy === "send" ? "Sending…" : "Send now"}
            </button>
            <button className="btn" onClick={() => setDraft(null)} disabled={!!busy}>
              Discard
            </button>
          </div>
          {!draft.autoSend && <p className="text-xs text-muted">Sending is off for this project. Set Auto-send = Y in the sheet to enable it.</p>}
        </section>
      )}

      <section className="card">
        <h2 className="border-b border-border px-4 py-2.5 text-sm font-semibold">Sent & drafted</h2>
        {history.length === 0 && <p className="px-4 py-3 text-sm text-muted">Nothing yet.</p>}
        {history.map((h) => (
          <div key={h.id} className="flex flex-wrap justify-between gap-2 border-b border-border px-4 py-2 text-sm last:border-b-0">
            <span className="min-w-0 truncate">
              <span className={h.status === "failed" ? "text-urgent" : h.status === "sent" ? "text-normal" : "text-muted"}>{h.status}</span> ·{" "}
              {h.project} · {h.subject} → {h.to}
            </span>
            <span className="text-muted">{timeAgo(h.created_at)}</span>
          </div>
        ))}
      </section>
    </div>
  );
}
