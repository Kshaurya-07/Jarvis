# Jarvis — Personal AI Assistant Backend, Laptop/Browser Companion & Daily Briefing

Jarvis is a modular, secure personal AI assistant backend, Windows companion, Chrome study extension, and on-demand briefing engine built with **FastAPI** and the official **Google Gen AI Python SDK**. It provides a decoupled backend architecture ready for any future desktop or web frontend.

---

## Architecture Overview

```
Jarvis/
├── app/
│   ├── main.py                  # FastAPI application setup, DNS rebinding defense, request size limit, lifespan
│   ├── api/
│   │   ├── routes.py            # API endpoints: /health, /api/chat, /api/tools, /api/confirm, /api/extension/read-page, /api/reminders, /api/memories, /api/briefing, /api/auth/google, /api/gmail, /api/calendar, /api/browser, /api/data, /api/demo
│   │   └── schemas.py           # Pydantic schemas for request and response payloads
│   ├── core/
│   │   ├── config.py            # Settings validation, path resolution, security thresholds via pydantic-settings
│   │   ├── confirmation.py      # ConfirmationManager for state-changing operations
│   │   ├── data_manager.py      # User data export, wiping, backup snapshots, checksum validation, restore
│   │   ├── demo_manager.py      # Phase 10 demo lifecycle: status, mock data seeding, isolated one-step cleanup
│   │   ├── rate_limiter.py      # Rolling-window rate limiter for auth and confirmation failures (HTTP 429)
│   │   ├── browser_automation.py# Domain validation, sensitive-field filtering, forbidden action blocking
│   │   ├── google_auth.py       # Google OAuth 2.0 PKCE flow, state verification, OS keyring credential storage
│   │   ├── security.py          # PathGuard security, NTFS ADS check, directory traversal & symlink escape defense
│   │   └── logger.py            # Action audit logger with regex scrubbing for keys, tokens, emails, cards
│   ├── services/
│   │   ├── agent_service.py     # Gemini client, tool dispatch loop, error handling
│   │   └── extension_service.py # Webpage text analysis, practice quiz guidance, prompt injection defense
│   └── tools/
│       ├── base.py              # Base tool schemas and ToolResult models
│       ├── workspace_tools.py   # list_files, read_text_file (workspace bound)
│       ├── notes_tools.py       # create_note, search_notes (notes bound)
│       ├── app_control_tools.py # open_application (server-side allowlist, Windows only)
│       ├── system_status_tools.py # get_battery_status, get_storage_status, get_memory_status
│       ├── screenshot_tools.py  # capture_screenshot (local-only), analyze_screenshot (vision)
│       ├── reminders_tools.py   # create_reminder, list_reminders, complete_reminder, delete_reminder
│       ├── memory_tools.py      # remember_item, forget_item, list_memories (sensitive credential filter)
│       ├── search_tools.py      # web_search (official Tavily/Google/Brave API, personal data guard)
│       ├── briefing_tools.py    # get_daily_briefing (on-demand reminders, notes & safe web overview)
│       ├── gmail_tools.py       # list_gmail_messages, summarize_gmail_messages (strictly read-only)
│       ├── calendar_tools.py    # list_calendar_events, summarize_calendar_events (strictly read-only)
│       ├── browser_automation_tools.py # browser_navigate, browser_read_page, browser_fill_field
│       ├── registry.py          # Central registry with server-side argument validation (26 approved tools)
│       └── future_interfaces.py # Contracts & TODO stubs for future phases
├── backups/                     # Opt-in local backup snapshots with SHA-256 checksums
├── demo/                        # Phase 10 Local Fictional Demo Page (/demo/)
│   └── index.html               # Project Deep Horizon Europa dossier, safe search input, practice quiz
├── extension/                   # Minimal Chrome Extension (Manifest V3)
│   ├── manifest.json            # Manifest V3 (activeTab, scripting only)
│   ├── popup.html               # Extension UI popup with voice, reading aid & browser automation controls
│   ├── popup.js                 # Safe DOM reading, non-sensitive field filling, Web Speech API, TTS, abort
│   ├── popup.css                # Extension styles
│   └── icons/                   # Extension icons (16px, 48px, 128px)
├── mobile/                      # Mobile-Friendly Web App & PWA Companion (Phase 7)
│   ├── index.html               # Responsive touch-friendly mobile interface with Demo Tour drawer
│   ├── style.css                # Mobile-first CSS, touch targets, dark palette
│   ├── app.js                   # Client logic: chat stream, abort control, push-to-talk, audit feed, demo actions
│   ├── manifest.webmanifest     # PWA manifest (standalone, theme colors, icons)
│   ├── service-worker.js        # Offline app shell caching & live API bypass
│   └── icons/                   # PWA icons (192px, 512px)
├── tests/                       # Complete pytest suite (169 unit and integration tests across 20 test files)
├── .env.example                 # Example environment variables template
├── requirements.txt             # Python dependencies
└── README.md                    # Project documentation and API reference
```

---

## Features Implemented

### Phase 1: Core Foundation & Sandboxed Storage
- **`list_files`**: Lists files and subfolders within the configured `workspace/` folder.
- **`read_text_file`**: Reads text and code files (`.txt`, `.md`, `.py`, `.json`, etc.) strictly inside `workspace/`.
- **`create_note`**: Saves a new markdown note in `notes/` with automatic title sanitization and timestamps.
- **`search_notes`**: Case-insensitive substring search across saved notes, returning matching files and snippets.
- **Strict Path Sandboxing**: Enforces `pathlib.Path.resolve()` checks. Any path escaping the designated folder via `../`, absolute root drives, or null bytes is immediately rejected with `SecurityViolationError`.
- **Audit Logging**: Every action is recorded with timestamp, tool name, execution duration, and success/failure. Sensitive contents and secrets are never logged.

