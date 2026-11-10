# Jarvis — One companion. Every device.

Jarvis is a personal AI companion designed to help across your paired devices —
not just on one laptop. Give a command on your phone, your laptop, or your
tablet, and choose where it should happen: from a phone, “Laptop par yeh file
kholo aur summarize karo”; from a laptop, “Mere phone par reminder set karo”;
from a tablet, “Laptop par yeh website kholo.” Jarvis understands the request,
identifies the target device, explains what it plans to do, performs only the
actions that are permitted, and reports the result back to you.

That cross-device vision is the destination, not the starting point. Today,
phone-to-laptop commands work when your phone is paired with your laptop over
your private Tailscale network; the other directions are labelled honestly in
the status table below and on the [vision landing page](landing/index.html).

Under the hood, a FastAPI backend on your own laptop talks to Google Gemini,
which can call 26 tools: read and search your files and notes, control
approved Windows apps, take screenshots, manage reminders and memory, search
the web, summarise read-only Gmail and Calendar, and automate low-risk browser
actions on domains you approve. It ships with a Chrome extension
(Manifest V3) and a mobile PWA companion.

Local-first by design: the backend binds to `127.0.0.1` by default, all data
lives on your laptop, and there is no telemetry, no background sync, and no
cloud relay.

## What works today — and what does not yet

| Capability | Status | Notes |
|---|---|---|
| Phone → laptop commands (chat, tools, voice) | Available | Paired over Tailscale with a one-time 6-digit code. |
| Voice input, editable transcript, spoken replies | Available | Browser speech recognition; raw audio stays on-device. |
| Read-only Gmail & Calendar summaries | Requires permission | Google sign-in with read-only scopes. |
| Choosing between several paired devices | In development | One laptop can be paired at a time today. |
| Laptop → phone actions (e.g. reminders on your phone) | Planned | Needs a phone companion that can receive actions. |
| Tablet as a command source | Planned | The companion web app opens in a tablet browser; a dedicated flow is planned. |
| Wi-Fi, volume & brightness controls | Planned | Interfaces exist in `app/tools/future_interfaces.py`; the features are not implemented. |
| Windows-only tools (app launch, screenshots, system status) | Available — Windows | On macOS/Linux these report “unsupported”. |

Jarvis never submits forms, quizzes, exams, or purchases, and it never asks you
to share passwords or API keys in chat.

## Features

- **Chat with tool calling** — Gemini (default `gemini-2.5-flash`) calls
  tools over up to 5 turns, with a plain-language fallback when no API key
  is configured.
- **Files and notes** — `list_files`, `read_text_file` (sandboxed to
  `workspace/`), `create_note`, `search_notes`. Paths are resolved and
  checked against the configured directory; traversal, symlink escapes,
  null bytes, and NTFS alternate data streams are rejected.
- **Windows companion** — `open_application` (allowlist only: notepad,
  calculator, paint, explorer, cmd), `get_battery_status`,
  `get_storage_status`, `get_memory_status`, `capture_screenshot` and
  `analyze_screenshot`. Windows-only tools report an unsupported-platform
  error on macOS/Linux.
- **Reminders and memory** — reminders and explicitly approved memories
  stored locally in `data/`. Memory never silently absorbs chat history,
  and passwords, API keys, card numbers, and tokens are refused on save.
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
- **Mobile PWA companion** — chat, voice input, stop/abort control,
  pending-action approvals, and an audit feed, served from the backend at
  `/mobile/`. Command history is opt-in and off by default.
- **Remote access via Tailscale Serve** — pair your phone once with a
  6-digit code generated on the laptop (5-minute expiry, single use, 5
  failed attempts per 60 seconds rate-limited). The resulting session token
  lives only in memory on the phone. Remote requests require a valid
  session token on every endpoint except `/health` and the pairing
  endpoints; the backend stays bound to `127.0.0.1`.
- **Confirmations** — state-changing tools (open app, screenshot, delete
  reminder, and others) return a one-time confirmation ID (128-bit entropy)
  that you approve or deny via `POST /api/confirm` before anything runs.
- **Data controls** — export, checksum-verified local backups, restore,
  and a confirmation-guarded wipe (`POST /api/data/clear`). Every action
  is written to an audit log with keys, tokens, emails, and card numbers
  redacted.
- **Demo mode** — a self-contained fictional demo page at `/demo/` with
  `/api/demo/status`, `/api/demo/seed`, and `/api/demo/reset`. Seeded items
  are tagged `[DEMO]` and reset removes only those items.

## Requirements

- Python 3.12 (or newer 3.x), pip
- Windows 10/11 64-bit for the full companion experience (app control,
  screenshots, system metrics, OS credential store). The core backend,
  workspace tools, search, briefing, Google tools, PWA, and extension also
  run on macOS/Linux; Windows-only tools report an unsupported-platform
  error there.
