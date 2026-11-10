# Jarvis — One companion. Every device.

**Jarvis lives in the cloud. Open it anywhere, sign in with Google, use your own Gemini key, everything syncs.**

Like Jessica (Muse) — it works on your laptop, on your phone, on your tablet, anywhere, anytime. Like a walking computer. There is **nothing on your laptop**: no install, no localhost, no terminal, no Tailscale, no setup on your side. A new user opens the web app, signs in with Google, adds their own free Gemini key (about a minute, guided in the app), and just starts chatting. The same account means the same chats, notes, memories and reminders on every device — state lives in the cloud per user, not per device.

Under the hood, the frontend and backend both run on Vercel (one project): the Companion PWA and landing page are static, the FastAPI backend runs as serverless functions under `/api/*`, and all per-user data lives in Postgres (Neon). Gemini is called with **each user's own key** (BYOK) — there is no shared server key, so nobody can spend anyone else's quota and the owner has no API bill.

## How it works for a new user

1. **Open the app** — the Companion at `/mobile/` (or the landing page at `/`, then "Open app").
2. **Sign in with Google** — one tap, no password typed into Jarvis (Google handles sign-in).
3. **Add your free Gemini key** — Settings → Your Gemini key. Get one free from [Google AI Studio](https://aistudio.google.com/) (Get API key → copy → paste → Save). Your key is encrypted on the server and never shown again.
4. **Start chatting** — ask, take notes, set reminders, get a briefing. Open the app on another device, sign in, and everything is there.

## What works today — and what does not yet

| Capability | Status | Notes |
|---|---|---|
| Sign in with Google, chat anywhere | Available | Cloud backend on Vercel; session is a stateless JWT (cookie + Bearer). |
| Your own Gemini key (BYOK) | Available | Encrypted at rest (Fernet), masked in the UI, never logged, never sent to the frontend. Key status + live validation in Settings. |
| Same chats, notes, memories, reminders on every device | Available | Per-user rows in Postgres (Neon); local dev uses per-user files instead. |
| Voice input, editable transcript, spoken replies | Available | Browser speech recognition; raw audio stays on-device. |
| Read-only Gmail & Calendar summaries | Local mode only | Still uses the laptop owner's single Google connection; **not available in cloud mode yet** (per-user Gmail tokens are not built). |
| Choosing between several paired devices | In development | One account works everywhere now; device targeting is a later step. |
| Laptop → phone actions (e.g. reminders on your phone) | Planned | Needs a phone companion that can receive actions. |
| Tablet as a command source | Available | The Companion web app opens in a tablet browser. |
| Wi-Fi, volume & brightness controls | Planned | Interfaces exist in `backend/app/tools/future_interfaces.py`; the features are not implemented. |
| Windows-only tools (app launch, screenshots, system status) | Local only — not in cloud | They read/control a physical laptop, which a cloud server does not have. In cloud mode they reply with a clear "not available" message instead of faking it. |
| Push notifications for reminders | Not built | Reminders are stored and shown when you open the app; nothing pushes yet. |

Jarvis never submits forms, quizzes, exams, or purchases, and it never asks you
to share passwords or API keys in chat.

## Features

- **Cloud-first** — sign in with Google, bring your own Gemini key, and
  everything syncs. No laptop, no localhost, no install. Local dev still
  works with zero setup (see "Local development" below).
- **Chat with tool calling** — Gemini (default `gemini-3.8-flash`, called
  with *your* key) calls tools over up to 5 turns. If you have not saved
  a key yet, chat tells you plainly how to add one instead of failing
  cryptically.
- **Files and notes** — `list_files`, `read_text_file` (sandboxed to
  your own workspace), `create_note`, `search_notes`. Everything is
  namespaced per Google account, so you only ever see your own files.
  Paths are resolved and checked against the configured directory;
  traversal, symlink escapes, null bytes, and NTFS alternate data
  streams are rejected.
- **Windows companion** — `open_application` (allowlist only: notepad,
  calculator, paint, explorer, cmd), `get_battery_status`,
  `get_storage_status`, `get_memory_status`, `capture_screenshot` and
  `analyze_screenshot`. Windows-only tools report an unsupported-platform
  error on macOS/Linux.
- **Reminders and memory** — reminders and explicitly approved memories
  stored per user (Postgres in production, per-user files locally).
  Memory never silently absorbs chat history, and passwords, API keys,
  card numbers, and tokens are refused on save.
- **Web search and daily briefing** — `web_search` via the official Tavily,
  Google Custom Search, or Brave APIs (no scraping); `get_daily_briefing`
  summarises reminders, notes, and an optional web overview on demand.
  Search queries are screened so credentials are never sent to a provider.
- **Gmail and Calendar, read-only** — OAuth 2.0 with PKCE, read-only
  scopes (`gmail.readonly`, `calendar.readonly`). Listing and summarising
  only; Jarvis cannot send mail, delete messages, or create/edit events.
  Tokens live in the OS credential store (Windows Credential Locker via
  `keyring`); a local fallback file is opt-in only.
- **Chrome extension** — Manifest V3, permissions `activeTab` and
  `scripting` only. Reads the active tab you choose, strips password and
  hidden fields, and offers voice input (Web Speech API), study help, and
  browser automation. It never submits forms, quizzes, or purchases.
- **Browser automation** — `browser_navigate`, `browser_read_page`,
  `browser_fill_field` on user-approved domains only. Sensitive fields
  (passwords, cards, CVVs, tokens) are never read or filled, and automated
  submission, checkout, and quiz completion are blocked.
- **Mobile PWA companion** — the same landing-page design family
  (near-black, warm off-white, one lilac accent, 3D tilt, pointer glow,
  per-pixel scroll), with chat, voice input, stop/abort control,
  pending-action approvals, an audit feed, Google sign-in, Gemini-key
  setup, and synced chat history. Served at `/mobile/`. Command history
  is opt-in and off by default.
- **Remote access via Tailscale Serve (legacy, local mode only)** — pair
  your phone once with a 6-digit code generated on the laptop (5-minute
  expiry, single use, 5 failed attempts per 60 seconds rate-limited).
  The cloud path replaces this entirely; Tailscale remains only for
  local development against a laptop backend.
- **Confirmations** — state-changing tools (open app, screenshot, delete
  reminder, and others) return a one-time confirmation ID (128-bit entropy)
  that you approve or deny via `POST /api/confirm` before anything runs.
- **Data controls** — export, a confirmation-guarded wipe
  (`POST /api/data/clear`), and checksum-verified local backups (local
  mode only — in cloud mode your data already lives in Postgres, which
  provides its own backups). Every action is written to a per-user audit
  log with keys, tokens, emails, and card numbers redacted.
- **Demo data API** — `/api/demo/status`, `/api/demo/seed`, and
  `/api/demo/reset` manage `[DEMO]`-tagged seed data (notes, reminders,
  memories) for testing; reset removes only those items. There is no demo
  page or demo UI — the demo section was removed.

## Requirements

**For users: nothing to install.** A modern browser is enough — open the
web app, sign in with Google, add your own free Gemini key.

**For developers / deploying your own copy:**

- Python 3.12 (or newer 3.x), pip, Node.js (only for `node --check` on the
  frontend JS in CI)
- A Vercel account (free Hobby plan works) for hosting frontend + backend
- A Neon account (free tier) for Postgres — the cloud database
- A Google Cloud project for the OAuth client (sign-in) — free
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)
  **per user** (free tier) — each user brings their own; there is no
  server key to buy or manage
