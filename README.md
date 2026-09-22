# A360 → Power Automate Migration Studio

Full-stack app for migrating Automation Anywhere A360 bots to Power Automate.

| Layer | Stack | Folder |
|---|---|---|
| Frontend | React 18 + Vite | `frontend/` |
| Backend | Python 3.10+ · FastAPI · SQLAlchemy | `backend/` |
| Database | SQLite (default, file `backend/migration.db`) or Postgres — switch with the `DB_TYPE` flag in `.env` (see below) | — |
| Parser | `backend/app/services/parser.py` — deterministic, no LLM | — |

## Pipeline

1. **Upload** — drop a Control Room export (`.zip`, exported with *Include dependencies*) or a single task-bot `.json`.
2. **Parse** — Python utility reads every task bot: active vs disabled actions, nesting (which bot calls which), variables, packages, Credential Vault / global value references, complexity score. Stored in the DB.
3. **Understand** — one request per bot (chunked for large bots) to your own model — Azure OpenAI, OpenAI, Claude, Gemini, a Copilot Studio agent, a self-hosted model or any HTTP gateway — for the functional narrative; rule set proposes Cloud flow / Desktop flow / AI Builder / Redesign per action group. Solution architect can override any target — the override is saved and drives conversion. Works without any model configured (rule-based narrative).
4. **Convert** — generates per bot: cloud-flow workflow-definition JSON (downloadable, solution-importable) and Robin script for desktop flows (copy to clipboard → paste in PAD designer). Unmapped commands become `# GAP` lines. Export everything as one zip.
5. **Configure** — three tabs: **LLM · bring your own** (model profiles, task routing with fallback, parameters, data governance, payload preview, cost estimate, audit trail); **Power Automate schemas** (cloud `$schema`, connection references); **Robin mapping** (PAD sample and A360-command → Robin table). All stored in the DB.

---

## Running in Visual Studio Code — step by step

### 0. Prerequisites (install once)

| Tool | Version | Check |
|---|---|---|
| Python | 3.10 or newer | `python --version` |
| Node.js | 18 or newer (20 recommended) | `node --version` |
| VS Code | current | — |
| VS Code extensions | Python, Pylance, Python Debugger (Microsoft) | VS Code will prompt to install the recommended ones |

### 1. Open the project

1. Unzip `a360-migration-studio.zip` somewhere without spaces in the path (e.g. `C:\dev\a360-migration-studio`).
2. In VS Code: **File → Open Folder…** → select the `a360-migration-studio` folder.
3. When VS Code offers to install recommended extensions, click **Install**.

### 2. Backend — create the virtual environment and install

Open a terminal in VS Code (**Terminal → New Terminal**) and run:

**Windows (PowerShell)**
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```
If PowerShell refuses to activate: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then retry.

**macOS / Linux**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then tell VS Code to use this interpreter: **Ctrl+Shift+P → Python: Select Interpreter → `backend/.venv`**.

(Alternative: **Terminal → Run Task… → "install everything"** does both the backend and frontend installs.)

### 3. Frontend — install packages

In a second terminal:
```bash
cd frontend
npm install
```

### 4. Run

**Option A — one click (recommended).** Open **Run and Debug** (Ctrl+Shift+D), pick **"Full stack (backend + frontend)"** from the dropdown, press **F5**. Two terminals start:
- API on http://localhost:8000 (interactive docs at http://localhost:8000/docs)
- UI on http://localhost:5173

**Option B — two terminals.**
```bash
# terminal 1
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000     # Windows: .\.venv\Scripts\uvicorn ...
# terminal 2
cd frontend && npm run dev
```

Open http://localhost:5173. The header shows **API connected** when the backend is reachable.

### 5. Try it

1. Stage 1 → **Choose file** → `samples/AR_CashApplication_Main.zip`.
2. Stage 2 shows 5 task bots and the call tree.
3. Stage 3 → **Generate understanding** (rule-based until you configure a model) → change a target in the dropdown to see the override saved.
4. Stage 4 → **Generate flows** → open `Post_F28` → **Robin script** → **Copy Robin to clipboard** → paste into Power Automate for desktop.
5. **Download all artefacts (.zip)** for the cloud-flow JSON files.

### 6. Bring your own LLM (optional)

Stage 5 → **Configure → LLM · bring your own**. Everything works without a model (rule-based); add one to get real narratives.

1. **Add a model** → pick a provider → fill the fields → **Save configuration** → **Test connection** (sends a one-word ping; the status turns *Connected* or shows the provider's error).

   | Provider | Endpoint | Key | Model field |
   |---|---|---|---|
   | Azure OpenAI | `https://<resource>.openai.azure.com` | API key | deployment name |
   | OpenAI | `https://api.openai.com/v1` | API key | e.g. `gpt-4o` |
   | Anthropic Claude | `https://api.anthropic.com` | API key | e.g. `claude-sonnet-4-5` |
   | Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | API key | e.g. `gemini-2.5-pro` |
   | Copilot Studio agent | `https://directline.botframework.com/v3/directline` | Direct Line secret (agent → Settings → Channels) | — |
   | Self-hosted (Ollama / vLLM / LM Studio) | e.g. `http://localhost:11434/v1` | optional | e.g. `llama3.1:70b` |
   | Custom HTTP gateway | your URL | optional | + headers JSON, body template, response path |

