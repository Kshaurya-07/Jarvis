# Jarvis — One companion. Every device.

**Live:** [https://jarvis-kumar-shaurya.vercel.app/](https://jarvis-kumar-shaurya.vercel.app/) — landing page at `/`, the app at `/mobile/`

## What it is

Jarvis is a personal AI assistant that lives entirely in the cloud. Open the web app, sign in with Google, add your own free Gemini API key, and start chatting. Your chats, notes, memories, and reminders are stored per user in the cloud, so the same account shows the same state on your laptop, phone, or tablet.

There is no shared server API key: every user brings their own Gemini key (free from Google AI Studio), so nobody can spend anyone else's quota and the owner has no API bill.

## Features

- **Cloud-first** — Google sign-in, your own Gemini key, per-user data in Postgres (Neon). Nothing runs on your laptop.
- **Chat with tool calling** — Gemini (default `gemini-3.8-flash`, called with *your* key) uses tools over up to 3 turns, with your conversation history sent along so it remembers the thread.
- **26 tools** — files and notes, reminders, user-approved memory, web search, daily briefing, read-only Gmail and Calendar summaries (local mode only), and browser automation on domains you approve.
- **Companion PWA** — the app at `/mobile/` (also `/companion/`): chat, voice input, stop/abort control, a 3-step onboarding wizard, synced chat history, and an installable app shell.
- **Landing page** — a black-hole themed homepage at `/` with live backend status.
- **Confirmations and audit log** — state-changing actions need your approval first, and every action is written to a per-user audit log.
- **Chrome extension** — Manifest V3, `activeTab` and `scripting` permissions only. Reads the page you choose and summarises it. Talks to a local backend only; it does not use the cloud backend yet.
- **Safety by design** — Jarvis never submits forms, quizzes, exams, or purchases, and never asks you to share passwords or API keys in chat.

## How it works for a new user

1. **Open the app** — the Companion at `/mobile/` (or the landing page at `/`, then "Open app").
2. **Sign in with Google** — one tap. Google handles sign-in; no password is typed into Jarvis.
3. **Add your free Gemini key** — Settings → Your Gemini key. Get one free from [Google AI Studio](https://aistudio.google.com/) (Get API key → copy → paste → Save). The key is encrypted on the server and never shown again.
4. **Start chatting** — ask questions, take notes, set reminders, get a briefing. Sign in on another device and everything is there.

## Architecture

```
Browser (landing + Companion PWA)
        │
        ▼
Vercel — one project
├── Static frontend  (frontend/public, outputDirectory)
└── Serverless API   (api/index.py → FastAPI, /api/*)
        │
        ▼
Neon Postgres — per-user data (notes, memories, reminders,
chat history, encrypted Gemini keys, usage counters)
        │
        ▼
Google Gemini — called with each user's own key (BYOK)
```

- **Frontend and backend are one Vercel project.** The landing page and Companion are static; the FastAPI backend runs as a serverless function under `/api/*`.
- **State lives in Postgres, not on the server.** Vercel serverless has no persistent filesystem, so all per-user data is in Neon Postgres. Tables are created automatically on first use.
- **Sign-in is Google OAuth 2.0** (`openid`, `email`, `profile`) with PKCE. Sessions are stateless JWTs (24 hours) in an HttpOnly cookie, so sign-in survives cold starts.
- **BYOK:** each user's Gemini key is encrypted with Fernet before storage. The encryption key comes from `KEY_ENCRYPTION_KEY` if set, otherwise it is derived from `SESSION_SECRET`. Keys are never logged, never returned by any endpoint, and shown only as a masked hint (last 4 characters).

## Tech stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12, FastAPI, Uvicorn |
| AI | Google Gemini (`gemini-3.8-flash` by default), per-user key |
| Auth | Google OAuth 2.0 (PKCE), HS256 JWT sessions |
| Database | Neon Postgres (per-user rows, `user_ns` scoped) |
| Hosting | Vercel — static frontend + serverless API |
| Frontend | Vanilla JS + CSS, PWA (service worker, manifest) |
| Search | Tavily (default), Google Custom Search, or Brave |
| Tests | pytest — 196 passing, 22 skipped (Windows-only, on Linux) |

## Deploy your own copy

### 1. Create the database (Neon, free tier)

1. At [neon.tech](https://neon.tech), create a project and a database (e.g. `jarvis`).
2. Copy the connection string — use the **pooled** connection string if Neon offers it (serverless functions open many short-lived connections; pooling keeps that healthy).

### 2. Create the Google OAuth client (sign-in)

1. In the [Google Cloud Console](https://console.cloud.google.com/), create a project. Sign-in itself needs no APIs enabled.
2. Under **APIs & Services > OAuth consent screen**, create an **External** app with the scopes `openid`, `email`, `profile`.
3. Under **APIs & Services > Credentials**, create an **OAuth client ID** (**Web application**) with the authorized redirect URI `https://<your-vercel-domain>/api/auth/login/callback`.
4. Copy the client ID and client secret — they go in Vercel env vars, never in the repo.

### 3. Import the project in Vercel

1. In Vercel, **Add New > Project**, import this repo.
2. Framework preset: **Other** (the repo sets `outputDirectory: frontend/public` in `vercel.json`; no build command is needed).
3. Set these **Environment Variables** (Production):

   | Variable | Value |
   | --- | --- |
   | `CLOUD_MODE` | `true` |
   | `DATABASE_URL` | The Neon connection string from step 1 |
   | `SESSION_SECRET` | A long random string (32+ chars) — `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
   | `KEY_ENCRYPTION_KEY` | Optional Fernet key for stored Gemini keys — `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` (if unset, one is derived from `SESSION_SECRET`) |
   | `GOOGLE_CLIENT_ID` | From step 2 |
   | `GOOGLE_CLIENT_SECRET` | From step 2 |
   | `GOOGLE_LOGIN_REDIRECT_URI` | `https://<your-vercel-domain>/api/auth/login/callback` |
   | `FRONTEND_URL` | `https://<your-vercel-domain>` |
   | `SEARCH_API_KEY` | Optional, for web search |

   Rotating `SESSION_SECRET` signs everyone out and makes previously stored BYOK keys undecryptable (users just re-enter their key). Rotating `KEY_ENCRYPTION_KEY` has the same effect on stored keys only.
4. Deploy. Check `https://<your-vercel-domain>/api/health` (200), then open `/mobile/`, sign in with Google, add a Gemini key, and chat.

### 4. Get a free Gemini key (every user, in the app)

1. Open [Google AI Studio](https://aistudio.google.com/) → **Get API key** → **Create API key**.
2. In Jarvis: Settings → Your Gemini key → paste → **Save key**. **Validate** checks the key against Google before you chat. Free-tier quotas apply to your own Google account, not to the owner's.

## Local development

No cloud account needed. Local mode uses per-user files and loopback trust:

```bash
git clone https://github.com/Kshaurya-07/Jarvis.git
cd Jarvis
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/` for the landing page and `http://127.0.0.1:8000/mobile/` for the Companion. Check health with `GET http://127.0.0.1:8000/health`. In local mode sign-in is optional: loopback requests act as the local owner. Google sign-in locally needs `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `SESSION_SECRET` in `.env`.

Copy `.env.example` to `.env` at the repo root — never commit a real `.env` (it is gitignored). All settings have defaults in `backend/app/core/config.py`.

## Usage limits

| Limit | What it means |
| --- | --- |
| **30 Gemini calls/hour, 100/day per user** | A runaway guard, even with BYOK. Configurable via `GEMINI_CALLS_PER_USER_PER_HOUR` / `GEMINI_CALLS_PER_USER_PER_DAY`. Web search has the same per-user caps (`SEARCH_CALLS_PER_USER_*`). |
| **10-second function timeout (Vercel Hobby)** | `vercel.json` sets `maxDuration: 10`, the Hobby maximum. A chat turn needing several Gemini tool calls can exceed it on a cold start; the app shows a plain error and you retry. |
| **Cold starts** | The first request after idle can take a few seconds (Python + FastAPI boot). Sessions and data are unaffected — they live in JWTs and Postgres, not memory. |
| **No background jobs** | No daemons, no push notifications, no scheduled reminders. Reminders are stored and shown when you open the app. |
| **No persistent filesystem** | Files written on Vercel disappear on the next invocation. All user data lives in Postgres. If `DATABASE_URL` is unset in cloud mode, the backend still boots but warns that data will not persist. |

## Security and privacy

- In cloud mode, sign-in is mandatory for all AI and data endpoints; unauthenticated requests get **401**. `/health` is public and exposes no per-user data.
- All data is namespaced per Google account (`user_<sha256(sub)[:32]>`); every Postgres query filters by that namespace, so you only ever see your own data.
- Your Gemini key is encrypted at rest (Fernet), never logged, never returned by any endpoint, and shown only masked.
- File access is sandboxed to configured directories, with symlink and traversal checks. No arbitrary shell or Python execution.
- Confirmation IDs carry 128 bits of entropy, expire after 5 minutes, and are single-use.
- Audit logs redact keys, tokens, emails, and card numbers. Search queries are screened before being sent to a provider.
- Passwords, API keys, card numbers, and tokens are refused when saving a memory.
- Gmail and Calendar are read-only by scope and by code — no write tools exist for them.

## API

Base URL: `https://<your-vercel-domain>` in production, `http://127.0.0.1:8000` for local dev. All AI/data endpoints require authentication in cloud mode (Google sign-in session: HttpOnly cookie `jarvis_session` or `Authorization: Bearer <jwt>`). 52 endpoints in total.

| Endpoint | Description |
| --- | --- |
| `GET /health` | Public health status. |
| `POST /api/chat` | Chat with Gemini tool calling (your own key). Body: `{"message": "..."}`. Without a saved key it replies with a plain "add your key" message. |
| `GET /api/auth/login`, `GET /api/auth/login/callback` | Google sign-in (PKCE) and callback. |
| `GET /api/auth/me` | `{authenticated, email, name, cloud_mode, has_key, key_hint}`. |
| `POST /api/auth/logout` | Clears the session cookie. |
| `GET /api/auth/key/status`, `POST /api/auth/key`, `POST /api/auth/key/validate`, `DELETE /api/auth/key` | Your Gemini key: status (masked), save (encrypted), live-validate, delete. |
| `GET /api/chat/history?limit=` | Your chat history, oldest first — syncs the Companion across devices. |
| `GET /api/tools` | List the 26 registered tools. |
| `GET /api/actions` | Audit log of recent actions (redacted). |
| `GET /api/confirm/pending`, `POST /api/confirm` | List and approve/deny pending actions. |
| `GET/POST/DELETE /api/reminders`, `PATCH /api/reminders/{id}/complete` | Manage reminders. |
| `GET/POST/DELETE /api/memories`, `GET /api/memories/status`, `POST /api/memories/toggle` | Manage user-approved memories. |
| `GET /api/briefing` | On-demand daily briefing. |
| `GET /api/data/export`, `POST /api/data/clear` | Export your data; confirmation-guarded wipe. |
| `POST /api/extension/read-page` | Summarise text sent by the Chrome extension. |
| `GET /api/demo/status`, `POST /api/demo/seed`, `POST /api/demo/reset` | Demo data lifecycle (API only — there is no demo page or demo UI). |

```bash
curl https://jarvis-kumar-shaurya.vercel.app/api/health
curl -X POST https://jarvis-kumar-shaurya.vercel.app/api/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-jwt>" \
  -d '{"message": "What reminders do I have today?"}'
```

## Project structure

```
Jarvis/
├── frontend/
│   ├── landing/            # Landing page — the homepage (/)
│   ├── mobile/             # Companion PWA (/mobile/, alias /companion/)
│   ├── extension/          # Chrome extension, Manifest V3
│   └── public/             # Static build output (generated by
│                           # backend/scripts/prepare_static.py; CI checks it is in sync)
├── api/
│   ├── index.py            # Vercel serverless entrypoint (exposes `app`)
│   └── requirements.txt    # Vercel function dependencies
├── backend/
│   ├── app/
│   │   ├── main.py         # FastAPI app, origin/host validation
│   │   ├── api/            # All API endpoints (routes.py, schemas.py)
│   │   ├── core/           # config, security, confirmation, Google OAuth,
│   │   │                   # session JWT, BYOK encryption, per-user store
│   │   │                   # (file + Postgres), usage limits, data manager
│   │   ├── services/       # Gemini agent service (BYOK), extension service
│   │   └── tools/          # 26 registered tools
│   ├── tests/              # pytest suite
│   ├── scripts/
│   │   └── prepare_static.py
│   └── requirements.txt
├── .env.example            # Environment variable template (no real secrets)
├── .gitignore
├── .vercelignore
└── vercel.json             # Static hosting + /api/* → serverless function, maxDuration 10
```

## Testing

```bash
pytest backend/tests -q
```

Run from the repo root. **196 tests pass, 22 skipped** (Windows-only tests skipped on Linux). The suite covers routes, confirmation lifecycle, security (path traversal, file-size caps), rate limiting, Google OAuth, BYOK (cloud-mode 401s, encryption at rest, per-user isolation, usage caps), Gmail/Calendar read-only behaviour, search and briefing safeguards, and remote authentication. A Linux CI workflow (`.github/workflows/ci.yml`) runs a compile check, `node --check` on the frontend JS, a `prepare_static.py` sync check, and the full test suite.

## Known limitations

- **Vercel serverless:** no persistent filesystem, 10-second function timeout on Hobby, cold starts, no background jobs or push notifications, and in-memory confirmation state can be lost on a cold start (approve again).
- **Gmail and Calendar are not available in cloud mode** (endpoints return 503). They work only in local mode with the laptop owner's single Google connection; per-user Gmail/Calendar tokens are not built yet.
- **Windows-only tools** (app launch, screenshots, system status) need a physical laptop. They report "not available in cloud mode" on Vercel and an unsupported-platform error on macOS/Linux.
- **Browser automation** is limited to approved domains and low-risk actions; it never submits forms, checks out, or completes quizzes.
- **Chrome extension** talks to a local backend only; it does not use the cloud backend yet.
- **No push notifications.** Reminders are stored and shown when you open the app.
- Rotating `SESSION_SECRET` or `KEY_ENCRYPTION_KEY` invalidates sessions and stored BYOK keys (users re-enter their key).

## Troubleshooting

| Problem | Cause | Fix |
| --- | --- | --- |
| Chat replies "add your Gemini key" | No key saved for your account | Settings → Your Gemini key → paste a key from [Google AI Studio](https://aistudio.google.com/) → Save. |
| `401 Sign-in required` (cloud) | Not signed in, or session expired (24 h) | Sign in with Google from Settings. |
| `429` from chat | Over the per-user cap (30/hour, 100/day) | Wait, or raise `GEMINI_CALLS_PER_USER_*` in Vercel. |
| Gmail/Calendar returns 503 in cloud | Not built for cloud yet | Use the local-mode backend for Gmail/Calendar. |
| Web search reports it is not configured | `SEARCH_API_KEY` missing | Set the key for your `SEARCH_PROVIDER` in `.env` / Vercel. |

## Author

**Kumar Shaurya**

- GitHub: [https://github.com/Kshaurya-07](https://github.com/Kshaurya-07)
