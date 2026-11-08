# Jarvis — Personal AI Assistant Backend, Laptop/Browser Companion & Daily Briefing

Jarvis is a modular, secure personal AI assistant backend, Windows companion, Chrome study extension, and on-demand briefing engine built with **FastAPI** and the official **Google Gen AI Python SDK**. It provides a decoupled backend architecture ready for any future desktop or web frontend.

---

## Architecture Overview

```
Jarvis/
├── app/
│   ├── main.py                  # FastAPI application setup, strict origin validation, CORS, lifespan
│   ├── api/
│   │   ├── routes.py            # API endpoints: /health, /api/chat, /api/tools, /api/confirm, /api/extension/read-page, /api/reminders, /api/memories, /api/briefing
│   │   └── schemas.py           # Pydantic schemas for request and response payloads
│   ├── core/
│   │   ├── config.py            # Application settings via pydantic-settings
│   │   ├── confirmation.py      # ConfirmationManager for state-changing operations
│   │   ├── security.py          # PathGuard security, OS checks, directory traversal defense
│   │   └── logger.py            # Action audit logger (never logs secrets or sensitive content)
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
│       ├── registry.py          # Central registry with server-side argument validation
│       └── future_interfaces.py # Contracts & TODO stubs for future phases
├── extension/                   # Minimal Chrome Extension (Manifest V3)
│   ├── manifest.json            # Manifest V3 (activeTab, scripting only)
│   ├── popup.html               # Extension UI popup with voice push-to-talk & TTS
│   ├── popup.js                 # Web Speech API recognition, local TTS, abort control
│   ├── popup.css                # Extension styles
│   └── icons/                   # Extension icons (16px, 48px, 128px)
├── tests/                       # Complete pytest suite (94 unit and integration tests)
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
   - **No Gmail / Calendar Integration**: Kept strictly local; external mail/calendar integrations are not included.

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

## API Usage Examples (`curl`)

### 1. On-Demand Daily Briefing
```bash
# Local briefing (reminders & notes only)
curl -X GET "http://127.0.0.1:8000/api/briefing?include_web_summary=false"

# Briefing with general web overview
curl -X GET "http://127.0.0.1:8000/api/briefing?include_web_summary=true&web_topics=latest%20tech%20news"
```

### 2. Chat with Web Search
```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the latest stable release of Python and what features were introduced? Cite your sources."}'
```

### 3. Reminders & Memory
```bash
# Create a reminder
curl -X POST http://127.0.0.1:8000/api/reminders \
  -H "Content-Type: application/json" \
  -d '{"title": "Algorithms Exam Study", "due_time": "Today at 2:00 PM", "notes": "Review Dynamic Programming"}'

# Remember a preference
curl -X POST http://127.0.0.1:8000/api/memories \
  -H "Content-Type: application/json" \
  -d '{"key": "preferred_language", "content": "Python 3 and TypeScript"}'
```

---

## Testing

Run the complete test suite:

```powershell
.\.venv\Scripts\pytest -v
```

**Test Coverage (94 tests total)**:
- `tests/test_search_and_briefing.py`: Result limits, query validation, citation formatting, personal credential screening, search timeout & rate limit handling, daily briefing compilation, private data isolation, and verification that no Gmail/Calendar tools exist.
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

## Known Limitations

1. **On-Demand Only**: Daily briefings are not sent automatically and do not run on background cron schedules. They are generated only when the user queries Jarvis.
2. **No Web Scraping**: Web search relies exclusively on structured search provider APIs (Tavily/Google/Brave); Jarvis does not scrape search engine result pages or navigate websites automatically.
3. **No Gmail / Google Calendar Integration**: Local reminders and notes are supported; email and cloud calendar OAuth integrations are reserved for a future phase.
4. **Localhost Dependency**: All APIs and Chrome extension interactions operate exclusively on `http://127.0.0.1:8000`.
