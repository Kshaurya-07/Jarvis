# Jarvis — Personal AI Assistant Backend (Phase 1: Core)

Jarvis is a modular, secure personal AI assistant foundation built with **FastAPI** and the official **Google Gen AI Python SDK**. It provides a decoupled backend architecture ready for any future desktop or web frontend.

---

## Architecture Overview

```
Jarvis/
├── app/
│   ├── main.py                  # FastAPI application setup, CORS, lifespan, exception handlers
│   ├── api/
│   │   ├── routes.py            # API endpoints: /health, /api/chat, /api/tools, /api/actions
│   │   └── schemas.py           # Pydantic schemas for request and response payloads
│   ├── core/
│   │   ├── config.py            # Application settings via pydantic-settings
│   │   ├── security.py          # PathGuard security, directory traversal defense, sanitization
│   │   └── logger.py            # Action audit logger (never logs secrets or sensitive content)
│   ├── services/
│   │   └── agent_service.py     # Gemini client, tool-calling dispatch loop, error handling
│   └── tools/
│       ├── base.py              # Base tool schemas and ToolResult models
│       ├── workspace_tools.py   # list_files, read_text_file (workspace bound)
│       ├── notes_tools.py       # create_note, search_notes (notes bound)
│       ├── registry.py          # Central registry with server-side argument validation
│       └── future_interfaces.py # Contracts & TODO stubs for future phases
├── tests/                       # Complete pytest suite (34 unit and integration tests)
├── .env.example                 # Example environment variables template
├── requirements.txt             # Python dependencies
└── README.md                    # Project documentation and API reference
```

---

## Phase 1 Capabilities

### 1. Health-Check Endpoints
- `GET /health` and `GET /api/health`
- Reports server status, version, storage path validation, and active approved tools.

### 2. Chat Endpoint with Gemini Function Calling
- `POST /api/chat`
- Accepts user messages, sends them to Gemini (`gemini-2.5-flash`), executes approved tools when the model decides to invoke them, and synthesizes a clear final response.

### 3. Core Approved Tools
- **`list_files`**: Lists files and subfolders within the explicitly configured `workspace/` folder.
- **`read_text_file`**: Reads plain text and code files (`.txt`, `.md`, `.py`, `.json`, etc.) within the workspace.
- **`create_note`**: Saves a new markdown note in the `notes/` directory with automatic title sanitization and timestamps.
- **`search_notes`**: Case-insensitive substring search across saved notes, returning matching files and line snippets.

### 4. Safety and Control Protections
- **Strict Path Sandboxing**: Enforces `pathlib.Path.resolve()` checks. Any path escaping the designated folder via `../`, absolute root drives, or null bytes is immediately rejected with `SecurityViolationError`.
- **Binary & Size Restrictions**: Blocks execution or reading of binary/executable files and caps file reads (default 1 MB) to prevent denial of service.
- **Server-Side Validation**: Never trusts model-generated arguments blindly; every parameter is validated on the server.
- **Zero Shell / Execution Access**: No arbitrary shell, PowerShell, or Python execution.
- **Safe Audit Logging**: Every tool execution is recorded with timestamp, tool name, execution time, and success/failure status. Secret keys and full file contents are never logged.
- **Localhost Only**: Binds strictly to `127.0.0.1` by default.

---

## Getting Started

### Prerequisites
- Python 3.10+ (tested on Python 3.15)
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)

### 1. Create Virtual Environment and Install Dependencies

```bash
# Create virtual environment
python -m venv .venv

# Activate on Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On macOS/Linux:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
copy .env.example .env
```

Edit `.env` and set your Gemini API key:

```ini
GEMINI_API_KEY=your_actual_api_key_here
HOST=127.0.0.1
PORT=8000
GEMINI_MODEL=gemini-2.5-flash
WORKSPACE_DIR=./workspace
NOTES_DIR=./notes
```

*(Note: If `GEMINI_API_KEY` is omitted, the server still boots, health checks pass, and the chat endpoint safely informs you that the API key is required).*

### 3. Run the Backend Server

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Interactive OpenAPI documentation is available at:
`http://127.0.0.1:8000/docs`

---

## API Usage Examples (`curl`)

### Health Check
```bash
curl -X GET http://127.0.0.1:8000/health
```

**Response:**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "gemini_configured": true,
  "workspace_directory": "D:\\Jarvis\\workspace",
  "notes_directory": "D:\\Jarvis\\notes",
  "active_tools": ["list_files", "read_text_file", "create_note", "search_notes"]
}
```

### List Approved Tools
```bash
curl -X GET http://127.0.0.1:8000/api/tools
```

### Chat with Jarvis (File & Note Management)

#### Example 1: Create a Note
```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Please create a note titled Weekly Goals and write down: Finish Jarvis Phase 1 backend and review tests."}'
```

#### Example 2: Search Notes
```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Search my notes for Weekly Goals."}'
```

#### Example 3: List Workspace Files
```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What files are in my workspace folder?"}'
```

#### Example 4: Read a Workspace File
```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Read the contents of notes.txt in my workspace."}'
```

### Inspect Audit Action Logs
```bash
curl -X GET http://127.0.0.1:8000/api/actions
```

---

## Running the Test Suite

Jarvis includes comprehensive unit and integration tests covering security boundaries, path traversal attacks, tool functionality, argument validation, and API routes.

```bash
pytest -v
```

All 34 tests execute in an isolated temporary environment.

---

## Future Roadmap (Planned Interfaces)

The following capabilities are specified in [`app/tools/future_interfaces.py`](file:///d:/Jarvis/app/tools/future_interfaces.py) with strict contracts and will be implemented in subsequent phases:
- **Phase 2: Browser & Control**: Browser extension for user-approved active tabs, screenshot understanding, visible laptop UI control with explicit confirmation prompts.
- **Phase 2: Memory & Knowledge**: Persistent memory with user-controlled inspection and deletion; live web search.
- **Phase 3: Multimodal & Productivity**: Voice I/O (speech-to-text and text-to-speech); Gmail & Google Calendar integrations using official OAuth 2.0 flows.
- **Phase 4: Client Ecosystem**: Mobile-friendly web client and desktop tray companion.
