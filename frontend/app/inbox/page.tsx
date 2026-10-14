"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { UrgencyPill } from "@/components/EmailCard";
import { ACTIONS, api, CATEGORIES, Email, gmailLink, timeAgo, URGENCIES } from "@/lib/api";

export default function InboxPage() {
  return (
    <Suspense>
      <Inbox />
    </Suspense>
  );
}

function Inbox() {
  const params = useSearchParams();
  const router = useRouter();
  const [emails, setEmails] = useState<Email[] | null>(null);
  const [q, setQ] = useState(params.get("q") ?? "");
  const [error, setError] = useState("");

  const filters = { category: params.get("category") ?? "", urgency: params.get("urgency") ?? "", action: params.get("action") ?? "" };

  const load = useCallback(() => {
    const qs = new URLSearchParams([...params.entries()].filter(([, v]) => v));
    api<Email[]>(`/api/emails?${qs}`).then(setEmails).catch((e) => setError(e.message));
  }, [params]);
  useEffect(() => {
    load();
  }, [load]);

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`/inbox?${next}`);
  }

  async function override(id: string, field: string, value: string) {
    const updated = await api<Email>(`/api/emails/${id}`, { method: "PATCH", json: { [field]: value } });
    setEmails((list) => list?.map((e) => (e.id === id ? updated : e)) ?? null);
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Inbox</h1>
      <div className="flex flex-wrap gap-2">
        <form
          className="min-w-48 flex-1"
          onSubmit={(e) => {
            e.preventDefault();
            setFilter("q", q);
          }}
        >
          <input className="input" placeholder="Search subject, sender, summary…" value={q} onChange={(e) => setQ(e.target.value)} />
        </form>
        <Select value={filters.category} options={CATEGORIES} placeholder="All categories" onChange={(v) => setFilter("category", v)} />
        <Select value={filters.urgency} options={URGENCIES} placeholder="Any urgency" onChange={(v) => setFilter("urgency", v)} />
        <Select value={filters.action} options={ACTIONS} placeholder="Any action" onChange={(v) => setFilter("action", v)} />
      </div>
      {error && <p className="text-sm text-urgent">{error}</p>}

      <div className="card overflow-hidden">
        {emails === null && <p className="px-4 py-3 text-sm text-muted">Loading…</p>}
        {emails?.length === 0 && <p className="px-4 py-3 text-sm text-muted">No emails match.</p>}
        {emails?.map((e) => (
          <div key={e.id} className="border-b border-border px-4 py-3 last:border-b-0">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              <UrgencyPill urgency={e.urgency} />
              <span>{e.sender}</span>
              <span>· {timeAgo(e.received_at)}</span>
              {e.overridden && <span>· edited by you</span>}
              {e.analysis_error && <span className="text-urgent">· classification failed</span>}
            </div>
            <a href={gmailLink(e)} target="_blank" rel="noreferrer" className="mt-1 block font-medium hover:underline">
              {e.subject}
            </a>
            <p className="text-sm text-muted">{e.summary ?? e.snippet}</p>
            {e.analyzed && (
              <div className="mt-2 flex flex-wrap gap-2">
                <Select small value={e.category ?? ""} options={CATEGORIES} onChange={(v) => override(e.id, "category", v)} />
                <Select small value={e.urgency ?? ""} options={URGENCIES} onChange={(v) => override(e.id, "urgency", v)} />
                <Select small value={e.action ?? ""} options={ACTIONS} onChange={(v) => override(e.id, "action", v)} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Select({
  value,
  options,
  placeholder,
  onChange,
  small,
}: {
  value: string;
  options: string[];
  placeholder?: string;
  onChange: (v: string) => void;
  small?: boolean;
}) {
  return (
    <select className={`input ${small ? "w-auto py-0.5 text-xs" : "w-auto"}`} value={value} onChange={(e) => onChange(e.target.value)}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}