- A search API key (Tavily, Google Custom Search, or Brave) for web
  search (optional)
- Windows 10/11 64-bit only for the *legacy local mode* extras (app
  control, screenshots, system metrics, OS credential store). The cloud
  backend runs on Linux (Vercel); Windows-only tools report "not
  available in cloud mode" there.

## Deploy the backend on Vercel (production)

The frontend and backend are **one Vercel project** (same repo). The
frontend is static (`outputDirectory: frontend/public`); the backend is
a serverless function (`api/index.py`, routed by `vercel.json` so every
`/api/*` request reaches FastAPI). No server Gemini key is needed.

### 1. Create the database (Neon, free tier)

1. At [neon.tech](https://neon.tech), create a project (free tier) and a
   database (e.g. `jarvis`).
2. Copy the connection string. Use the **pooled** connection string if
   Neon offers it (serverless functions open many short-lived
   connections; pooling keeps that healthy). It looks like:
   `postgresql://<user>:<password>@<host>.neon.tech/jarvis?sslmode=require`
3. Tables are created automatically on first use (`CREATE TABLE IF NOT
   EXISTS` in `backend/app/core/store.py`): `jarvis_users`,
   `jarvis_notes`, `jarvis_memories`, `jarvis_reminders`,
   `jarvis_user_keys`, `jarvis_chat_history`, `jarvis_action_log`,
   `jarvis_usage`. No migration step is needed for a fresh database.

### 2. Create the Google OAuth client (sign-in)

1. In the [Google Cloud Console](https://console.cloud.google.com/),
   create a project and enable **no APIs** for sign-in itself (Gmail /
   Calendar APIs are only needed for the local-mode read-only features).
2. Under **APIs & Services > OAuth consent screen**, create an
   **External** app, add the scopes `openid`, `email`, `profile`, and
   publish it (or add test users while in testing mode).
3. Under **APIs & Services > Credentials**, create an **OAuth client ID**
   (**Web application**) with authorized redirect URI
   `https://<your-vercel-domain>/api/auth/login/callback`
   (e.g. `https://jarvis-kumar-shaurya.vercel.app/api/auth/login/callback`).
   Also add `http://127.0.0.1:8000/api/auth/login/callback` for local dev.
4. Copy the client ID and client secret — they go in Vercel env vars,
   never in the repo. **No client IDs or secrets are invented or
   committed anywhere in this project.**

### 3. Import the project in Vercel

1. In Vercel, **Add New > Project**, import `Kshaurya-07/Jarvis`.
2. Framework preset: **Other** (the repo sets `outputDirectory:
   frontend/public` in `vercel.json`; no build command is needed for
   the static frontend).
3. Set these **Environment Variables** (Production):

   | Variable | Value |
   | --- | --- |
   | `CLOUD_MODE` | `true` |
   | `ENVIRONMENT` | `production` |
   | `DATABASE_URL` | the Neon connection string from step 1 |
   | `SESSION_SECRET` | a long random string (32+ chars) — generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
   | `KEY_ENCRYPTION_KEY` | a Fernet key — generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` (optional; if unset, one is derived from `SESSION_SECRET`) |
   | `GOOGLE_CLIENT_ID` | from step 2 |
   | `GOOGLE_CLIENT_SECRET` | from step 2 |
   | `GOOGLE_LOGIN_REDIRECT_URI` | `https://<your-vercel-domain>/api/auth/login/callback` |
   | `FRONTEND_URL` | `https://<your-vercel-domain>` |
   | `SEARCH_API_KEY` | optional, for web search |

   Rotating `SESSION_SECRET` signs everyone out and makes previously
   stored BYOK keys undecryptable (users just re-enter their key).
   Rotating `KEY_ENCRYPTION_KEY` has the same effect on stored keys only.
4. Deploy. Check `https://<your-vercel-domain>/api/health` (200, no
   per-user counts in cloud mode), then open `/mobile/`, sign in with
   Google, add a Gemini key, and chat.

### 4. Get a free Gemini key (every user, in the app)

1. Open [Google AI Studio](https://aistudio.google.com/) → **Get API key**
   → **Create API key**.
2. Copy it (it starts with `AIza` for older keys, or `AQ.` for keys created in AI Studio since May 2026).
3. In Jarvis: Settings → Your Gemini key → paste → **Save key**. The
   app shows only the last 4 characters afterwards, and **Validate**
   checks it against Google before you chat. Free-tier quotas apply to
   your own Google account, not to Jarvis's owner.

## Vercel limits — read this before promising anything

Vercel serverless is **stateless** and the Hobby plan is small. The
design respects that honestly; these are real limits, not fine print:

| Limit | What it means for Jarvis |
| --- | --- |
| **No persistent filesystem** | Files written on Vercel disappear on the next invocation. That is why **all** user data lives in Postgres (`DATABASE_URL`). If `DATABASE_URL` is unset in cloud mode, the backend still boots but warns loudly that data will not persist. |
| **Function timeout: 10 s (Hobby)** | `vercel.json` sets `maxDuration: 10` (the Hobby maximum). A chat turn that needs several Gemini tool calls can exceed 10 s on a cold start; the app then shows a plain error and the user retries. There is no streaming yet. Pro raises the cap to 60 s. |
| **Cold starts** | The first request after idle can take a few seconds (Python + FastAPI boot). Sessions, login state and data are unaffected — they live in JWTs / Postgres, not memory. |
| **No background jobs** | No daemons, no push notifications, no scheduled reminders. Reminders are stored and shown when you open the app. (A future step could add Vercel Cron hitting an endpoint; it is not built.) |
| **In-memory state does not sync** | Per-user usage caps are durable in Postgres, but the confirmation manager and the Gmail OAuth pending-states are in-memory: a pending confirmation can be lost if the function cold-starts before you approve it — you just approve again. The Google *login* flow is stateless by design (PKCE verifier in a signed cookie), so sign-in survives cold starts. |
| **One instance, one region** | Hobby deploys run in one region; latency depends on where the user is. |

### Render as an alternative (not the primary path)

The deploy target is Vercel. If you ever prefer a long-running server
instead, the same FastAPI app runs on Render as a Web Service
(`uvicorn app.main:app --host 0.0.0.0 --port $PORT` from `backend/`,
with `CLOUD_MODE=true`, `DATABASE_URL`, `SESSION_SECRET` and the Google
vars set) — but no Render config is shipped, and Vercel is the path
documented and tested here.

## Local development

No cloud account needed. Local mode uses per-user files
(`data/users/<namespace>/…`) and loopback trust, so the existing
workflow keeps working:

```powershell
git clone https://github.com/Kshaurya-07/Jarvis.git
cd Jarvis
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
copy .env.example .env
```

Edit `.env` if you want (Google sign-in needs `GOOGLE_CLIENT_ID` /
`GOOGLE_CLIENT_SECRET` + `SESSION_SECRET`; otherwise leave the cloud
vars unset), then start the server from the `backend/` folder:

```powershell
cd backend
.\..\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

On macOS/Linux use `python3 -m venv .venv`,
`source .venv/bin/activate`, `cp .env.example .env`, and from `backend/`:
`uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`.

Open `http://127.0.0.1:8000/` (redirects to the vision landing page at
`/landing/`, the homepage), `http://127.0.0.1:8000/mobile/` for the
companion. Check health with
`GET http://127.0.0.1:8000/health`. In local mode, sign-in is optional:
loopback requests act as the local owner, and your own Gemini key is
saved the same way (Settings → Your Gemini key).

### Chrome extension

1. Open `chrome://extensions/` and enable **Developer mode**.
2. Click **Load unpacked** and select the `frontend/extension/` folder.
3. Pin **Jarvis Local Companion** to the toolbar and click **Read this page**
   on a tab you want summarised.

   > Note: the extension talks to a local backend (`http://127.0.0.1:8000`) —
   > it does not use the cloud backend yet.

### Mobile PWA

With the backend running, open `http://127.0.0.1:8000/mobile/` in a
browser and install it from the address bar (Chrome/Edge) or
**Share > Add to Home Screen** (iOS Safari). The PWA caches the app shell
for fast startup; API calls always go to the live backend. On Vercel,
just open `https://<your-vercel-domain>/mobile/` and install it the
same way — no backend address to type in.

## Configuration

Copy `.env.example` to `.env` at the repo root. The backend reads that
file even when started from `backend/`; a `.env` inside `backend/`
overrides it if present. Never commit a real `.env` — it is
gitignored. All settings have defaults in `backend/app/core/config.py`.

| Variable | Default | Notes |
| --- | --- | --- |
| `GEMINI_API_KEY` | — | **IGNORED since Phase 12 (BYOK).** Each user brings their own key in the app; there is no server key. Do not set it. |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Gemini model used for chat and tool calling. |
| `GEMINI_FALLBACK_MODEL` | — (none) | Optional fallback model, tried once when the primary model stays overloaded (503). Google's docs also list `gemini-3.5-flash-lite`. |
| `CLOUD_MODE` | `false` | `true` on Vercel: sign-in mandatory, storage is Postgres, host is the Vercel domain. Local dev leaves it `false`. |
| `DATABASE_URL` | — | **Required in production.** Neon Postgres connection string. Unset = local per-user files. |
| `SESSION_SECRET` | — | **Required in cloud mode.** Long random secret (32+ chars) signing session JWTs; also the fallback BYOK encryption-key source. |
| `KEY_ENCRYPTION_KEY` | — | Optional dedicated Fernet key for stored Gemini keys (else derived from `SESSION_SECRET`). |
| `GOOGLE_LOGIN_REDIRECT_URI` | `http://127.0.0.1:8000/api/auth/login/callback` | Sign-in callback; must match Google Cloud Console exactly (production: `https://<domain>/api/auth/login/callback`). |
| `GOOGLE_LOGIN_SCOPES` | `openid, email, profile` | Sign-in scopes only — separate from the Gmail/Calendar scopes below. |
| `FRONTEND_URL` | `https://jarvis-kumar-shaurya.vercel.app` | Public frontend origin users return to after sign-in. |
| `GEMINI_CALLS_PER_USER_PER_HOUR` | `30` | Per-user Gemini call cap (fat-finger guard; the user's own key pays). |
| `GEMINI_CALLS_PER_USER_PER_DAY` | `100` | Per-user Gemini call cap per day. |
| `HOST` | `127.0.0.1` | Local mode binds here. Cloud mode is served by Vercel; binding does not apply. |
| `PORT` | `8000` | Backend port. |
| `ENVIRONMENT` | `development` | `development` or `production`. |
| `LOG_LEVEL` | `INFO` | Log level. |
| `ALLOW_REMOTE_ACCESS` | `false` | Legacy local-mode flag. Must stay `false` unless you deliberately expose a laptop backend. |
| `MEMORY_ENABLED` | `true` | Enables user-approved persistent memory. |
| `WORKSPACE_DIR`, `NOTES_DIR`, `SCREENSHOTS_DIR`, `DATA_DIR`, `BACKUPS_DIR` | `./workspace`, `./notes`, `./screenshots`, `./data`, `./backups` | Local storage directories. |
| `REMINDERS_FILE`, `MEMORIES_FILE`, `ACTION_LOG_FILE` | `./data/reminders.json`, `./data/memories.json`, `./logs/actions.jsonl` | Local data files. |
| `GOOGLE_FALLBACK_TOKEN_FILE` | `./data/protected_google_token.json` | Used only if `GOOGLE_CREDENTIAL_FALLBACK_OPT_IN=true`. |
| `SEARCH_PROVIDER` | `tavily` | `tavily`, `google_custom_search`, or `brave`. |
| `SEARCH_API_KEY` | — | Key for the configured search provider. |
| `SEARCH_ENGINE_ID` | — | Google Custom Search engine ID (`cx`); only for `google_custom_search`. |
| `SEARCH_TIMEOUT_SECONDS` | `8.0` | Search request timeout. |
| `MAX_SEARCH_RESULTS` | `5` | Max search results per query. |
| `MAX_SEARCH_QUERY_LENGTH` | `200` | Max search query length. |
| `MAX_FILE_READ_BYTES` | `1048576` | Max file size for `read_text_file` (1 MB). |
| `MAX_REQUEST_LENGTH` | `4096` | Max user prompt length. |
| `MAX_REQUEST_BODY_BYTES` | `2097152` | Max request body (2 MB). |
| `MAX_PAGE_TEXT_CHARS` | `50000` | Max page text read by the extension. |
| `CONFIRMATION_TIMEOUT_SECONDS` | `300` | Pending-confirmation lifetime (5 minutes). |
| `AUTH_FAILURE_RATE_LIMIT` | `5` | Max auth failures before a temporary block. |
| `AUTH_FAILURE_WINDOW_SECONDS` | `60` | Rate-limit window in seconds. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | — | Google Cloud OAuth credentials (see below). |
| `GOOGLE_REDIRECT_URI` | `http://127.0.0.1:8000/api/auth/google/callback` | Must match the redirect URI in Google Cloud. |
| `GOOGLE_CREDENTIAL_FALLBACK_OPT_IN` | `false` | Opt in to local fallback token storage. |
| `GOOGLE_OAUTH_SCOPES` | Gmail + Calendar read-only | JSON array; see `.env.example`. |
| `MAX_GMAIL_RESULTS` | `10` | Max Gmail results per listing. |
| `MAX_CALENDAR_RESULTS` | `25` | Max Calendar events per listing. |
| `ALLOWED_ORIGINS` | `[]` | JSON array of extra permitted browser origins. |
| `TAILSCALE_HOST` | — | Optional explicit Tailscale machine domain, e.g. `laptop.tailnet.ts.net`. |
| `REMOTE_PAIRING_CODE_TIMEOUT_SECONDS` | `300` | Pairing-code lifetime (5 minutes). |
| `REMOTE_SESSION_TIMEOUT_SECONDS` | `3600` | Session-token lifetime (1 hour). |
| `PAIRING_RATE_LIMIT` | `5` | Max failed pairing attempts. |
| `PAIRING_RATE_LIMIT_WINDOW_SECONDS` | `60` | Pairing rate-limit window in seconds. |

List-valued settings (`GOOGLE_OAUTH_SCOPES`, `ALLOWED_ORIGINS`) must be
JSON arrays in `.env`, for example
`ALLOWED_ORIGINS=["https://example.com"]`. Startup fails with a clear
error if a list value is not valid JSON.

## Search providers

Set `SEARCH_PROVIDER` and `SEARCH_API_KEY` in `.env`:

- **Tavily (default)** — sign up at [tavily.com](https://tavily.com/),
  set `SEARCH_PROVIDER=tavily`.
- **Google Custom Search** — enable the Custom Search API in Google
  Cloud, create a Programmable Search Engine, set
  `SEARCH_PROVIDER=google_custom_search`, `SEARCH_API_KEY` to your API
  key, and `SEARCH_ENGINE_ID` to the engine ID (`cx`).
- **Brave** — get a key at [brave.com/search/api/](https://brave.com/search/api/),
  set `SEARCH_PROVIDER=brave`.

Without `SEARCH_API_KEY`, Jarvis runs normally and reports that web
search is not configured when it is requested.

## Google sign-in (login) vs Google data (Gmail & Calendar)

Two separate OAuth uses share one client ID/secret but **different
scopes and different redirect URIs** — do not mix them up:

| | Sign-in (login) | Gmail & Calendar (local mode only) |
| --- | --- | --- |
| Scopes | `openid`, `email`, `profile` | `gmail.readonly`, `calendar.readonly` |
| Redirect URI | `/api/auth/login/callback` | `/api/auth/google/callback` |
| Endpoints | `GET /api/auth/login` → `GET /api/auth/login/callback` → `GET /api/auth/me` | `GET /api/auth/google/url` → callback → `/api/auth/google/status` |
| Session | Stateless JWT (24 h), HttpOnly cookie `jarvis_session` | Tokens stored per Google account on the laptop, read-only |

### Sign-in flow (cloud)

1. `GET /api/auth/login` (or `?format=json`) redirects to Google with
   PKCE + a state value held in a signed 10-minute cookie — no server
   state, so login survives Vercel cold starts.
2. Google redirects back to `/api/auth/login/callback`; the backend
   verifies the state and the ID token (`verify_oauth2_token` against
   Google's keys), then mints a JWT containing only the Google `sub`
   (stable user ID), email and name.
3. `GET /api/auth/me` returns `{authenticated, email, name, cloud_mode,
   has_key, key_hint}` so the Companion can show the right onboarding.
4. `POST /api/auth/logout` clears the cookie.

Unauthenticated requests to any AI or data endpoint get **401 "Sign-in
required…"** in cloud mode. In local mode, loopback requests act as the
local owner; non-loopback requests need the legacy Tailscale session
token (see below).

### Gmail & Calendar setup (local mode only — read-only)

1. In the [Google Cloud Console](https://console.cloud.google.com/),
   create a project and enable the **Gmail API** and **Google Calendar API**.
2. Under **APIs & Services > OAuth consent screen**, create an **External**
   app, add the scopes `https://www.googleapis.com/auth/gmail.readonly`
   and `https://www.googleapis.com/auth/calendar.readonly`, and add your
   Google account as a test user.
3. Under **APIs & Services > Credentials**, create an **OAuth client ID**
   (Web application) with authorized redirect URI
   `http://127.0.0.1:8000/api/auth/google/callback`.
4. Put the client ID and secret in `.env` as `GOOGLE_CLIENT_ID` and
   `GOOGLE_CLIENT_SECRET`.
5. Connect: `GET /api/auth/google/url`, open the returned `auth_url`,
   sign in, and approve the read-only permissions. Check status with
   `GET /api/auth/google/status`. Disconnect and revoke with
   `POST /api/auth/google/disconnect`.

In cloud mode these endpoints return **503** — per-user Gmail/Calendar
tokens are not built yet, and Jarvis will not silently fall back to
another user's mailbox.

## BYOK: bring your own Gemini key — design and security

**Decision: there is no server-key path at all.** An earlier design had
all users share the owner's `GEMINI_API_KEY`; that was replaced, because
a shared key means the owner pays for everyone's usage and one abusive
user can drain the quota or run up the bill. BYOK removes the cost and
abuse risk entirely: each user's calls are charged to their own free
Google AI Studio quota, and nobody can spend anyone else's.

- **Validation:** keys must look like a Gemini key (`AIza…` classic keys, or
  `AQ.…` auth keys issued by Google AI Studio since May 2026; ≥ 30 chars)
  before saving. `POST /api/auth/key/validate` calls Google's models
  list with the key — a read-only check, no generation call.
- **Encryption at rest:** the key is encrypted with Fernet
  (AES-128-CBC + HMAC) before storage. The Fernet key comes from
  `KEY_ENCRYPTION_KEY` if set, otherwise PBKDF2-HMAC-SHA256 derives one
  from `SESSION_SECRET` (200,000 iterations, fixed salt
  `jarvis-byok-v1`). Postgres stores it in a `BYTEA` column; local mode
  uses a `0600` file under the user's private namespace.
- **Never exposed:** the key is never logged, never returned by any
  endpoint, and never sent to the frontend except as a masked hint
  (last 4 characters). The only endpoints are `GET /api/auth/key/status`
  (`has_key` + `key_hint`), `POST /api/auth/key`, `POST
  /api/auth/key/validate`, `DELETE /api/auth/key`.
- **Per-user caps:** even with BYOK, each user is capped at 30 Gemini
  calls/hour and 100/day (env-configurable) as a runaway guard. The
  counter lives in Postgres in cloud mode, so it survives cold starts.
- **No key yet:** chat replies with a plain message — "add your Gemini
  key in Settings (Get one free at Google AI Studio)" — instead of a
  stack trace.

## Per-user isolation

Every user is identified by their Google `sub`. Internally, the
backend uses an opaque namespace `user_<sha256(sub)[:32]>` — no email or
PII in file paths or database keys. All data is scoped by that
namespace:

- **Postgres (cloud):** every table has a `user_ns` column and every
  query filters `WHERE user_ns = ?`. `PostgresUserStore` in
  `backend/app/core/store.py` implements notes, memories, reminders,
  BYOK key, chat history, action log, usage counters and wipe.
- **Files (local dev):** `data/users/<ns>/…`, `notes/users/<ns>/…`,
  per-user backup directories. The local owner maps to the historical
  top-level paths so existing local data keeps working.
- **Runtime:** the current user travels in a `ContextVar` set by the
  `require_user` dependency and read by tools/registry; confirmation
  pending actions carry the `user_sub`, so only the user who started an
  action can approve it; the audit log is filtered per user.
- **Chat history** is recorded per user (user + assistant turns) and
  the Companion loads it on sign-in (`GET /api/chat/history`), which is
  what makes cross-device chat sync work.

## Remote access from your phone (Tailscale) — legacy, local mode only

The cloud path replaces this. It remains only for local development
against a laptop backend:

1. Install [Tailscale](https://tailscale.com/download) on the laptop and
   on your phone, sign in with the same account, and enable MagicDNS and
   HTTPS certificates in the
   [Tailscale admin console](https://login.tailscale.com/admin/dns).
2. Start the backend bound to `127.0.0.1:8000`, then on the laptop run:
   ```powershell
   tailscale serve --https=443 http://127.0.0.1:8000
   ```
3. Generate a one-time pairing code on the laptop (from `backend/`):
   ```powershell
   python -m app.cli pair
   ```
4. On the phone, open the hosted PWA, go to **Settings > Legacy: laptop
   pairing (Tailscale)**, enter your laptop's Tailscale address
   (`https://<laptop>.<tailnet>.ts.net`) and the 6-digit code, and tap
   **Connect & Pair**. The session token is kept only in memory on the
   phone. Disconnect any time from Settings; the token can also be
   revoked with `POST /api/remote/session/revoke`.

The backend never listens on a public interface, and no Tailscale Funnel
or public port is used. Only the hosted PWA origin, localhost, and Chrome
extensions are accepted as browser origins.

## API reference

Base URL: `https://<your-vercel-domain>` in production,
`http://127.0.0.1:8000` for local dev. All AI/data endpoints require
authentication: in cloud mode a Google sign-in session (HttpOnly cookie
`jarvis_session` or `Authorization: Bearer <jwt>`); in local mode the
same JWT, or a Tailscale session token
(`Authorization: Bearer <token>` or `X-Session-Token`), or loopback.
`/health` is public and leaks no paths or per-user counts in cloud mode.
Unauthenticated requests get `401`.

| Endpoint | Description |
| --- | --- |
| `GET /health` | Health status. Returns status, version, config flags, reminder/memory counts, and the active tool list; no filesystem paths. In cloud mode the counts are 0 and no paths are exposed. |
| `POST /api/chat` | Chat with Gemini tool calling (your own key; 30/hour, 100/day per user). Body: `{"message": "..."}`. Without a saved key it replies with a plain "add your key" message. |
| `GET /api/auth/login` | Google sign-in: 302 redirect to Google (or `?format=json` → `{auth_url, state}`). | 
| `GET /api/auth/login/callback` | Google callback: verifies state + ID token, sets the session cookie, redirects to the Companion. |
| `GET /api/auth/me` | `{authenticated, email, name, cloud_mode, has_key, key_hint}`. |
| `POST /api/auth/logout` | Clears the session cookie. |
| `GET /api/auth/key/status`, `POST /api/auth/key`, `POST /api/auth/key/validate`, `DELETE /api/auth/key` | Your Gemini key: status (masked), save (encrypted), live-validate, delete. |
| `GET /api/chat/history?limit=` | Your chat history, oldest first — used to sync the Companion across devices. |
| `GET /api/tools` | List the 26 registered tools. |
| `GET /api/actions` | Audit log of recent actions (redacted). |
| `GET /api/confirm/pending`, `POST /api/confirm` | List and approve/deny pending actions. |
| `POST /api/extension/read-page` | Summarise text sent by the Chrome extension. |
| `GET/POST/DELETE /api/reminders`, `PATCH /api/reminders/{id}/complete` | Manage reminders. Complete marks one done; delete requires confirmation. |
| `GET/POST/DELETE /api/memories`, `GET /api/memories/status`, `POST /api/memories/toggle` | Manage user-approved memories; check or toggle memory on/off. |
| `GET /api/briefing` | On-demand daily briefing. |
| `GET /api/auth/google/url`, `GET /api/auth/google/callback`, `GET /api/auth/google/status`, `POST /api/auth/google/disconnect` | Google OAuth flow. |
| `GET /api/gmail/messages`, `POST /api/gmail/summarize` | Read-only Gmail. |
| `GET /api/calendar/events`, `POST /api/calendar/summarize` | Read-only Calendar. |
| `GET /api/browser/approved-domains`, `POST /api/browser/approve-domain`, `POST /api/browser/plan-action` | Browser automation allowlist and planning. |
| `GET /api/data/locations`, `GET /api/data/export`, `POST /api/data/clear`, `GET /api/data/backups`, `POST /api/data/backup`, `POST /api/data/restore` | Data export, wipe (confirmation-guarded), backup, restore. |
| `GET /api/demo/status`, `POST /api/demo/seed`, `POST /api/demo/reset` | Demo data lifecycle. |
| `POST /api/remote/pair/generate`, `POST /api/remote/pair/exchange`, `GET /api/remote/session/status`, `POST /api/remote/session/revoke`, `POST /api/remote/stop` | Remote pairing and control. |

Example:

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What reminders do I have today?"}'
```

## Testing

```powershell
.\.venv\Scripts\pytest backend/tests -q
```

Run it from the repo root (the virtual environment lives there too).
On macOS/Linux use `.venv/bin/pytest backend/tests -q`.

**179 tests pass and 22 Windows-only tests are skipped on Linux**
(201 total across 22 test files, plus `conftest.py`); on a Windows
laptop the skipped tests run. The suite covers routes, confirmation
lifecycle, security (path traversal, file-size caps, extension checks),
DNS rebinding and referer defenses, rate limiting, Google OAuth, Gmail
and Calendar read-only behaviour, search and briefing safeguards, remote
authentication. `backend/tests/test_cloud_byok.py`
(19 tests) covers the cloud path specifically: cloud-mode 401s,
health-leak check, login URL/scopes, callback → session → `/auth/me`,
state-mismatch rejection, BYOK save/masked/encrypted-at-rest/delete,
chat-without-key prompt, chat-with-key using the user's key and
recording history, per-user isolation (reminders, memories, notes,
export, disk namespace), per-user usage caps (429), key validation,
Gmail 503 in cloud mode, local-only tools refusing in cloud mode, the
store factory choosing Postgres when `DATABASE_URL` is set, the Vercel
entrypoint/config, and `PostgresUserStore` scoping with a fake cursor.
The Postgres store was also verified against a real embedded Postgres
server (see "Known limitations" for what that found). A Linux CI workflow is provided in
`.github/workflows/ci.yml` (install, compile check,
`node --check frontend/landing/landing.js`,
`python backend/scripts/prepare_static.py` with a check that the
committed `frontend/public/` output is in sync, then
`pytest backend/tests -q`).

## Security

- In cloud mode, sign-in is mandatory for AI/data endpoints and the
  backend serves only the Vercel domain and `FRONTEND_URL` (host and
  referer validated). Local mode binds to `127.0.0.1` by default;
  non-loopback binding without `ALLOW_REMOTE_ACCESS=true` fails startup.
- Host-header and referer validation (DNS rebinding defense); request
  body capped at 2 MB; auth failures rate-limited (5 per 60 seconds).
- All file access is sandboxed to configured directories with symlink
  and traversal checks; `read_text_file` accepts only allowlisted text
  extensions, including extension-less files only when the exact
  filename is allowlisted (`.env.example`, `.gitignore`).
- No arbitrary shell or Python execution. App control uses a hardcoded
  allowlist; screenshots and destructive actions need confirmation.
- Confirmation IDs carry 128 bits of entropy (`secrets.token_hex(16)`),
  expire after `CONFIRMATION_TIMEOUT_SECONDS`, and are single-use.
- Secrets are never stored in memory, logs, or the browser. Audit logs
  redact keys, tokens, emails, and card numbers. Search queries are
  screened before being sent to any provider. User Gemini keys are
  stored encrypted (Fernet) and only ever shown masked; Google passwords
  are never handled by Jarvis — sign-in happens on Google's page.
- Per-user isolation: all data is namespaced by `user_<sha256(sub)[:32]>`
  (Postgres `WHERE user_ns = ?` on every query; per-user files in local
  mode). Confirmation pending actions carry the `user_sub`, so only the
  user who started an action can approve it.
- Gmail and Calendar are read-only by scope and by code — no write
  tools exist for them.

## Troubleshooting

| Problem | Cause | Fix |
| --- | --- | --- |
| Chat replies "add your Gemini key" | No key saved for your account | Settings → Your Gemini key → paste a key from [Google AI Studio](https://aistudio.google.com/) → Save. |
| `401 Sign-in required` (cloud) | Not signed in, or session expired (24 h) | Sign in with Google from Settings. |
| `429` from chat | Over the per-user cap (30/hour, 100/day) | Wait, or raise `GEMINI_CALLS_PER_USER_*` in Vercel. |
| Gmail/Calendar returns 503 in cloud | Not built for cloud yet | Use the local-mode backend for Gmail/Calendar, or wait for per-user tokens. |
| `GEMINI_API_KEY is not configured` | Old local-mode error | No longer used: the server key is ignored. Save your own key in Settings instead. |
| `403 Forbidden: Host not authorized` | Accessed via an unauthorised hostname | Use `http://127.0.0.1:8000` or `http://localhost:8000`. |
| `403 Forbidden: Origin not authorized` | Request came from an unauthorised origin | Only localhost, `chrome-extension://*`, and the configured PWA origin are allowed. |
| `401 Remote authentication required` | Remote request without a valid session token | Pair from the laptop (`cd backend` then `python -m app.cli pair`) and reconnect from the phone. |
| `413 Request Entity Too Large` | Request body over the 2 MB cap | Reduce input or page-text size. |
| `429 Too Many Requests` | Too many auth/confirmation failures | Wait 60 seconds, then retry. |
| Google disconnected / token revoked | Token revoked in Google account settings | Reconnect via `GET /api/auth/google/url`. |
| Web search reports it is not configured | `SEARCH_API_KEY` missing | Set the key for your `SEARCH_PROVIDER` in `.env`. |

## Project structure

The repo is split into two top-level folders: `frontend/` holds everything
a browser loads, and `backend/` holds the local FastAPI server and its
tests. The repo root stays small — `README.md`, `.env.example`,
`.gitignore`, `.vercelignore`, and `vercel.json` only (plus the usual
`.github/` workflows).

```
Jarvis/
├── frontend/
│   ├── landing/                 # Vision landing page — the HOMEPAGE (/)
│   │   ├── index.html           # 3D hero, scroll + pointer effects
│   │   ├── landing.css
│   │   └── landing.js
│   ├── mobile/                  # Mobile PWA companion (/mobile/, alias /companion/)
│   │   ├── config.js            # API base URL ("" = same origin; override for a separate backend)
│   │   └── icons/               # icon-192.png, icon-512.png (manifest + service worker)
│   ├── extension/               # Chrome extension, Manifest V3 (activeTab, scripting)
│   │   └── icons/               # icon16.png, icon48.png, icon128.png (manifest.json)
│   └── public/                  # Static build output for the hosted site
│       ├── index.html           # landing page at / (copied from frontend/landing/)
│       ├── mobile/              # companion at /mobile/ (copied from frontend/mobile/)
│       └── landing/             # (generated — run backend/scripts/prepare_static.py;
│                                #  the committed output must stay in sync, checked by CI)
├── api/
│   ├── index.py                 # Vercel serverless entrypoint (exposes `app`)
│   └── requirements.txt         # Vercel function dependencies (copy of backend's)
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, origin/host validation, lifespan
│   │   ├── cli.py               # CLI helpers (e.g. `python -m app.cli pair`)
│   │   ├── api/
│   │   │   ├── routes.py        # All API endpoints (incl. /auth/login, /auth/key, /chat/history)
│   │   │   └── schemas.py       # Pydantic request/response models
│   │   ├── core/                # config, security, confirmation, remote auth,
│   │   │                        # Google OAuth + login, session JWT, BYOK encryption,
│   │   │                        # per-user store (file + Postgres), usage limits,
│   │   │                        # data manager, logger
│   │   ├── services/            # Gemini agent service (BYOK), extension service
│   │   └── tools/               # 26 registered tools (workspace, notes, system,
│   │                            # screenshots, reminders, memory, search, briefing,
│   │                            # Gmail, Calendar, browser automation)
│   ├── tests/                   # 179 passing tests across 22 test files (22 skipped on Linux)
│   ├── scripts/
│   │   └── prepare_static.py    # Builds frontend/public/ from frontend/mobile/,
│   │                            # frontend/landing/
│   └── requirements.txt         # Python dependencies
├── .env.example                 # Environment variable template (no real secrets)
├── .gitignore
├── .vercelignore
└── vercel.json                  # Static hosting + /api/* → serverless function, maxDuration 10
```

## Known limitations

- **Vercel serverless:** no persistent filesystem (all data in Neon
  Postgres), 10-second function timeout on Hobby (slow multi-step
  Gemini chats can hit it), cold starts, no background jobs or push
  notifications, and in-memory confirmation state can be lost on a
  cold start (approve again). See "Vercel limits" above.
- Windows-only tools (app control, screenshots, system metrics, OS
  credential store) report an unsupported-platform error on macOS/Linux
  and "not available in cloud mode" on Vercel — they need a physical
  laptop, which the cloud does not have.
- Gmail and Calendar are read-only and **not available in cloud mode
  yet** (503); they work only in local mode with the laptop owner's
  single Google connection. Jarvis cannot send mail, delete messages,
  or create/edit events.
- Browser automation is limited to approved domains and low-risk
  actions; it never submits forms, checks out, or completes quizzes.
- Briefings, search, and summaries run on demand only; there are no
  background jobs or notifications.
- Rotating `SESSION_SECRET` or `KEY_ENCRYPTION_KEY` invalidates sessions
  and stored BYOK keys (users re-enter their key); choose them once and
  keep them in Vercel.
- **Not yet deployed/tested live:** the Vercel + Neon path has been
  tested locally (full suite green; the Postgres store verified against
  a real embedded Postgres — that check found and fixed two bugs: TEXT
  columns returned as bytes on a non-UTF-8 test database, and BYTEA
  keys needing an exemption from that decode) but no live Vercel
  deployment or Neon project has been created yet, so cold-start
  behaviour, the 10-second limit against real Gemini latency, and Neon
  free-tier pooling limits are still unproven in production.

## Uninstall

1. Delete your Gemini key: Settings → Your Gemini key → **Delete key**
   (or `DELETE /api/auth/key`).
2. Disconnect Google: `POST /api/auth/google/disconnect`, and remove
   Jarvis at [Google Account Permissions](https://myaccount.google.com/permissions).
3. Wipe your data: `POST /api/data/clear` with
   `{"confirm": true, "confirmation_text": "DELETE ALL DATA"}` (deletes
   your rows in Postgres, or your per-user files locally).
4. Remove the Chrome extension at `chrome://extensions/`.
5. Delete the project directory and virtual environment, and remove any
   `Jarvis_Google_OAuth` entry from Windows Credential Manager.
