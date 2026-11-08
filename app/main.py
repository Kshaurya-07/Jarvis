from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import router
from app.core.config import settings
from app.core.logger import app_logger
from app.core.security import SecurityViolationError, InvalidPathError


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager: sets up storage directories and logs startup."""
    settings.resolve_paths()
    app_logger.info("=" * 50)
    app_logger.info("Jarvis Agent Backend starting up (v%s)", __version__)
    app_logger.info("Workspace directory: %s", settings.WORKSPACE_DIR)
    app_logger.info("Notes directory: %s", settings.NOTES_DIR)
    app_logger.info("Bound to: %s:%d", settings.HOST, settings.PORT)
    app_logger.info("=" * 50)
    yield
    app_logger.info("Jarvis Agent Backend shutting down.")


app = FastAPI(
    title="Jarvis AI Assistant Backend",
    description=(
        "Core agent and tool backend for Jarvis personal assistant. "
        "Provides safe workspace file operations, notes management, and Gemini tool calling."
    ),
    version=__version__,
    lifespan=lifespan,
)

# Enable CORS for local development and future frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SecurityViolationError)
async def security_violation_handler(request: Request, exc: SecurityViolationError):
    app_logger.warning("Security violation intercepted: %s", exc)
    return JSONResponse(
        status_code=403,
        content={"detail": "Security violation: Access denied outside authorized boundaries."},
    )


@app.exception_handler(InvalidPathError)
async def invalid_path_handler(request: Request, exc: InvalidPathError):
    return JSONResponse(
        status_code=400,
        content={"detail": f"Invalid path parameter: {str(exc)}"},
    )


# Mount router under /api as well as root for standard health-check
app.include_router(router, prefix="/api")
app.include_router(router)  # Allows /health directly at root as well as /api/health