### Phase 2: Windows Laptop Companion (Permission-Based)
- **Application Control (`open_application`)**: Launches pre-approved Windows apps (`notepad`, `calculator`, `paint`, `explorer`, `cmd`). Zero arbitrary shell execution; explicit user confirmation required.
- **System Status (Read-Only)**: `get_battery_status` (charge, power source), `get_storage_status` (drive usage), `get_memory_status` (RAM capacity and usage).
- **Display Capture**: `capture_screenshot` (local-first to `screenshots/`, requires confirmation, no background capture) and `analyze_screenshot` (discloses external transmission to Gemini vision).
- **Confirmation Workflow**: State-changing tools return a one-time `confirmation_id` approved via `POST /api/confirm`.

### Phase 3: Minimal Chrome Extension Companion (Study & Reading Aid)
- **Manifest V3 Platform**: Modern Chrome extension with minimum permissions: `"activeTab"` and `"scripting"`.
- **User-Triggered Active Tab Access**: Does **not** request `<all_urls>` or run automatically when a page loads. Only accesses the single tab the user selects when clicking "Read this page".
- **Privacy-Guaranteed DOM Extraction**: Automatically strips password fields (`input[type="password"]`), hidden inputs, scripts, styles, iframes, and hidden DOM nodes (`display: none`, `visibility: hidden`, `aria-hidden="true"`). Slices text to 50,000 characters.
- **Practice Quiz & Study Help**: Explains questions, clarifies terminology, and compares options to help students study. **Zero Auto-Submit**: Does not select answers or submit quizzes on the user's behalf.
- **Prompt Injection Defenses & Abort Control**: Webpage content is treated as untrusted input; Stop button aborts active requests immediately via `AbortController`.
- **Strict Backend Origin Validation**: Custom middleware blocks unauthorized external web origins (`HTTP 403`). Only localhost and `chrome-extension://*` are permitted.

### Phase 4: Voice I/O, Local Reminders & User-Controlled Memory
- **Voice Input / Output (Chrome Extension)**:
  - **Push-to-Talk**: Microphone access is requested only when the user clicks "Push to Talk". No continuous or background recording.
  - **Editable Transcript**: Speech is transcribed via the browser's Web Speech API and placed into the text box for user review and editing before sending.
  - **Optional Spoken Responses (TTS)**: Off by default via toggle. Local browser speech synthesis with a "Stop Speaking" mute button.
  - **Zero Audio Transmission**: Raw audio is never stored or transmitted to the backend or Gemini.
- **Local Reminders (`data/reminders.json`)**:
  - `create_reminder`, `list_reminders`, `complete_reminder`, `delete_reminder`.
  - Confirmation required before deleting any reminder. Stored locally without background OS daemons.
- **User-Controlled Memory (`data/memories.json`)**:
  - `remember_item`, `forget_item`, `list_memories`.
  - Strict opt-in: Never silently converts chat history into memory.
  - Sensitive credential screening: Automatically detects and rejects passwords, API keys, card numbers, and tokens.
  - Setting to toggle memory and clear all memory.

### Phase 5: Web Search & On-Demand Daily Briefing
1. **Web Search (`web_search`)**:
   - Uses official search APIs (**Tavily Search**, **Google Custom Search JSON API**, or **Brave Search**). Zero HTML page scraping.
   - Credentials configured via environment variables (`SEARCH_API_KEY`, `SEARCH_ENGINE_ID`, `SEARCH_PROVIDER`).
   - Returns structured results: title, source domain, link, snippet, and publication date when available.
   - **Mandatory Markdown Citations**: Assistant cites links for claims in `[Title](URL)` format, distinguishing sourced facts from its own explanations.
   - **Personal Data Guard**: Search queries are screened with `detect_sensitive_data()`. Any query containing potential passwords, API keys, or private credentials is blocked immediately.
   - **No Automated Actions**: Never opens links or navigates to websites without explicit user direction.
   - **No Query Logging**: Search queries and result snippets are never stored in persistent audit logs.

2. **On-Demand Daily Briefing (`get_daily_briefing` / `GET /api/briefing`)**:
   - Summarizes:
     1. Today's local reminders from `data/reminders.json`.
     2. Recent local notes and tasks from `notes/`.
     3. Optional web overview strictly when requested with general user topics.
   - **No Automatic Background Jobs**: Generated purely on-demand when requested by the user.
   - **Private Data Isolation**: Private reminders and personal notes are **never** included or leaked into external search queries.
   - **Clear Sourcing**: Explicitly identifies which details came from local laptop storage and which came from external web sources.

### Phase 6: Read-Only Gmail & Google Calendar Integration (OAuth 2.0 & PKCE)
- **Official Google OAuth 2.0 Flow**:
  - Implements the authorization-code flow with **PKCE (RFC 7636, S256)** and cryptographically secure anti-CSRF `state` tokens (10-minute TTL, single-use consumption).
  - Keeps refresh tokens stored securely in the **Operating System Credential Store** (Windows Credential Locker via `keyring`).
  - Fallback local encrypted token storage is disabled by default and requires explicit user opt-in (`GOOGLE_CREDENTIAL_FALLBACK_OPT_IN=true`).
  - Never stores client secrets, tokens, or credentials in source code, browser extensions, or audit logs.
- **Gmail Read-Only Tools**:
  - **`list_gmail_messages`**: Lists recent message headers (sender, subject, date, snippet). Respects `max_results` caps (1 to 20, default 5).
  - **`summarize_gmail_messages`**: Summarizes selected messages (by ID) or recent unread emails using Gemini.
  - **Strictly Read-Only**: **Zero write/delete capabilities**. Does **not** send, delete, trash, archive, label, or mark messages as read.
  - **Clear Disclosure**: Always discloses to the user: *"Notice: Email text from these messages is being transmitted to Google Gemini for summarization."*
  - **No Persistent Body Storage**: Email body content is **never** written to `data/memories.json` or `logs/actions.jsonl`.
- **Google Calendar Read-Only Tools**:
  - **`list_calendar_events`**: Lists upcoming events for a validated date range (`time_min` to `time_max`, maximum window 365 days).
  - **`summarize_calendar_events`**: Summarizes scheduled commitments, busy periods, and conflicts for a date range using Gemini.
  - **Strictly Read-Only**: **Zero write/delete capabilities**. Does **not** create, edit, update, or delete calendar events.
  - **Clear Disclosure**: Always discloses: *"Notice: Calendar event details for this date range are being transmitted to Google Gemini for summarization."*
  - **Strict Redaction**: Event titles, descriptions, attendee emails, and locations are **never** written to persistent memory or audit action logs.
