import re
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles


from app import __version__
from app.api.routes import router
from app.core.config import settings, ConfigurationError
from app.core.logger import app_logger
from app.core.security import SecurityViolationError, InvalidPathError

# Approved exact static Vercel production and verified preview origins
APPROVED_STATIC_ORIGINS = [
    "https://jarvis-kumar-shaurya.vercel.app",
    "https://jarvis-eta-ten-83.vercel.app",
]

# Regex permitting localhost, 127.0.0.1 (any port), and Chrome extension origins
ALLOWED_ORIGIN_REGEX = re.compile(
    r"^(http://(localhost|127\.0\.0\.1)(:\d+)?|chrome-extension://[a-zA-Z0-9]+)$"
)

# Regex permitting localhost, 127.0.0.1, or testclient Host headers (DNS rebinding defense)
ALLOWED_HOST_REGEX = re.compile(
    r"^(localhost|127\.0\.0\.1|testserver)(:\d+)?$"
)

# Regex permitting private Tailscale MagicDNS addresses (*.ts.net) or Tailscale CGNAT IP (100.x.y.z)
TAILSCALE_HOST_REGEX = re.compile(
    r"^([a-zA-Z0-9-]+\.[a-zA-Z0-9-]+\.ts\.net|100\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?$"
)


def is_allowed_origin(origin: str) -> bool:
    """
    Validate whether an Origin header belongs to an approved origin.
    Permits exact Vercel production origin, verified preview origin, localhost,
    Chrome extension origins, and custom origins configured in settings.ALLOWED_ORIGINS.
    Rejects all unauthorized origins.
    """
    if not origin:
        return True  # Direct non-browser requests (e.g. curl, test client)
    clean_origin = origin.strip().rstrip("/")
    if clean_origin in APPROVED_STATIC_ORIGINS:
        return True
    if clean_origin in settings.ALLOWED_ORIGINS:
        return True
    return bool(ALLOWED_ORIGIN_REGEX.match(origin))


def is_allowed_host(host_header: str) -> bool:
    """Validate whether a Host header matches approved localhost or Tailscale Serve addresses."""
    if not host_header:
        return True
    host_clean = host_header.strip()
    if bool(ALLOWED_HOST_REGEX.match(host_clean)):
        return True
    if bool(TAILSCALE_HOST_REGEX.match(host_clean)):
        return True
    if settings.TAILSCALE_HOST and host_clean.startswith(settings.TAILSCALE_HOST):
        return True
    return False


def is_allowed_referer(referer: str) -> bool:
    """Validate whether a Referer header originates from an approved origin."""
    if not referer:
        return True
    for approved in APPROVED_STATIC_ORIGINS:
        if referer.startswith(approved):
            return True
    for custom in settings.ALLOWED_ORIGINS:
        if referer.startswith(custom):
            return True
    return bool(
        referer.startswith("http://localhost")
        or referer.startswith("http://127.0.0.1")
        or referer.startswith("chrome-extension://")
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager: validates settings, initializes directories, logs startup."""
    settings.resolve_paths()
    try:
        warnings = settings.validate_configuration()
        for w in warnings:
            app_logger.warning("%s", w)
    except ConfigurationError as e:
        app_logger.error("Configuration validation failed on startup: %s", e)
        raise

    app_logger.info("=" * 50)
    app_logger.info("Jarvis Agent Backend starting up (v%s)", __version__)
    app_logger.info("Workspace directory: %s", settings.WORKSPACE_DIR)
    app_logger.info("Notes directory: %s", settings.NOTES_DIR)
    app_logger.info("Data directory: %s", settings.DATA_DIR)
    app_logger.info("Backups directory: %s", settings.BACKUPS_DIR)
    app_logger.info("Bound to: %s:%d (remote access: %s)", settings.HOST, settings.PORT, settings.ALLOW_REMOTE_ACCESS)
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


@app.middleware("http")
async def request_size_limit_middleware(request: Request, call_next):
    """
    Enforces maximum payload size from Content-Length header to prevent DOS/memory exhaustion.
    Returns 413 if content-length exceeds MAX_REQUEST_BODY_BYTES.
    """
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            length = int(content_length)
            if length > settings.MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"Request entity too large ({length} bytes). "
                            f"Maximum allowed size is {settings.MAX_REQUEST_BODY_BYTES} bytes."
                        )
                    },
                )
        except ValueError:
            pass
    return await call_next(request)


@app.middleware("http")
async def origin_validation_middleware(request: Request, call_next):
    """
    Strict origin, host, and referer validation middleware:
    Blocks unauthorized remote web origins, DNS rebinding attacks, and cross-site referers.
    """
    # 1. DNS Rebinding defense via Host header
    host = request.headers.get("host")
    if host and not is_allowed_host(host):
        app_logger.warning("Rejected unauthorized Host header: %s", host)
        return JSONResponse(
            status_code=403,
            content={
                "detail": (
                    f"Access denied: Host '{host}' is not authorized. "
                    "Only localhost, 127.0.0.1, and authorized test environments are permitted."
                )
            },
        )

    # 2. Origin validation
    origin = request.headers.get("origin")
    if origin and not is_allowed_origin(origin):
        app_logger.warning("Rejected unauthorized origin: %s", origin)
        return JSONResponse(
            status_code=403,
            content={
                "detail": (
                    f"Access denied: Origin '{origin}' is not authorized. "
                    "Only localhost and Chrome extension origins are permitted."
                )
            },
        )

    # 3. Referer validation for state-changing requests without Origin
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        referer = request.headers.get("referer")
        if referer and not origin and not is_allowed_referer(referer):
            app_logger.warning("Rejected unauthorized referer on %s: %s", request.method, referer)
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        f"Access denied: Referer '{referer}' is not authorized. "
                        "State-changing actions must originate from localhost or Chrome extensions."
                    )
                },
            )

    return await call_next(request)


# Enable CORS for localhost, Chrome extensions, and approved Vercel static PWA origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=APPROVED_STATIC_ORIGINS + settings.ALLOWED_ORIGINS,
    allow_origin_regex=r"^(http://(localhost|127\.0\.0\.1)(:\d+)?|chrome-extension://[a-zA-Z0-9]+)$",
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

# Phase 7: Mount Mobile Web App & PWA Companion
mobile_dir = Path(__file__).resolve().parent.parent / "mobile"
if mobile_dir.exists():
    app.mount("/mobile", StaticFiles(directory=str(mobile_dir), html=True), name="mobile")

# Phase 10: Mount Local Fictional Demo Sandbox
demo_dir = Path(__file__).resolve().parent.parent / "demo"
if demo_dir.exists():
    app.mount("/demo", StaticFiles(directory=str(demo_dir), html=True), name="demo")

# Vision landing page: static, no backend dependency
landing_dir = Path(__file__).resolve().parent.parent / "landing"
if landing_dir.exists():
    app.mount("/landing", StaticFiles(directory=str(landing_dir), html=True), name="landing")


@app.get("/demo", tags=["Demo"])
async def demo_redirect():
    """Redirect to demo interface with trailing slash."""
    return RedirectResponse(url="/demo/")


@app.get("/", tags=["Companion"])
async def root_redirect():
    """Redirect root browser requests to the mobile companion interface."""
    return RedirectResponse(url="/mobile/")