- Google Chrome 115+ or Edge 115+ for the extension; a modern mobile
  browser for the PWA.
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)
  for live chat (optional — Jarvis runs offline without one).
- A search API key (Tavily, Google Custom Search, or Brave) for web
  search (optional).

## Quick start

```powershell
git clone https://github.com/Kshaurya-07/Jarvis.git
cd Jarvis
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and set at least `GEMINI_API_KEY`, then start the server:

```powershell
.\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

On macOS/Linux use `python3 -m venv .venv`,
`source .venv/bin/activate`, `cp .env.example .env`, and
`uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`.

Open `http://127.0.0.1:8000/` (redirects to `/mobile/`) or
`http://127.0.0.1:8000/demo/`. Check health with
`GET http://127.0.0.1:8000/health`.

### Chrome extension

1. Open `chrome://extensions/` and enable **Developer mode**.
2. Click **Load unpacked** and select the `extension/` folder.
3. Pin **Jarvis Local Companion** to the toolbar and click **Read this page**
   on a tab you want summarised.

### Mobile PWA

With the backend running, open `http://127.0.0.1:8000/mobile/` in a
browser and install it from the address bar (Chrome/Edge) or
**Share > Add to Home Screen** (iOS Safari). The PWA caches the app shell
for fast startup; API calls always go to the live backend.

## Configuration

Copy `.env.example` to `.env`. Never commit a real `.env` — it is
gitignored. All settings have defaults in `app/core/config.py`.

| Variable | Default | Notes |
| --- | --- | --- |
| `GEMINI_API_KEY` | — | Required for live AI chat. Get one at Google AI Studio. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model used for chat and tool calling. |
| `HOST` | `127.0.0.1` | Binding to anything else requires `ALLOW_REMOTE_ACCESS=true`. |
| `PORT` | `8000` | Backend port. |
| `ENVIRONMENT` | `development` | `development` or `production`. |
| `LOG_LEVEL` | `INFO` | Log level. |
| `ALLOW_REMOTE_ACCESS` | `false` | Must stay `false` unless you deliberately expose the backend. |
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

## Google OAuth setup (read-only Gmail & Calendar)

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

## Remote access from your phone (Tailscale)

