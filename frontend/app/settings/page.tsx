"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, AppSettings, ModelSettings } from "@/lib/api";

const MODEL_EXAMPLES: Record<string, string> = {
  anthropic: "claude-haiku-5-5 or claude-sonnet-5-5",
  openai: "gpt-4.1-mini",
  gemini: "gemini-2.5-flash",
  groq: "llama-3.3-70b-versatile",
  openrouter: "anthropic/claude-sonnet-5-5",
  ollama: "llama3.1",
};

const TASK_INFO = {
  classifier: { title: "Classifier model", hint: "Reads every email, so a fast, cheap model works best." },
  writer: { title: "Writer model", hint: "Writes your briefing and project status emails, so pick a stronger model." },
} as const;

export default function SettingsPage() {
  return (
    <Suspense>
      <Settings />
    </Suspense>
  );
}

function Settings() {
  const params = useSearchParams();
  const [s, setS] = useState<AppSettings | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<AppSettings>("/api/settings").then(setS).catch((e) => setError(e.message));
  }, []);

  const googleStatus = params.get("google");

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Settings</h1>
      {error && <p className="text-sm text-urgent">{error}</p>}
      {googleStatus === "connected" && <p className="text-sm text-normal">Google account connected.</p>}
      {googleStatus === "error" && <p className="text-sm text-urgent">Google connection failed ({params.get("reason")}). Try again.</p>}

      {s && (
        <>
          <section className="card space-y-4 p-4">
            <div>
              <h2 className="font-semibold">AI models</h2>
              <p className="text-sm text-muted">
                Plug in any provider. Pick it, enter the model name and paste your API key. Changes apply immediately.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {(["classifier", "writer"] as const).map((task) => (
                <ModelSlot key={task} task={task} initial={s.models[task]} providers={s.providers} onSaved={setS} />
              ))}
            </div>
          </section>

          <GoogleSection s={s} onChange={setS} />
          <SheetSection s={s} onChange={setS} />
        </>
      )}
    </div>
  );
}

function ModelSlot({
  task,
  initial,
  providers,
  onSaved,
}: {
  task: "classifier" | "writer";
  initial: ModelSettings;
  providers: AppSettings["providers"];
  onSaved: (s: AppSettings) => void;
}) {
  const [provider, setProvider] = useState(initial.provider);
  const [model, setModel] = useState(initial.model);
  const [apiBase, setApiBase] = useState(initial.api_base);
  const [apiKey, setApiKey] = useState("");
  const [keyHint, setKeyHint] = useState(initial.has_key ? initial.key_hint : "");
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function save(extra: { api_key?: string } = {}) {
    const body: Record<string, string> = { provider, model, api_base: apiBase };
    if (apiKey) body.api_key = apiKey;
    Object.assign(body, extra);
    const s = await api<AppSettings>(`/api/settings/models/${task}`, { method: "PUT", json: body });
    const m = s.models[task];
    setKeyHint(m.has_key ? m.key_hint : "");
    setApiKey("");
    onSaved(s);
  }

  async function saveAndTest() {
    setBusy(true);
    setStatus(null);
    try {
      await save();
      const r = await api<{ ok: boolean; model: string; reply?: string; error?: string }>(`/api/settings/models/${task}/test`, { method: "POST" });
      setStatus(r.ok ? { ok: true, text: `Connected to ${r.model}` } : { ok: false, text: r.error ?? "failed" });
    } catch (e) {
      setStatus({ ok: false, text: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <div>
        <h3 className="text-sm font-semibold">{TASK_INFO[task].title}</h3>
        <p className="text-xs text-muted">{TASK_INFO[task].hint}</p>
      </div>
      <label className="block text-sm">
        Provider
        <select className="input mt-1" value={provider} onChange={(e) => setProvider(e.target.value)}>
          {Object.entries(providers).map(([k, p]) => (
            <option key={k} value={k}>
              {p.label}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        Model
        <input className="input mt-1" value={model} placeholder={`e.g. ${MODEL_EXAMPLES[provider] ?? ""}`} onChange={(e) => setModel(e.target.value)} />
      </label>
      {providers[provider]?.needs_key !== false && (
        <label className="block text-sm">
          API key
          <input
            className="input mt-1"
            type="password"
            autoComplete="off"
            value={apiKey}
            placeholder={keyHint ? `Saved (${keyHint}). Leave blank to keep it` : "Paste key (or set it in backend .env)"}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </label>
      )}
      <label className="block text-sm">
        API base URL <span className="text-muted">(optional)</span>
        <input
          className="input mt-1"
          value={apiBase}
          placeholder={provider === "ollama" ? "http://localhost:11434" : "Only for proxies / self-hosted"}
          onChange={(e) => setApiBase(e.target.value)}
        />
      </label>
      <div className="flex flex-wrap gap-2 pt-1">
        <button className="btn-primary" onClick={saveAndTest} disabled={busy || !model}>
          {busy ? "Testing…" : "Save & test"}
        </button>
        {keyHint && (
          <button className="btn" onClick={() => save({ api_key: "" })} disabled={busy}>
            Remove key
          </button>
        )}
      </div>
      {status && <p className={`text-xs break-words ${status.ok ? "text-normal" : "text-urgent"}`}>{status.text}</p>}
    </div>
  );
}

function GoogleSection({ s, onChange }: { s: AppSettings; onChange: (s: AppSettings) => void }) {
  async function disconnect() {
    await api("/api/google/disconnect", { method: "POST" });
    onChange(await api<AppSettings>("/api/settings"));
  }
  return (
    <section className="card space-y-2 p-4">
      <h2 className="font-semibold">Google account</h2>
      <p className="text-sm text-muted">Gmail (read, draft, send) and Google Sheets (read-only).</p>
      {!s.google.credentials_file_present && (
        <p className="text-sm text-high">
          No OAuth client found. Put your Google Cloud OAuth client JSON at <code>backend/credentials.json</code> (see README).
        </p>
      )}
      {s.google.connected ? (
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm">
            Connected as <strong>{s.google.email}</strong>
          </span>
          <button className="btn" onClick={disconnect}>
            Disconnect
          </button>
        </div>
      ) : (
        <a className="btn-primary" href="/auth/google/start">
          Connect Google
        </a>
      )}
    </section>
  );
}

function SheetSection({ s, onChange }: { s: AppSettings; onChange: (s: AppSettings) => void }) {
  const [sheet, setSheet] = useState(s.sheet.id);
  const [range, setRange] = useState(s.sheet.range);
  const [saved, setSaved] = useState(false);

  async function save() {
    onChange(await api<AppSettings>("/api/settings/sheet", { method: "PUT", json: { sheet, range } }));
    setSaved(true);
  }

  return (
    <section className="card space-y-2 p-4">
      <h2 className="font-semibold">Project status sheet</h2>
      <p className="text-sm text-muted">
        First row = headers: Project, Status, Progress, Updates, Next steps, Blockers, Owner, Stakeholder name, Stakeholder email, Auto-send.
      </p>
      <div className="flex flex-wrap gap-2">
        <input className="input min-w-64 flex-1" placeholder="Google Sheet URL or ID" value={sheet} onChange={(e) => { setSheet(e.target.value); setSaved(false); }} />
        <input className="input w-36" placeholder="A1:Z200" value={range} onChange={(e) => { setRange(e.target.value); setSaved(false); }} />
        <button className="btn-primary" onClick={save}>
          Save
        </button>
      </div>
      {saved && <p className="text-xs text-normal">Saved. Open Projects to see the rows.</p>}
    </section>
  );
}