2. **Which model does what** — route each task to a primary model and a fallback:
   - *Functional understanding* — narrative per bot
   - *Target classification* — model re-checks the rule-based Cloud / Desktop / AI Builder / Redesign suggestion
   - *GAP assist* — model proposes PAD actions under `# GAP` lines, marked `# SUGGESTED … review before use`

   Attempt order: primary (with retries) → fallback (with retries) → rule set. The pipeline never stops on a model error.
3. **Generation parameters** — temperature, max tokens, actions per request (large bots are chunked and merged), timeout, retries.
4. **Data governance** — applied to *every* request before it leaves the backend:
   - mask literal values (structure, variable names, sub-task paths, SAP field IDs and conditions are kept; data becomes `<masked>`)
   - replace Credential Vault references with `<vault-ref>`
   - redact paths, URLs and email addresses
   - data residency: *Client tenant only* makes the backend refuse public endpoints (OpenAI, Anthropic, Gemini) and log the call as `blocked`
   - **Preview what gets sent** shows the exact first request for a bot after these rules
5. **Estimated usage** — token and cost estimate for the open project, projected to N bots, per model profile (prices are editable per profile).
6. **Recent model calls** — audit trail from the `llm_calls` table: task, model, status, latency, error. Prompt/response bodies are stored only when *Keep prompts and responses* is on. API keys are never written to the audit log.

API keys are stored in the backend database and always returned masked (`••••1234`); saving the masked value back keeps the stored key.

### 7. Inspect the database

Install the recommended **SQLite Viewer** extension, then click `backend/migration.db` in the Explorer. Tables: `projects`, `bots`, `action_groups`, `artifacts`, `config`, `run_log`, `llm_calls` (model audit trail).

### Database choice (SQLite or Postgres)

The backend reads `DB_TYPE` from `backend/.env` (gitignored, never pushed):

```dotenv
DB_TYPE=sqlite        # local file backend/migration.db — nothing else to set
# or
DB_TYPE=postgresql
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME
# …or leave DATABASE_URL empty and set DB_HOST, DB_PORT(=5432), DB_USER, DB_PASSWORD, DB_NAME instead
```

Tables are created automatically on startup (`app/main.py` → `Base.metadata.create_all`) — no manual schema setup for either backend.

### Deploy to Render

Commit to GitHub, then in Render: **New + → Blueprint** → pick the repo. `render.yaml` creates a Postgres database, the API service and the UI service; the API's `DATABASE_URL` is injected from the database automatically.

After provisioning, set two env vars in the Render dashboard (*sync: false*):

1. **API service** → `CORS_ORIGINS` = your UI URL, e.g. `https://a360-migration-ui.onrender.com`
2. **UI service** → `VITE_API_BASE` = your API URL, e.g. `https://a360-migration-api.onrender.com` (read at **build time** — changing it triggers a redeploy)

Data lives in Render Postgres (persists across deploys). SQLite would NOT persist on Render, so keep `DB_TYPE=postgresql` there.

---

## Project layout

