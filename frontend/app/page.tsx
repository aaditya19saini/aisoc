"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { EmailCard } from "@/components/EmailCard";
import { api, Dashboard, Email, timeAgo } from "@/lib/api";

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [busy, setBusy] = useState<"" | "sync" | "digest">("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => api<Dashboard>("/api/dashboard").then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => {
    load();
  }, [load]);

  async function sync() {
    setBusy("sync");
    setError("");
    setMessage("");
    try {
      const r = await api<{ fetched: number; classified: number; errors: string[]; digest_error?: string }>("/api/sync", {
        method: "POST",
        json: {},
      });
      setMessage(`Fetched ${r.fetched} new emails, classified ${r.classified}.`);
      if (r.errors.length) setError(`Some emails failed to classify: ${r.errors[0]}`);
      else if (r.digest_error) setError(`Briefing failed: ${r.digest_error}`);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function regenerateDigest() {
    setBusy("digest");
    setError("");
    try {
      await api("/api/dashboard/digest", { method: "POST" });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function dismiss(id: string) {
    await api(`/api/emails/${id}`, { method: "PATCH", json: { dismissed: true } });
    load();
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Today</h1>
          <p className="text-sm text-muted">Last sync: {data ? timeAgo(data.last_sync) : "…"}</p>
        </div>
        <button className="btn-primary" onClick={sync} disabled={!!busy}>
          {busy === "sync" ? "Syncing & classifying…" : "Sync inbox"}
        </button>
      </div>

      {message && <p className="text-sm text-muted">{message}</p>}
      {error && (
        <p className="rounded-md border border-urgent px-3 py-2 text-sm text-urgent">
          {error}{" "}
          {/connect|model|api key|sheet/i.test(error) && (
            <Link href="/settings" className="underline">
              Open Settings
            </Link>
          )}
        </p>
      )}

      <section className="card p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Your briefing</h2>
          <button className="btn text-xs" onClick={regenerateDigest} disabled={!!busy}>
            {busy === "digest" ? "Writing…" : "Refresh"}
          </button>
        </div>
        <p className="leading-relaxed">{data?.digest.text || "Sync your inbox to get your first briefing."}</p>
      </section>

      {data && (
        <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Emails (14d)" value={data.totals.emails} />
          <Stat label="Urgent" value={data.totals.urgent} tone="text-urgent" />
          <Stat label="Need your reply" value={data.totals.needs_reply} tone="text-high" />
          <Stat label="Unclassified" value={data.totals.unclassified} />
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Queue title="Urgent & important" emails={data?.urgent} onDismiss={dismiss} empty="Nothing urgent. Nice." />
          <Queue title="Needs your reply" emails={data?.needs_reply} onDismiss={dismiss} empty="You're all caught up on replies." />
          <Queue title="Waiting on others" emails={data?.waiting} onDismiss={dismiss} empty="Not waiting on anyone." />
        </div>
        <div className="space-y-6">
          <Breakdown title="By category" counts={data?.by_category} />
          <Breakdown title="By urgency" counts={data?.by_urgency} order={["urgent", "high", "normal", "low"]} />
          <Queue title="Deadlines" emails={data?.deadlines} onDismiss={dismiss} empty="No deadlines spotted." />
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, tone = "" }: { label: string; value: number; tone?: string }) {
  return (
    <div className="card px-4 py-3">
      <div className={`text-2xl font-semibold tabular-nums ${tone}`}>{value}</div>
      <div className="text-xs text-muted">{label}</div>
    </div>
  );
}

function Queue({ title, emails, onDismiss, empty }: { title: string; emails?: Email[]; onDismiss: (id: string) => void; empty: string }) {
  return (
    <section className="card">
      <h2 className="border-b border-border px-4 py-2.5 text-sm font-semibold">
        {title} {emails && <span className="font-normal text-muted">({emails.length})</span>}
      </h2>
      {!emails ? (
        <p className="px-4 py-3 text-sm text-muted">Loading…</p>
      ) : emails.length === 0 ? (
        <p className="px-4 py-3 text-sm text-muted">{empty}</p>
      ) : (
        emails.map((e) => <EmailCard key={e.id} email={e} onDismiss={onDismiss} />)
      )}
    </section>
  );
}

function Breakdown({ title, counts, order }: { title: string; counts?: Record<string, number>; order?: string[] }) {
  const entries = Object.entries(counts ?? {}).sort((a, b) =>
    order ? order.indexOf(a[0]) - order.indexOf(b[0]) : b[1] - a[1],
  );
  const max = Math.max(1, ...entries.map(([, n]) => n));
  return (
    <section className="card p-4">
      <h2 className="mb-3 text-sm font-semibold">{title}</h2>
      {entries.length === 0 && <p className="text-sm text-muted">No data yet.</p>}
      <div className="space-y-2">
        {entries.map(([k, n]) => (
          <Link key={k} href={`/inbox?${order ? "urgency" : "category"}=${encodeURIComponent(k)}`} className="block text-sm">
            <div className="flex justify-between">
              <span>{k}</span>
              <span className="tabular-nums text-muted">{n}</span>
            </div>
            <div className="mt-1 h-1.5 rounded bg-border">
              <div className="h-1.5 rounded bg-accent" style={{ width: `${(n / max) * 100}%` }} />
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
