export type Email = {
  id: string;
  thread_id: string;
  sender: string;
  sender_email: string;
  subject: string;
  snippet: string;
  received_at: string;
  is_bulk: boolean;
  analyzed: boolean;
  category: string | null;
  urgency: "urgent" | "high" | "normal" | "low" | null;
  urgency_reason: string | null;
  action: "reply" | "review" | "fyi" | "waiting" | null;
  deadline: string | null;
  summary: string | null;
  related_project: string | null;
  analysis_model: string | null;
  analysis_error: string | null;
  overridden: boolean;
  dismissed: boolean;
};

export type Dashboard = {
  digest: { text: string; at: string };
  last_sync: string;
  totals: { emails: number; unclassified: number; urgent: number; needs_reply: number };
  by_category: Record<string, number>;
  by_urgency: Record<string, number>;
  urgent: Email[];
  needs_reply: Email[];
  waiting: Email[];
  deadlines: Email[];
};

export type ModelSettings = { provider: string; model: string; api_base: string; has_key: boolean; key_hint: string };

export type AppSettings = {
  providers: Record<string, { label: string; needs_key: boolean }>;
  models: Record<"classifier" | "writer", ModelSettings>;
  google: { connected: boolean; email: string; credentials_file_present: boolean };
  sheet: { id: string; range: string };
};

export type Project = Record<string, string> & { project: string; auto_send: boolean };

export type Outbound = {
  id: number;
  project: string;
  to: string;
  subject: string;
  mode: string;
  status: string;
  error: string | null;
  created_at: string;
};

export const CATEGORIES = ["Investor", "Customer", "Hiring", "Vendor", "Legal/Finance", "Internal", "Newsletter", "Spam", "Other"];
export const URGENCIES = ["urgent", "high", "normal", "low"];
export const ACTIONS = ["reply", "review", "fyi", "waiting"];

export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  const res = await fetch(path, {
    ...rest,
    headers: json !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
    cache: "no-store",
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail ?? `Request failed (${res.status})`);
  return data as T;
}

export function timeAgo(iso: string): string {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const gmailLink = (e: Email) => `https://mail.google.com/mail/u/0/#all/${e.thread_id}`;