```
a360-migration-studio/
├─ .vscode/                 launch.json (F5 configs), tasks.json, settings, extensions
├─ backend/
│  ├─ app/
│  │  ├─ main.py            FastAPI app, CORS, table creation
│  │  ├─ db.py              engine / session (DATABASE_URL)
│  │  ├─ models.py          Project, Bot, ActionGroup, Artifact, Config, RunLog
│  │  ├─ schemas.py         Pydantic models
│  │  ├─ routers/
│  │  │  ├─ projects.py     upload/parse · understand · target override · convert · download · export.zip
│  │  │  └─ config.py       GET/PUT/reset configuration
│  │  └─ services/
│  │     ├─ parser.py       A360 export parser (no LLM) + complexity scoring
│  │     ├─ classify.py     rule set: package → Cloud / Desktop / AI Builder / Redesign
│  │     ├─ llm.py          Bring Your Own LLM: provider adapters, masking, routing + fallback, classify, GAP assist
│  │     ├─ convert.py      cloud-flow JSON + Robin generators
│  │     └─ defaults.py     seed configuration
│  ├─ requirements.txt
│  └─ .env.example
├─ frontend/
│  ├─ src/App.jsx           stage rail + routing
│  ├─ src/components/       Upload · Parse · Understand · Convert · Configure · LLMConfig
│  ├─ src/lib/llm.js        provider catalogue, cost estimate helpers
│  ├─ src/lib/api.js        API client
│  └─ vite.config.js        /api proxy → localhost:8000
└─ samples/AR_CashApplication_Main.zip
```

## API reference (also at /docs)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/projects` | upload + parse (multipart `file`) |
| GET | `/api/projects` · `/api/projects/{id}` | list / detail |
| POST | `/api/projects/{id}/bots/{bot_id}/understand` | narrative + target suggestion for one bot |
| POST | `/api/projects/{id}/understand` | all bots (sequential, server side) |
| PATCH | `/api/projects/{id}/groups/{group_id}` | `{ "target": "Desktop flow" }` — SA override |
| POST | `/api/projects/{id}/bots/{bot_id}/convert` · `/api/projects/{id}/convert` | generate artefacts |
| GET | `/api/projects/{id}/artifacts/{artifact_id}` | one artefact (JSON or Robin) |
| GET | `/api/projects/{id}/export.zip` | all artefacts |
| GET / PUT / POST | `/api/config` · `/api/config/reset` | configuration (keys masked on read) |
| POST | `/api/config/llm/test/{profile_id}` | live connection test for a saved model profile |
| GET | `/api/config/llm/calls` | model-call audit trail |
| GET | `/api/projects/{id}/llm-preview?bot_id=` | exact first request for a bot after masking — nothing is sent |
| GET | `/api/projects/{id}/llm-estimate` | token estimate for the project |

## Tuning

- **Complexity weights**: `parser.py` → `LOC_BANDS`, `PACKAGE_WEIGHT`, `COMPLEXITY_THRESHOLDS`.
- **Target rules**: `classify.py` → `RULES` (regex on package name, first match wins).
- **Robin mapping**: Stage 5 in the UI (stored in DB) — or `defaults.py` for the seed. `{attr}` = Robin literal, `{attr!}` = raw text.
- **Cloud-flow action templates**: `convert.py` → `cloud_flow_json`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Header says **API offline** | Backend not running or not on port 8000. Check terminal 1 / the Debug console. |
| `ModuleNotFoundError: app` | Run uvicorn from the `backend/` folder, not the repo root. |
| PowerShell won't activate venv | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Port 5173/8000 in use | Change in `vite.config.js` / launch.json; update `CORS_ORIGINS` in `.env` if you change 5173. |
| Upload says "No task-bot JSON found" | The zip has no objects with a `nodes` array. Export from Control Room with *Include dependencies*, or upload a bot `.json` directly. |
| Test connection says *Failed* | Read the error in the toast or **Recent model calls**. HTTP 401 = key; 404 = endpoint or deployment/model name; timeout = network/proxy. Self-hosted endpoints must be reachable from the backend machine, not the browser. |
| Narrative source still says `rules` | No model routed to *Functional understanding*, the model failed (see Recent model calls), or residency blocked a public endpoint. |
| Robin pastes with red cards in PAD | That action's syntax differs in your PAD version. Paste a real sample into Stage 5 → PAD schema sample, and fix the mapping row. |
