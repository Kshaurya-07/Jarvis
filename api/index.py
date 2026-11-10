"""Vercel serverless entrypoint for the Jarvis FastAPI backend.

Vercel runs this file as a serverless function: every ``/api/*`` request
is routed here (see vercel.json rewrites). The FastAPI app itself is
unchanged — the same ``app`` also runs under ``uvicorn`` locally for
development. State lives outside the function: sessions are stateless
JWTs, user data lives in Postgres (``DATABASE_URL``), BYOK keys are
encrypted in Postgres. Nothing is kept in memory that must survive
between invocations (see README "Vercel limits").
"""
import sys
from pathlib import Path

# This file lives at <repo>/api/index.py; the FastAPI package lives at
# <repo>/backend/app. Add backend/ to sys.path so `import app...` works.
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.main import app  # noqa: E402

# Vercel's Python runtime looks for `app` in this module.
__all__ = ["app"]