- **Privacy & Safety Guarantees**:
  - Integrations remain disabled until the user explicitly initiates connection.
  - Email and calendar data are **never** passed into web search queries.
  - No background polling: Data is fetched only upon explicit user request.

### Phase 7: Mobile-Friendly Web App & PWA Companion (Localhost-First)
- **Responsive Mobile Web Interface (`mobile/`)**:
  - Accessible, touch-friendly UI optimized for phones (320px+), tablets, and desktop browsers.
  - Touch targets adhere to accessibility standards (minimum 48px by 48px for interactive buttons).
  - Dark-mode palette matching modern OS themes with safe area insets for mobile gesture bars and notches.
- **PWA Installation Support**:
  - Web App Manifest (`manifest.webmanifest`) enabling standalone app window display and home screen installation.
  - Service Worker (`service-worker.js`) caching core UI assets for rapid startup while passing live `/api/` calls network-only.
- **Network Safety & Option B Architecture**:
  - Jarvis backend remains bound strictly to `127.0.0.1` (localhost).
  - No public internet exposure, no unauthenticated cloud relays, and no remote account dependencies.
  - Explicit notification banner clarifies that phone-to-laptop cross-device access requires a dedicated local pairing mechanism (planned for a future phase).
- **Core Companion Features**:
  - **Live Connection Status**: Visual indicator reporting backend health, platform, Gemini configuration, and Google OAuth status.
  - **Text Command Input & Send**: Auto-expanding input area with quick command suggestion chips.
  - **Active Stop / Pause Control**: Uses `AbortController` to cancel in-flight assistant requests immediately on user demand.
  - **Push-to-Talk Voice Input**: Touch-friendly on-device microphone button with live recording banner and cancel option. Speech is transcribed locally via Web Speech API and placed into an editable input box before sending.
  - **Recent Action Status (Audit Feed)**: Collapsible drawer displaying non-sensitive audit logs (`GET /api/actions`) without leaking file bodies or secrets.
  - **Pending Action Approvals**: Directly presents approval/denial cards for state-changing operations requiring confirmation tokens.
  - **Command History Privacy Control**: Local command history is **opt-in only (disabled by default)** with a one-click "Clear History" button. Never saves API keys, OAuth tokens, passwords, or cookies in browser storage.


---

## Web Search Provider Setup

Jarvis supports three official search providers via `SEARCH_PROVIDER`:

