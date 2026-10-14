# AI Chief of Staff (v1)

AI triage for your Gmail inbox plus AI-written project status emails.

- **Inbox intelligence:** each email gets a category, urgency (with a reason), the action needed, any deadline and a summary. The dashboard shows a written briefing, urgent / needs-reply / waiting / deadline queues, and breakdowns.
- **Project status emails:** projects come from a Google Sheet. The AI writes a status email for each project's stakeholder. You can save it to Gmail Drafts or send it (sending only works when the sheet row has `Auto-send = Y`, and only to the stakeholder email listed there). Every draft and send is logged.
- **Plug-and-play AI:** pick a provider (Anthropic, OpenAI, Gemini, Groq, OpenRouter, Ollama), a model name and an API key in **Settings**. There are two slots: a cheap *classifier* model and a stronger *writer* model. Changes apply immediately; everything is routed through [LiteLLM](https://docs.litellm.ai/).

Stack: FastAPI + SQLite (`backend/`) and Next.js + Tailwind (`frontend/`).

## Setup

### 1. Google OAuth client (one time)
1. In [Google Cloud Console](https://console.cloud.google.com/), create a project and enable the **Gmail API** and **Google Sheets API**.
2. Set up the **OAuth consent screen** (External / Testing is fine) and add your Gmail address as a test user.
3. Under **Credentials → Create OAuth client ID → Web application**, add the authorized redirect URI `http://localhost:8000/auth/google/callback`.
4. Download the JSON and save it as `backend/credentials.json`.

### 2. Run
```bash
# backend
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# frontend (new terminal)
cd frontend
npm install
npm run dev        # http://localhost:3000
```

### 3. Configure in the app (http://localhost:3000/settings)
1. **AI models:** choose a provider and model, paste the API key, then click **Save & test**. Keys can also go in `backend/.env` (see `.env.example`).
2. **Connect Google.**
3. **Project sheet:** paste the sheet URL. The first row must have these headers:

   | Project | Status | Progress | Updates | Next steps | Blockers | Owner | Stakeholder name | Stakeholder email | Auto-send |
   |---|---|---|---|---|---|---|---|---|---|

Then click **Sync inbox** on the dashboard.

## Demo data
To preview the dashboard without Gmail: `cd backend && uv run python -m app.seed_demo`. Remove it with `--clear`.

## Tests
```bash
cd backend && uv run pytest
```

## Project layout
```
backend/app/
  llm.py            plug-and-play model layer (LiteLLM): get_text / get_json
  classifier.py     email triage schema + prompt
  composer.py       project status email + dashboard briefing
  sync.py           Gmail sync -> classify -> briefing
  google_client.py  OAuth, Gmail read/draft/send, Sheets
  projects.py       sheet rows -> projects
  main.py           API routes
frontend/app/       dashboard, inbox, projects, settings pages
```

## Not in v1 yet
Background/scheduled sync, scheduled auto-sends, rate limits, multi-user accounts, Postgres.
