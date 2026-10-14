"use client";

import { Email, gmailLink, timeAgo } from "@/lib/api";

const urgencyColor: Record<string, string> = {
  urgent: "text-urgent border-urgent",
  high: "text-high border-high",
  normal: "text-normal border-normal",
  low: "text-low border-low",
};

export function UrgencyPill({ urgency }: { urgency: string | null }) {
  if (!urgency) return <span className="rounded border border-border px-1.5 text-xs text-muted">unclassified</span>;
  return <span className={`rounded border px-1.5 text-xs font-medium ${urgencyColor[urgency] ?? ""}`}>{urgency}</span>;
}

export function EmailCard({ email, onDismiss }: { email: Email; onDismiss?: (id: string) => void }) {
  return (
    <div className="border-b border-border px-4 py-3 last:border-b-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <UrgencyPill urgency={email.urgency} />
            {email.category && <span>{email.category}</span>}
            {email.action && email.action !== "fyi" && <span>· {email.action}</span>}
            {email.deadline && <span className="text-high">· due {email.deadline}</span>}
            <span>· {timeAgo(email.received_at)}</span>
          </div>
          <a href={gmailLink(email)} target="_blank" rel="noreferrer" className="mt-1 block truncate font-medium hover:underline">
            {email.subject}
          </a>
          <div className="truncate text-sm text-muted">{email.sender}</div>
          {email.summary && <p className="mt-1 text-sm">{email.summary}</p>}
          {email.urgency_reason && <p className="mt-0.5 text-xs text-muted italic">Why: {email.urgency_reason}</p>}
        </div>
        {onDismiss && (
          <button className="btn shrink-0 text-xs" onClick={() => onDismiss(email.id)} title="Mark as done">
            Done
          </button>
        )}
      </div>
    </div>
  );
}