1. Install [Tailscale](https://tailscale.com/download) on the laptop and
   on your phone, sign in with the same account, and enable MagicDNS and
   HTTPS certificates in the
   [Tailscale admin console](https://login.tailscale.com/admin/dns).
2. Start the backend bound to `127.0.0.1:8000`, then on the laptop run:
   ```powershell
   tailscale serve --https=443 http://127.0.0.1:8000
   ```
3. Generate a one-time pairing code on the laptop:
   ```powershell
   python -m app.cli pair
   ```
4. On the phone, open the hosted PWA, go to **Settings > Private
   Tailscale Connection**, enter your laptop's Tailscale address
   (`https://<laptop>.<tailnet>.ts.net`) and the 6-digit code, and tap
   **Connect & Pair**. The session token is kept only in memory on the
   phone. Disconnect any time from Settings; the token can also be
   revoked with `POST /api/remote/session/revoke`.

The backend never listens on a public interface, and no Tailscale Funnel
or public port is used. Only the hosted PWA origin, localhost, and Chrome
extensions are accepted as browser origins.

## API reference

Base URL: `http://127.0.0.1:8000`. Remote requests require a valid
session token (`Authorization: Bearer <token>` or `X-Session-Token`),
except `/health` and the pairing endpoints.

| Endpoint | Description |
| --- | --- |
| `GET /health` | Health status. Returns status, version, and tool counts; no filesystem paths. |
| `POST /api/chat` | Chat with Gemini tool calling. Body: `{"message": "..."}`. |
| `GET /api/tools` | List the 26 registered tools. |
| `GET /api/actions` | Audit log of recent actions (redacted). |
| `GET /api/confirm/pending`, `POST /api/confirm` | List and approve/deny pending actions. |
| `POST /api/extension/read-page` | Summarise text sent by the Chrome extension. |
| `GET/POST/DELETE /api/reminders` | Manage reminders. Delete requires confirmation. |
| `GET/POST/DELETE /api/memories` | Manage user-approved memories. |
| `GET /api/briefing` | On-demand daily briefing. |
| `GET /api/auth/google/url`, `GET /api/auth/google/callback`, `GET /api/auth/google/status`, `POST /api/auth/google/disconnect` | Google OAuth flow. |
| `GET /api/gmail/messages`, `POST /api/gmail/summarize` | Read-only Gmail. |
| `GET /api/calendar/events`, `POST /api/calendar/summarize` | Read-only Calendar. |
| `GET/POST /api/browser/approved-domains`, `POST /api/browser/plan-action` | Browser automation allowlist and planning. |
| `GET /api/data/locations`, `GET /api/data/export`, `POST /api/data/clear`, `GET/POST /api/data/backups`, `POST /api/data/restore` | Data export, wipe (confirmation-guarded), backup, restore. |
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
.\.venv\Scripts\pytest -v
```

**181 tests across 21 test files** (plus `conftest.py`). On Linux,
159 pass and 22 Windows-only tests are skipped
(`pytest.mark.skipif(sys.platform != "win32")`); on a Windows laptop
those tests run. The suite covers routes, confirmation lifecycle,
security (path traversal, file-size caps, extension checks), DNS
rebinding and referer defenses, rate limiting, Google OAuth, Gmail and
Calendar read-only behaviour, search and briefing safeguards, remote
authentication, and the demo flow. A Linux CI workflow is provided in
`.github/workflows/ci.yml` (install, compile check, `pytest tests -q`).

## Security

- Binds to `127.0.0.1` by default; non-loopback binding without
  `ALLOW_REMOTE_ACCESS=true` fails startup.
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
  screened before being sent to any provider.
- Gmail and Calendar are read-only by scope and by code — no write
  tools exist for them.

## Troubleshooting

| Problem | Cause | Fix |
| --- | --- | --- |
| `GEMINI_API_KEY is not configured` | Missing or placeholder key in `.env` | Add a key from Google AI Studio. Jarvis runs offline until then. |
| `403 Forbidden: Host not authorized` | Accessed via an unauthorised hostname | Use `http://127.0.0.1:8000` or `http://localhost:8000`. |
| `403 Forbidden: Origin not authorized` | Request came from an unauthorised origin | Only localhost, `chrome-extension://*`, and the configured PWA origin are allowed. |
| `401 Remote authentication required` | Remote request without a valid session token | Pair from the laptop (`python -m app.cli pair`) and reconnect from the phone. |
| `413 Request Entity Too Large` | Request body over the 2 MB cap | Reduce input or page-text size. |
| `429 Too Many Requests` | Too many auth/confirmation failures | Wait 60 seconds, then retry. |
| Google disconnected / token revoked | Token revoked in Google account settings | Reconnect via `GET /api/auth/google/url`. |
| Web search reports it is not configured | `SEARCH_API_KEY` missing | Set the key for your `SEARCH_PROVIDER` in `.env`. |

## Project structure

```
Jarvis/
├── app/
│   ├── main.py                  # FastAPI app, origin/host validation, lifespan
│   ├── cli.py                   # CLI helpers (e.g. `python -m app.cli pair`)
│   ├── api/
│   │   ├── routes.py            # All API endpoints
│   │   └── schemas.py           # Pydantic request/response models
│   ├── core/                    # config, security, confirmation, remote auth,
│   │                            # Google OAuth, data manager, demo manager, logger
│   ├── services/                # Gemini agent service, extension service
│   └── tools/                   # 26 registered tools (workspace, notes, system,
│                                # screenshots, reminders, memory, search, briefing,
│                                # Gmail, Calendar, browser automation)
├── demo/                        # Fictional local demo page (/demo/)
├── extension/                   # Chrome extension, Manifest V3 (activeTab, scripting)
├── mobile/                      # Mobile PWA companion (/mobile/)
├── public/                      # Static build output for the hosted PWA
├── scripts/prepare_static.py    # Builds public/ from mobile/ and demo/
├── tests/                       # 181 pytest tests across 21 test files
├── .env.example                 # Environment variable template (no real secrets)
├── requirements.txt             # Python dependencies
└── vercel.json                  # Static hosting config for the PWA
```

## Known limitations

- Windows-only tools (app control, screenshots, system metrics, OS
  credential store) report an unsupported-platform error on macOS/Linux.
- Gmail and Calendar are read-only; Jarvis cannot send mail, delete
  messages, or create/edit events.
- Browser automation is limited to approved domains and low-risk
  actions; it never submits forms, checks out, or completes quizzes.
- Briefings, search, and summaries run on demand only; there are no
  background jobs or notifications.
- Remote access requires Tailscale on both devices; without it, the
  backend is reachable only from the laptop itself.

## Uninstall

1. Disconnect Google: `POST /api/auth/google/disconnect`, and remove
   Jarvis at [Google Account Permissions](https://myaccount.google.com/permissions).
2. Wipe local data: `POST /api/data/clear` with
   `{"confirm": true, "confirmation_text": "DELETE ALL DATA"}`.
3. Remove the Chrome extension at `chrome://extensions/`.
4. Delete the project directory and virtual environment, and remove any
   `Jarvis_Google_OAuth` entry from Windows Credential Manager.