### 1. Tavily Search API (Default)
1. Sign up at [tavily.com](https://tavily.com/) and obtain an API key.
2. In `.env`:
   ```ini
   SEARCH_PROVIDER=tavily
   SEARCH_API_KEY=tvly-your_tavily_api_key
   ```

### 2. Google Custom Search JSON API
1. Enable the **Custom Search API** in the Google Cloud Console.
2. Create a Programmable Search Engine at [programmablesearchengine.google.com](https://programmablesearchengine.google.com/) and copy the Search Engine ID (`cx`).
3. In `.env`:
   ```ini
   SEARCH_PROVIDER=google_custom_search
   SEARCH_API_KEY=your_google_cloud_api_key
   SEARCH_ENGINE_ID=your_search_engine_cx_id
   ```

### 3. Brave Search API
1. Sign up at [brave.com/search/api/](https://brave.com/search/api/) and get an API key.
2. In `.env`:
   ```ini
   SEARCH_PROVIDER=brave
   SEARCH_API_KEY=your_brave_api_key
   ```

*(Note: If `SEARCH_API_KEY` is not set, Jarvis continues to run normally, and gracefully informs you that web search requires `SEARCH_API_KEY` when web search is requested).*

---

## How to Load the Chrome Extension Locally

1. Open Google Chrome.
2. In the URL bar, go to `chrome://extensions/`.
3. In the top-right corner, enable the **Developer mode** toggle.
4. Click the **Load unpacked** button in the top-left toolbar.
5. Select the folder:
   ```
   D:\Jarvis\extension
   ```
6. **Jarvis Local Companion** will appear in your extensions list. Pin it to your Chrome toolbar.

---

## Getting Started with the Backend

### 1. Create Virtual Environment & Install Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env`:

```powershell
copy .env.example .env
```

Edit `.env`:

```ini
GEMINI_API_KEY=your_gemini_api_key_here
HOST=127.0.0.1
PORT=8000
SEARCH_PROVIDER=tavily
SEARCH_API_KEY=your_search_api_key_here
MEMORY_ENABLED=true
```

### 3. Run the Backend Server

```powershell
.\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## Google Cloud Console & OAuth 2.0 Setup (Phase 6)

Jarvis integrates with Gmail and Google Calendar strictly through official Google APIs and read-only OAuth scopes.

### 1. Create Google Cloud Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click **Select a project** (or dropdown) > **New Project**, name it `Jarvis-Assistant`, and click **Create**.

### 2. Enable APIs
1. In the left navigation menu, go to **APIs & Services** > **Library**.
2. Search for and enable:
   - **Gmail API**
   - **Google Calendar API**

### 3. Configure OAuth Consent Screen
1. Go to **APIs & Services** > **OAuth consent screen**.
2. Select **External** (for personal Google accounts) and click **Create**.
3. Fill in:
   - App name: `Jarvis Assistant`
   - User support email: your email
   - Developer contact email: your email
4. On the **Scopes** page, click **Add or Remove Scopes** and select:
   - `https://www.googleapis.com/auth/gmail.readonly` (Read resources & metadata)
   - `https://www.googleapis.com/auth/calendar.readonly` (Read calendar events)
5. On the **Test users** page, add your Google account email address.
6. Save and finish.

### 4. Create OAuth 2.0 Credentials
1. Go to **APIs & Services** > **Credentials**.
2. Click **Create Credentials** > **OAuth client ID**.
3. Choose **Web application** (or **Desktop app**).
4. Under **Authorized redirect URIs**, add:
   ```
   http://127.0.0.1:8000/api/auth/google/callback
   ```
5. Click **Create** and copy your **Client ID** and **Client Secret**.

### 5. Configure `.env`
In your local `.env` file, add:
```ini
GOOGLE_CLIENT_ID=your_client_id_here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
GOOGLE_CREDENTIAL_FALLBACK_OPT_IN=false
```

### 6. Connect, Disconnect, and Revoke Flow
- **Connect**:
  1. Make a GET request to `http://127.0.0.1:8000/api/auth/google/url`.
  2. Open the returned `auth_url` in your browser.
  3. Sign in, review the requested read-only permissions, and click **Allow**.
  4. Google redirects to `http://127.0.0.1:8000/api/auth/google/callback`.
  5. The backend validates the PKCE verifier and anti-CSRF state, and stores the refresh token in the **Windows Credential Locker** via `keyring`.
- **Check Status**:
  `GET http://127.0.0.1:8000/api/auth/google/status` returns connection status, connected email, granted scopes, and storage backend.
- **Disconnect & Revoke**:
  `POST http://127.0.0.1:8000/api/auth/google/disconnect` calls Google's revocation endpoint (`https://oauth2.googleapis.com/revoke`), erases credentials from the OS Credential Store, and resets auth status.

---

## Mobile Companion Web App & PWA (Phase 7)

Jarvis includes a mobile-friendly responsive companion web application and Progressive Web App (PWA) located in `mobile/`. It allows users to send commands, view responses, monitor recent audit actions, and manage action confirmations from a phone, tablet, or desktop browser.

### 1. How to Access the Mobile Companion
When the Jarvis backend server is running:
- **Direct Browser Access**: Navigate to `http://127.0.0.1:8000/mobile/` (or visit `http://127.0.0.1:8000/` which automatically redirects to `/mobile/`).
- **Responsive Testing in Chrome / Edge**:
  1. Open DevTools (`F12` or `Ctrl+Shift+I`).
  2. Toggle the Device Toolbar (`Ctrl+Shift+M`).
  3. Select mobile presets such as **iPhone 14**, **Pixel 7**, or **iPad Air** to experience touch targets, responsive drawer panels, and mobile input layouts.
- **PWA Installation**:
  - In supported browsers (Chrome, Edge), click the **Install Jarvis Companion** icon in the address bar.
  - On iOS Safari, tap **Share > Add to Home Screen**.
  - Operates in standalone window mode with cached app shell assets for instant launch.

### 2. Supported Browsers
- **Desktop**: Google Chrome, Microsoft Edge, Mozilla Firefox, Apple Safari.
- **Mobile & Tablet**: Chrome for Android, Safari for iOS, Samsung Internet, Edge Mobile.

### 3. Network Architecture & Connection Limitations (Option B)
- **Localhost-Only Isolation**: In strict accordance with **Option B**, the Jarvis backend is bound exclusively to `127.0.0.1` on the user's host laptop.
- **Cross-Device Boundary**: A mobile phone connected to the same Wi-Fi cannot directly access the laptop's `127.0.0.1` address without an explicit LAN binding and authenticated pairing protocol. The web app detects this environment and displays a clear notice:
  > *"Jarvis runs in Localhost-Only mode (Option B). Phone-to-laptop remote commands across different devices are not available without local network pairing."*
- **No Unsafe Relays**: Jarvis does **not** expose ports to the public internet, employ unauthenticated port-forwarding, or rely on third-party cloud relays.

### 4. Security Model & Data Storage Behavior
- **No Secrets in Browser Storage**: The companion web app **never** stores Gemini API keys, OAuth tokens, client secrets, passwords, or session cookies in `localStorage` or `sessionStorage`.
- **Command History Privacy Control**:
  - Command history is **opt-in only (disabled by default)**.
  - When enabled by the user in Settings, command strings are stored strictly on-device in the browser's local storage (`jarvis_command_history`).
  - Users can click **Clear Local Command History** at any time to purge all stored entries.
- **Push-to-Talk Voice Privacy**:
  - Microphone access is requested only when the user explicitly interacts with the voice button.
  - Audio is converted to text on-device via the browser's native Web Speech API.
  - The transcript is placed directly into the editable text area for review before sending.
  - Zero raw audio is transmitted or persisted to the server.
- **State-Changing Action Confirmations**:
  - Commands requiring confirmation (e.g. `open_application`, `capture_screenshot`, `delete_reminder`) render interactive confirmation cards directly in the chat timeline, requiring explicit "Approve" or "Deny" user taps before execution.

### Phase 8: Limited Browser Automation (User-Approved Domains & Tasks)
- **Approved Domain Scope & Allowlist**:
  - The user explicitly selects or approves allowed domains (e.g., `wikipedia.org`, `python.org`, `fastapi.tiangolo.com`, `docs.python.org`).
  - Strict host validation and subdomain matching prevents open redirects and domain spoofing (e.g., `evil-wikipedia.org`). Target URLs escaping approved domains are immediately blocked (`DomainSecurityViolation`).
- **Low-Risk Supported Actions**:
  - **`browser_navigate`**: Navigates active browser tab to a validated URL strictly within the approved domain. Requires explicit user confirmation.
  - **`browser_read_page`**: Reads visible text from an active page within the approved domain. Strips script/style tags, hidden DOM elements, and password fields. Untrusted page content is treated strictly as reference data and truncated to safe limits.
  - **`browser_fill_field`**: Fills ordinary, non-sensitive form fields (e.g., search query input) on an approved domain. Requires explicit user confirmation.
- **Sensitive-Field Exclusion Guard (Zero Credential Automation)**:
  - Automatically identifies sensitive fields via input type (`password`, `hidden`, `file`), autocomplete metadata (`current-password`, `new-password`, `cc-number`, `cc-csc`, `cc-exp`, `one-time-code`), and field names/selectors/labels (passwords, credit cards, CVVs, pins, SSNs, 2FA/MFA/OTP codes, auth tokens).
  - Jarvis strictly refuses to read or fill sensitive fields (`Security Refusal`).
  - Proposed input values are scanned for embedded secrets with `detect_sensitive_data()`. Any value containing passwords or tokens is blocked immediately (`Privacy Refusal`).
- **Zero Automated Submission, Purchases, or Quiz Completion**:
  - Jarvis **never** clicks submit, buy, purchase, checkout, pay, send message, or quiz submission buttons.
  - Form submission controls must remain entirely user-operated; the agent fills values and prompts the user to review and submit manually.
  - Never bypasses CAPTCHAs, paywalls, access controls, or site security measures.
  - Graded quizzes and certification submissions are prohibited from automation; study help explains questions while the user selects and submits answers themselves.
- **Confirmation Lifecycle & Pause/Stop Controls**:
  - Before any navigation or field-filling operation, Jarvis generates a pending action and displays the exact target, selector, and domain, requiring explicit user approval via token (`POST /api/confirm`).
  - Active operations can be halted immediately via the visible Stop control (`AbortController`) in the Chrome extension and mobile companion.
- **Privacy & Audit Logging**:
  - Page text and filled field values are **never** persisted to disk logs (`logs/actions.jsonl`) or persistent memory (`data/memories.json`).
  - Never collects or stores website passwords, session cookies, or auth tokens in backend storage.

### Phase 9: Security Hardening, User Data Controls & Release Readiness
- **Security Hardening**:
  - **DNS Rebinding Defense**: Restricts `Host` header strictly to `localhost`, `127.0.0.1`, and test environments (`HTTP 403`).
  - **Cross-Site Referer Filtering**: Rejects state-changing requests (`POST`, `PUT`, `DELETE`, `PATCH`) originating from foreign external referers (`HTTP 403`).
  - **Request Body Payload Limit**: Enforces a strict 2 MB maximum payload size via `Content-Length` header check before reading requests (`HTTP 413`).
  - **Authentication Failure Rate Limiting**: Employs rolling 60-second window limiting failed confirmation or OAuth callback requests to 5 attempts, returning `HTTP 429 Too Many Requests` with standard `Retry-After`.
  - **Filesystem & Path Escape Defense**: Rejects Windows NTFS Alternate Data Streams (`:`) and detects symlinks resolving outside configured base directories (`SecurityViolationError`).
  - **Audit Log Redaction**: Regex-based scrubbing automatically redacts passwords, API keys, bearer tokens, credit card numbers, and email addresses before writing to `logs/actions.jsonl` or in-memory feeds.
- **User Data Controls**:
  - **Data Locations (`GET /api/data/locations`)**: View exact local paths for notes, reminders, memories, screenshots, action logs, backups, and OAuth credential storage status.
  - **Data Export (`GET /api/data/export`)**: Exports user-owned notes, reminders, and memories in clean JSON format. API keys, secrets, and credentials are strictly excluded.
  - **Clear All Data (`POST /api/data/clear`)**: Permanently wipes local notes, reminders, memories, and screenshots. Requires explicit confirmation: `confirm=true` and `confirmation_text='DELETE ALL DATA'`.
  - **OAuth Disconnect & Google Revocation (`POST /api/auth/google/disconnect`)**: Erases local refresh tokens from Windows Credential Locker / fallback file, requests remote revocation, and provides direct instructions to review permissions at [myaccount.google.com/permissions](https://myaccount.google.com/permissions).
- **Opt-In Local Backup & Recovery**:
  - **Create Backup (`POST /api/data/backup`)**: Saves validated JSON snapshots to `backups/` with SHA-256 integrity checksums over canonical data. Secrets and credentials are never included.
  - **Validate & List Backups (`GET /api/data/backups`)**: Inspects local backup files, reports verification status, and checks checksum matches.
  - **Restore Backup (`POST /api/data/restore`)**: Validates backup structure, checksum, and note filenames (defending against traversal). Prevents accidental overwrites by requiring `confirm_overwrite=true` whenever existing data is detected.
- **Startup Configuration Validation**:
  - Verifies loopback binding (`127.0.0.1`, `localhost`, `::1`); halts startup with friendly error if bound to non-localhost without `ALLOW_REMOTE_ACCESS=true`.
  - Validates port numbers and search provider settings; outputs friendly informational notices if `GEMINI_API_KEY` is not yet configured.
- **Privacy & Telemetry**:
  - Jarvis includes zero telemetry, zero analytics tracking, and zero automatic cloud backups. All processing and storage are local-first.

### Phase 10: Polished End-to-End Demo & Multi-Interface Integration
- **Fictional Local Science Dossier (`/demo/`)**:
  - Hosted locally at `http://127.0.0.1:8000/demo/`. Features a rich, fictional space exploration article: *"Deep Horizon: Exploring Europa's Subsurface Ocean"*.
  - Completely self-contained with **zero real personal data**, **zero live credentials**, and **zero external cloud accounts**.
  - Includes interactive demonstration elements: a non-sensitive mission filter input (`#demoSearchInput`) and a non-graded study quiz section (`#studyQuizHelp`).
  - **Academic Integrity Guard**: Prominent safety disclaimer confirming Jarvis operates strictly as a study aid to explain questions and compare options. Jarvis will *never* automatically select or submit quiz answers.
- **Backend Demo Manager (`app/core/demo_manager.py`) & Lifecycle REST API**:
  - `GET /api/demo/status`: Returns comprehensive demo metadata, active demo item counts, localhost URLs, and 8-step guided walkthrough instructions.
  - `POST /api/demo/seed`: Safely creates mock mission notes (`demo_europa_mission_notes.md`), a reminder (`[DEMO] Review Europa mission science objectives`), and a memory (`demo_favorite_mission`). Every item is explicitly tagged `[DEMO]`.
  - `POST /api/demo/reset`: **One-step cleanup** that safely unlinks and purges all mock demo records while strictly preserving real user notes, reminders, and memories.
- **Mobile Companion Integration (`mobile/`)**:
  - **"Demo Tour" Header Button**: Opens a dedicated slide-out drawer (`#demo-drawer`) presenting the 7-step guided walkthrough.
  - **One-Click Actions**: "Open Demo Page", "Seed Demo Data", and "Clear Demo Data" buttons with real-time feedback rendered directly in the chat stream.
  - **Quick Demo Chips**: Pre-configured command chips for `"Show my demo notes"` and `"What is the launch date of the Europa Deep Horizon mission?"`.
- **Chrome Extension Integration (`extension/`)**:
  - **Quick Launch Banner**: Added "Launch Local Demo Tab (/demo/)" quick-access banner directly in `extension/popup.html`.
  - **Pre-Approved Localhost**: Added `localhost` and `127.0.0.1` to default approved domains for browser automation, enabling instant testing on the local demo page without configuration overhead.
  - **Visible Text Grounding**: Transmits only active tab visible text with explicit disclosure that text is processed by Gemini.
  - **Push-to-Talk Voice Workflow**: Records speech on-demand, transcribes locally via Web Speech API, and places the text into an editable box for user review before submission.
  - **Active Stop / Pause Control**: Aborts in-flight operations instantly via `AbortController` in both the extension and mobile companion.

---

## API Usage Examples (`curl`)

### 1. Google OAuth & Status
```bash
# Get OAuth authorization URL
curl -X GET "http://127.0.0.1:8000/api/auth/google/url"

# Check Google integration status
curl -X GET "http://127.0.0.1:8000/api/auth/google/status"

# Disconnect and revoke Google account
curl -X POST "http://127.0.0.1:8000/api/auth/google/disconnect"
```

### 2. Read-Only Gmail
```bash
# List recent emails
curl -X GET "http://127.0.0.1:8000/api/gmail/messages?max_results=5"

# Summarize recent unread emails with Gemini
curl -X POST "http://127.0.0.1:8000/api/gmail/summarize" \
  -H "Content-Type: application/json" \
  -d '{"max_results": 3, "query": "is:unread", "custom_instructions": "Highlight action items and deadlines"}'
```

### 3. Read-Only Google Calendar
```bash
# List upcoming calendar events
curl -X GET "http://127.0.0.1:8000/api/calendar/events?max_results=10"

# Summarize schedule for a date range with Gemini
curl -X POST "http://127.0.0.1:8000/api/calendar/summarize" \
  -H "Content-Type: application/json" \
  -d '{"time_min": "2026-11-10T00:00:00Z", "time_max": "2026-11-17T23:59:59Z"}'
```

### 4. On-Demand Daily Briefing
```bash
# Local briefing (reminders & notes only)
curl -X GET "http://127.0.0.1:8000/api/briefing?include_web_summary=false"

# Briefing with general web overview
curl -X GET "http://127.0.0.1:8000/api/briefing?include_web_summary=true&web_topics=latest%20tech%20news"
```

### 5. Chat with Tool Calling
```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What meetings do I have scheduled this week?"}'
```

### 6. User Data Controls & Backup (Phase 9)
```bash
# View all local data storage locations and item counts
curl -X GET "http://127.0.0.1:8000/api/data/locations"

# Export user-owned notes, memories, and reminders (JSON format, secrets excluded)
curl -X GET "http://127.0.0.1:8000/api/data/export"

# Create a local validated backup snapshot with SHA-256 checksum
curl -X POST "http://127.0.0.1:8000/api/data/backup" \
  -H "Content-Type: application/json" \
  -d '{"backup_name": "my_snapshot"}'

# List all local backups with verification status
curl -X GET "http://127.0.0.1:8000/api/data/backups"

# Restore from a backup (requires confirm_overwrite=true if existing data exists)
curl -X POST "http://127.0.0.1:8000/api/data/restore" \
  -H "Content-Type: application/json" \
  -d '{"backup_filename": "jarvis_backup_my_snapshot.json", "confirm_overwrite": true}'

# Permanently clear all user notes, memories, reminders, and screenshots (requires confirmation)
curl -X POST "http://127.0.0.1:8000/api/data/clear" \
  -H "Content-Type: application/json" \
  -d '{"confirm": true, "confirmation_text": "DELETE ALL DATA"}'
```

### 7. Phase 10 End-to-End Demo Endpoints
```bash
# Check demo status, active mock items, and walkthrough steps
curl -X GET "http://127.0.0.1:8000/api/demo/status"

# Seed mock demo notes, reminders, and memories (tagged [DEMO])
curl -X POST "http://127.0.0.1:8000/api/demo/seed"

# One-step removal of all mock demo items (real user data is preserved)
curl -X POST "http://127.0.0.1:8000/api/demo/reset"
```

---

## Phase 10 End-to-End Demo Walkthrough Guide

The Phase 10 interactive demo connects the laptop assistant backend, Chrome extension, and mobile-friendly companion using a self-contained local science dossier.

### Step-by-Step Demo Flow

1. **Start the Backend**:
   ```powershell
   .\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   Confirm the console logs show `Bound to: 127.0.0.1:8000` and `Jarvis Agent Backend starting up`.

2. **Open the Mobile Companion**:
   Navigate to `http://127.0.0.1:8000/mobile/`.
   - The top header pill shows **Online** (confirming loopback connectivity).
   - Tap **"Demo Tour"** in the top navigation bar to open the 7-step guided demo drawer.
   - Tap **"Seed Demo Data"**. Jarvis creates fictional mission notes (`demo_europa_mission_notes.md`), a reminder (`[DEMO] Review Europa mission science objectives`), and memory (`demo_favorite_mission`).

3. **Send Text Commands from Companion**:
   - Tap the quick chip **"System Status"** or type `"What is the system status?"` and click Send. Jarvis executes read-only hardware tools and returns RAM, battery, and storage metrics.
   - Tap the quick chip **"Demo Notes"** or type `"Show my demo notes"`. Jarvis reads the seeded Europa dossier notes and summarizes mission instruments.

4. **Open Chrome Demo Page & Extension**:
   - In Google Chrome, navigate to `http://127.0.0.1:8000/demo/`.
   - Click the **Jarvis Local Companion** extension icon in your Chrome toolbar.
   - The status badge shows **Jarvis Online** (connected to `127.0.0.1:8000`).

5. **Read Active Tab & Inspect Grounded Summary**:
   - Click **"Read This Page"**.
   - Jarvis extracts visible page text, displays the character count, and presents a clear disclosure:
     > *"Notice: Visible page text was transmitted to the Gemini API for study assistance."*
   - Returns a concise answer grounded in the Europa mission article.

6. **Practice Quiz Study Help (Academic Integrity)**:
   - In the extension popup, select **"Practice Quiz Help"** mode.
   - In the question box, enter: `"Explain Question 1 about the Deep-Ice Radar Sounder"`.
   - Click **"Read This Page"**. Jarvis explains the scientific principles behind radar sounding and compares the multiple-choice options.
   - **Safety Boundary**: Jarvis explicitly reminds the user to choose and submit answers manually; no automated form submission occurs.

7. **Voice Push-to-Talk & Active Stop Control**:
   - Tap **"Push to Talk"** in the extension or companion. Speak your question.
   - Inspect and edit the locally generated transcript in the input box before sending.
   - During in-flight operations, click the visible red **"Stop"** button to abort requests immediately via `AbortController`.

8. **One-Step Demo Cleanup**:
   - In the companion's Demo Tour drawer (or via `POST /api/demo/reset`), click **"Clear Demo Data"**.
   - Jarvis purges all `[DEMO]` notes, reminders, and memories in a single step without touching any real user records.

---

## Testing

Run the complete test suite:

```powershell
.\.venv\Scripts\pytest -v
```

**Test Coverage (169 tests across 20 test files)**:
- `tests/test_demo_flow.py`: Local demo page serving (`/demo/`), fictional science content verification (zero personal data, zero live accounts), demo status metadata inquiry (`GET /api/demo/status`), mock data seeding (`POST /api/demo/seed`), one-step demo cleanup (`POST /api/demo/reset`) with strict user data preservation, companion text command dispatch, extension active tab grounded summarization, practice quiz academic integrity compliance, browser automation safe field filling with confirmation, password/sensitive field rejection on demo domains, and mobile companion demo tour UI element serving.
- `tests/test_phase9_hardening.py`: DNS rebinding defenses (Host header filtering), cross-site referer filtering on state-changing methods, request payload size caps (Content-Length 413), authentication failure rate limiting (rolling 60s window, HTTP 429), NTFS alternate data stream (`:`) rejection, symlink escape checks, audit log regex scrubbing (zero keys, secrets, tokens, card numbers, or emails in logs), startup configuration validation, data locations inquiry, clean data export, confirmation-guarded data wiping, Google disconnect guidance, and backup creation/integrity-validation/restore overwrite safety.
- `tests/test_browser_automation.py`: Domain allowlist rules, subdomain validation, domain spoofing defense, URL escape rejection, sensitive-field exclusion (passwords, cards, CVVs, tokens), secret credential screening in field values, automated submit/checkout blocking, negative tool registration audit, confirmation lifecycle for navigation and field filling, audit log redaction (zero page text or values logged), and REST endpoints.
- `tests/test_mobile_companion.py`: Mobile HTML PWA delivery, viewport tags, touch-target CSS rules, PWA web manifest, service worker caching, stop/abort control via `AbortController`, command history opt-in privacy, recent actions feed, root redirect, and Option B localhost isolation notice.
- `tests/test_google_auth.py`: PKCE code verifier and S256 challenge generation, anti-CSRF state token validation and expiration, token exchange, Windows Credential Locker / keyring storage, fallback opt-in checks, token refresh, and revocation endpoint calls.
- `tests/test_gmail_calendar.py`: Read-only Gmail listing and summarization, disclosure notice verification, date range validation, Calendar event listing and summarization, privacy audit log redaction (zero email bodies or event titles in action logs), persistent memory immutability, scope enforcement, and negative testing confirming no write tools exist.
- `tests/test_search_and_briefing.py`: Result limits, query validation, citation formatting, personal credential screening, search timeout & rate limit handling, daily briefing compilation, private data isolation, and safety assertions ensuring no write tools exist.
- `tests/test_reminders.py`: Reminder CRUD, active/completed filtering, confirmation before deletion, REST endpoints.
- `tests/test_memory.py`: Explicit memory storage, sensitive credential refusal, disable setting, clear all memory, REST endpoints.
- `tests/test_extension.py`: Origin checks, size limits, grounded analysis, practice quiz mode, privacy audit logs, forbidden tool assertions.
- `tests/test_app_control.py`: Allowlist enforcement, confirmation lifecycle.
- `tests/test_system_status.py`: Battery, storage, and memory status queries.
- `tests/test_screenshot.py`: Confirmation requirements, local storage verification.
- `tests/test_confirmation.py`: Token lifecycle, expiration cleanup, anti-tampering protection.
- `tests/test_security.py`: Path traversal attacks, file size caps, extension checks.
- `tests/test_workspace_tools.py` & `tests/test_notes_tools.py`: Workspace and notes operations.
- `tests/test_api.py` & `tests/test_api_phase2.py`: FastAPI routes, validation, and error handling.

---

## Supported Environments & Permissions

### 1. Operating Systems
- **Windows 10 / Windows 11 (64-bit)**: Primary target platform for full assistant companion features, including pre-approved Windows application control (`notepad`, `calculator`, `paint`, `explorer`, `cmd`), primary display screenshot capture, system hardware metrics (battery/storage/RAM via `psutil`), and native OS Credential Store (Windows Credential Locker via `keyring`).
- **macOS / Linux**: Fully supported for the core assistant backend, sandboxed workspace tools, notes, memory, local reminders, web search, daily briefing, Google OAuth read-only tools, mobile PWA, and Chrome extension. Windows-specific companion tools gracefully report unsupported platform errors when invoked on non-Windows hosts.

### 2. Supported Browsers
- **Google Chrome**: Version 115 or newer (supports Manifest V3, Web Speech API, and `activeTab`).
- **Microsoft Edge**: Version 115 or newer.
- **Mobile Browsers (PWA Companion)**: Chrome for Android, Safari for iOS (16.4+), Samsung Internet, Edge Mobile.

### 3. Required Permissions
- **Chrome Extension**:
  - `"activeTab"`: Temporary access strictly to the single tab the user explicitly selects when clicking "Read this page". Zero background tab inspection.
  - `"scripting"`: Executes safe, sandboxed content scripts to extract visible text or fill non-sensitive form fields.
  - **No `<all_urls>` permission**: The extension does not request or possess permission to read all websites.
- **Microphone**:
  - Requested exclusively on-demand when the user clicks **Push to Talk**. Audio is transcribed locally via the browser's native Web Speech API and placed into an editable text box. Zero audio is stored or transmitted to external servers.

---

## Setup, Updates & Troubleshooting

### Setup Instructions
1. Clone or download the repository to your local machine:
   ```powershell
   git clone https://github.com/Kshaurya-07/Jarvis.git D:\Jarvis
   cd D:\Jarvis
   ```
2. Create and activate a Python virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and set your configuration:
   ```powershell
   copy .env.example .env
   ```
4. Start the Jarvis backend server:
   ```powershell
   .\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```
5. Open Chrome, go to `chrome://extensions/`, enable Developer Mode, click **Load unpacked**, and select `D:\Jarvis\extension`.

### How to Update
```powershell
git pull origin main
.\.venv\Scripts\pip install -r requirements.txt --upgrade
.\.venv\Scripts\pytest -v
```

### Troubleshooting Guide

| Issue | Root Cause | Resolution |
| :--- | :--- | :--- |
| **Notice: GEMINI_API_KEY is not configured** | Missing or placeholder key in `.env` | Add your API key from [Google AI Studio](https://aistudio.google.com/) to `.env`. Jarvis runs in offline mode until configured. |
| **403 Forbidden: Host not authorized** | Attempted to access backend via unauthorized hostname or external IP | Access backend exclusively via `http://127.0.0.1:8000` or `http://localhost:8000` to prevent DNS rebinding attacks. |
| **403 Forbidden: Origin not authorized** | Request originated from an unauthorized remote website | Only `http://localhost`, `http://127.0.0.1`, and `chrome-extension://*` origins are permitted. |
| **413 Request Entity Too Large** | Request body payload exceeded 2 MB cap | Keep input text and page content within the configured size limits (`MAX_REQUEST_BODY_BYTES`). |
| **429 Too Many Requests** | Too many consecutive auth/confirmation failures | Wait 60 seconds for the rolling rate limit window to expire, then retry with valid tokens. |
| **Google Disconnected / Token Revoked** | Token was revoked in Google Account settings | Visit `http://127.0.0.1:8000/api/auth/google/url` to reconnect read-only access. |

---

## Privacy & Data Flow Architecture

- **Localhost-Only Default**: Jarvis binds strictly to `127.0.0.1:8000`. It is never exposed to the public internet, uses no port forwarding, and requires no cloud relay.
- **Zero Telemetry**: Jarvis contains zero analytics tracking, zero usage metrics, and zero automatic background uploads.
- **External Data Transmissions (Disclosed & Minimal)**:
  1. **Google Gemini API**: Transmits user prompt text, tool declarations, and user-approved screenshot/page text strictly when reasoning or summarization is explicitly requested.
  2. **Search Providers (Tavily/Google/Brave)**: Transmits non-sensitive search queries when web search is invoked. Queries are screened by `detect_sensitive_data()` to prevent leaking credentials.
  3. **Google APIs (Gmail & Calendar)**: Read-only API calls authenticated via OAuth tokens stored in the OS Credential Store.
- **Local Storage Isolation**:
  - `workspace/`: Sandboxed user files for file tools.
  - `notes/`: Local markdown notes.
  - `data/reminders.json`: Local reminder store.
  - `data/memories.json`: User-approved persistent knowledge.
  - `backups/`: Opt-in local backup snapshots with SHA-256 integrity checksums.
  - `logs/actions.jsonl`: Audit execution log with automated regex redaction of keys, tokens, emails, and passwords.

---

## Complete Uninstall & Data Removal Guide

To completely remove Jarvis and all associated local user data from your device:

1. **Disconnect Google OAuth & Revoke Remote Access**:
   ```powershell
   curl -X POST "http://127.0.0.1:8000/api/auth/google/disconnect"
   ```
   Visit [Google Account Permissions](https://myaccount.google.com/permissions) and ensure "Jarvis Assistant" is removed.
2. **Permanently Wipe Local Data Stores**:
   ```powershell
   curl -X POST "http://127.0.0.1:8000/api/data/clear" -H "Content-Type: application/json" -d '{"confirm": true, "confirmation_text": "DELETE ALL DATA"}'
   ```
3. **Remove Chrome Extension**:
   - Open Chrome and navigate to `chrome://extensions/`.
   - Locate **Jarvis Local Companion** and click **Remove**.
4. **Delete Application Directory & Virtual Environment**:
   ```powershell
   cd ..
   Remove-Item -Recurse -Force D:\Jarvis
   ```
5. **Verify Windows Credential Store**:
   - Open **Windows Credential Manager** > **Windows Credentials**.
   - Confirm that any entry named `Jarvis_Google_OAuth` has been removed.

---

## Known Limitations

1. **Option B Localhost Isolation**: The backend runs exclusively on `127.0.0.1:8000`. Direct phone-to-laptop remote execution across separate devices is not available without local network pairing. Use the companion on your host machine or via responsive browser emulation.
2. **Limited Browser Automation**: Automation is restricted to user-approved domains and low-risk actions (navigation, page reading, filling non-sensitive fields). Automated form submission, checkout, purchases, message transmission, and quiz completions are strictly prohibited. Sensitive fields (passwords, cards, CVVs, auth tokens) are completely excluded.
3. **Strictly Read-Only Integrations**: Gmail and Google Calendar tools are strictly read-only. Jarvis cannot send emails, delete messages, modify labels, create calendar events, or edit appointments.
4. **On-Demand Only**: Daily briefings, browser actions, and email/calendar summaries are generated purely on-demand when requested by the user. There are no background cron jobs, continuous sync daemons, or unsolicited desktop notifications.
5. **No Web Scraping**: Web search uses official APIs (Tavily/Google/Brave); Jarvis never scrapes web pages or automates browser actions without explicit instruction.
6. **Token Expiration**: If a refresh token is revoked on Google Account settings, Jarvis clears cached credentials and requires the user to reconnect via `/api/auth/google/url`.
7. **Localhost Dependency**: All APIs, OAuth callbacks, Chrome extension, and mobile companion interactions are bound strictly to `http://127.0.0.1:8000`.

