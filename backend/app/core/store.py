"""Pluggable per-user storage (Phase 12, cloud-first).

THE key serverless fact: **Vercel serverless functions have no persistent
filesystem.** Anything written to ``workspace/`` / ``data/`` on Vercel is
gone on the next invocation. So user data must live in an external store
in production.

Storage backends (chosen by ``DATABASE_URL``):
* **Postgres (production)** — Neon serverless Postgres (free tier), one
  database for every entity: notes, memories, reminders, encrypted BYOK
  keys, chat history, action log, usage counters. Chosen over Vercel KV
  (Redis — wrong shape for notes/documents, no queries) and Vercel Blob
  (object storage — no queries, no transactions). Standard SQL, one
  connection string, works with Supabase Postgres too (same wire
  protocol). Every query is scoped ``WHERE user_ns = ...``.
* **Files (local dev / tests)** — the historical layout, namespaced per
  user under ``data/users/<namespace>/`` etc. (see ``user_context``).
  Used whenever ``DATABASE_URL`` is unset, so ``uvicorn`` local dev and
  the test suite work with zero setup.

``get_user_store()`` picks the backend; tools and routes only talk to the
``UserStore`` interface, never to files or SQL directly.
"""
from __future__ import annotations

import datetime
import json
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.user_context import UserIdentity, resolve_user, user_paths

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jarvis_users (
    user_ns TEXT PRIMARY KEY,
    email TEXT,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS jarvis_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_ns TEXT NOT NULL REFERENCES jarvis_users(user_ns) ON DELETE CASCADE,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_ns, filename)
);
CREATE TABLE IF NOT EXISTS jarvis_memories (
    user_ns TEXT NOT NULL REFERENCES jarvis_users(user_ns) ON DELETE CASCADE,
    memory_key TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_ns, memory_key)
);
CREATE TABLE IF NOT EXISTS jarvis_reminders (
    id TEXT PRIMARY KEY,
    user_ns TEXT NOT NULL REFERENCES jarvis_users(user_ns) ON DELETE CASCADE,
    title TEXT NOT NULL,
    due_time TEXT NOT NULL,
    notes TEXT,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS jarvis_user_keys (
    user_ns TEXT PRIMARY KEY REFERENCES jarvis_users(user_ns) ON DELETE CASCADE,
    encrypted_key BYTEA NOT NULL,
    key_hint TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS jarvis_chat_history (
    id BIGSERIAL PRIMARY KEY,
    user_ns TEXT NOT NULL REFERENCES jarvis_users(user_ns) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS jarvis_action_log (
    id BIGSERIAL PRIMARY KEY,
    user_ns TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    details TEXT,
    execution_time_ms DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS jarvis_usage (
    id BIGSERIAL PRIMARY KEY,
    user_ns TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_user_created ON jarvis_chat_history (user_ns, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_user_created ON jarvis_usage (user_ns, kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_action_user_created ON jarvis_action_log (user_ns, created_at DESC);
"""


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class UserStore:
    """Interface every storage backend implements (all methods user-scoped)."""

    name = "base"

    # -- notes --
    def create_note(self, user: UserIdentity, title: str, content: str) -> Dict[str, Any]:
        raise NotImplementedError

    def search_notes(self, user: UserIdentity, query: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def list_notes(self, user: UserIdentity) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def delete_note(self, user: UserIdentity, filename: str) -> bool:
        raise NotImplementedError

    # -- memories --
    def list_memories(self, user: UserIdentity) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def put_memory(self, user: UserIdentity, key: str, content: str) -> Dict[str, Any]:
        raise NotImplementedError

    def delete_memory(self, user: UserIdentity, key: str) -> bool:
        raise NotImplementedError

    def clear_memories(self, user: UserIdentity) -> int:
        raise NotImplementedError

    # -- reminders --
    def list_reminders(self, user: UserIdentity, include_completed: bool = False) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def add_reminder(self, user: UserIdentity, title: str, due_time: str, notes: Optional[str]) -> Dict[str, Any]:
        raise NotImplementedError

    def complete_reminder(self, user: UserIdentity, reminder_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def delete_reminder(self, user: UserIdentity, reminder_id: str) -> bool:
        raise NotImplementedError

    def get_reminder(self, user: UserIdentity, reminder_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    # -- BYOK key (encrypted bytes + public hint) --
    def save_key(self, user: UserIdentity, encrypted: bytes, hint: str) -> None:
        raise NotImplementedError

    def load_key(self, user: UserIdentity) -> Optional[bytes]:
        raise NotImplementedError

    def key_meta(self, user: UserIdentity) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def delete_key(self, user: UserIdentity) -> bool:
        raise NotImplementedError

    # -- chat history (cross-device sync) --
    def append_chat(self, user: UserIdentity, role: str, content: str) -> None:
        raise NotImplementedError

    def list_chat(self, user: UserIdentity, limit: int = 50) -> List[Dict[str, Any]]:
        raise NotImplementedError

    # -- action log --
    def append_action(self, user: UserIdentity, entry: Dict[str, Any]) -> None:
        raise NotImplementedError

    def recent_actions(self, user: UserIdentity, limit: int = 50) -> List[Dict[str, Any]]:
        raise NotImplementedError

    # -- usage counters (per-user Gemini-call caps) --
    def record_usage(self, user: UserIdentity, kind: str) -> None:
        raise NotImplementedError

    def count_usage_since(self, user: UserIdentity, kind: str, since_ts: float) -> int:
        raise NotImplementedError

    # -- whole-account wipe / export helpers --
    def clear_all_user_data(self, user: UserIdentity) -> Dict[str, int]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# File backend (local dev / tests)
# ---------------------------------------------------------------------------

class FileUserStore(UserStore):
    name = "file"

    # notes
    def create_note(self, user, title, content):
        from app.core.security import resolve_safe_path, sanitize_filename

        paths = user_paths(user)
        clean_title = sanitize_filename(title)
        filename = f"{clean_title}.md"
        target = resolve_safe_path(base_dir=paths.notes_dir, user_path=filename,
                                   allow_root=False, must_exist=False)
        if target.exists():
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{clean_title}_{ts}.md"
            target = resolve_safe_path(base_dir=paths.notes_dir, user_path=filename,
                                       allow_root=False, must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        formatted = f"# {title.strip()}\n*Created: {now_iso}*\n\n{content}\n"
        target.write_text(formatted, encoding="utf-8")
        return {"title": title.strip(), "filename": target.name,
                "relative_path": target.name, "bytes_written": len(formatted.encode("utf-8"))}

    def _read_note_files(self, user):
        paths = user_paths(user)
        out = []
        if paths.notes_dir.exists():
            for fp in sorted(paths.notes_dir.glob("*.md")) + sorted(paths.notes_dir.glob("*.txt")):
                if fp.is_file():
                    try:
                        out.append((fp, fp.read_text(encoding="utf-8", errors="replace")))
                    except Exception:
                        continue
        return out

    def delete_note(self, user, filename):
        p = user_paths(user).notes_dir / Path(filename).name
        if p.exists() and p.is_file():
            p.unlink()
            return True
        return False

    def search_notes(self, user, query):
        term = query.strip().lower()
        matches = []
        for fp, text in self._read_note_files(user):
            lines = text.splitlines()
            hits = [{"line_number": i + 1, "text": ln.strip()[:200]}
                    for i, ln in enumerate(lines) if term in ln.lower()]
            if hits:
                matches.append({"filename": fp.name, "relative_path": fp.name,
                                "total_matches_in_file": len(hits), "snippets": hits[:5]})
        return matches

    def list_notes(self, user):
        items = []
        for fp, text in self._read_note_files(user):
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            items.append({"filename": fp.name, "title": lines[0].lstrip("# ").strip() if lines else fp.stem,
                          "content": text,
                          "modified_at": datetime.datetime.fromtimestamp(fp.stat().st_mtime, tz=datetime.timezone.utc).isoformat()})
        return items

    # memories / reminders via the existing JSON storage classes, per-user files
    def _mem_storage(self, user):
        from app.tools.memory_tools import MemoryStorage

        return MemoryStorage(file_path=user_paths(user).memories_file)

    def _rem_storage(self, user):
        from app.tools.reminders_tools import RemindersStorage

        return RemindersStorage(file_path=user_paths(user).reminders_file)

    def list_memories(self, user):
        return [m.model_dump() for m in self._mem_storage(user).list_all()]

    def put_memory(self, user, key, content):
        return self._mem_storage(user).put(key=key, content=content).model_dump()

    def delete_memory(self, user, key):
        return self._mem_storage(user).delete(key)

    def clear_memories(self, user):
        return self._mem_storage(user).clear()

    def list_reminders(self, user, include_completed=False):
        return [r.model_dump() for r in self._rem_storage(user).list_all(include_completed=include_completed)]

    def add_reminder(self, user, title, due_time, notes):
        return self._rem_storage(user).add(title=title, due_time=due_time, notes=notes).model_dump()

    def complete_reminder(self, user, reminder_id):
        r = self._rem_storage(user).complete(reminder_id)
        return r.model_dump() if r else None

    def delete_reminder(self, user, reminder_id):
        return self._rem_storage(user).delete(reminder_id)

    def get_reminder(self, user, reminder_id):
        r = self._rem_storage(user).get_by_id(reminder_id)
        return r.model_dump() if r else None

    # BYOK key
    def save_key(self, user, encrypted, hint):
        paths = user_paths(user)
        paths.data_dir.mkdir(parents=True, exist_ok=True)
        import os

        fd = os.open(str(paths.gemini_key_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(encrypted)
        with open(paths.gemini_key_meta_file, "w", encoding="utf-8") as f:
            json.dump({"hint": hint, "created_at": _utcnow_iso()}, f)

    def load_key(self, user):
        p = user_paths(user).gemini_key_file
        if not p.exists():
            return None
        try:
            return p.read_bytes()
        except Exception:
            return None

    def key_meta(self, user):
        p = user_paths(user).gemini_key_meta_file
        if not p.exists():
            return None
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def delete_key(self, user):
        paths = user_paths(user)
        removed = False
        for p in (paths.gemini_key_file, paths.gemini_key_meta_file):
            if p.exists():
                p.unlink()
                removed = True
        return removed

    # chat history (JSONL, one line per turn)
    def append_chat(self, user, role, content):
        paths = user_paths(user)
        paths.data_dir.mkdir(parents=True, exist_ok=True)
        rec = {"role": role, "content": content, "created_at": _utcnow_iso()}
        with open(paths.chat_history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def list_chat(self, user, limit=50):
        p = user_paths(user).chat_history_file
        if not p.exists():
            return []
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return []
        out = []
        for ln in lines[-limit:]:
            try:
                rec = json.loads(ln)
                if isinstance(rec, dict) and rec.get("role") in ("user", "assistant"):
                    out.append(rec)
            except Exception:
                continue
        return out

    # action log (JSONL)
    def append_action(self, user, entry):
        paths = user_paths(user)
        paths.action_log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(paths.action_log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def recent_actions(self, user, limit=50):
        # In-memory entries are the live source; the file is the durable one.
        # File backend: read the tail of the JSONL file.
        p = user_paths(user).action_log_file
        if not p.exists():
            return []
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return []
        out = []
        for ln in lines[-limit:]:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        return out

    # usage: in-memory counters (file mode only; Postgres mode counts in DB)
    _usage: Dict[str, List[float]] = {}

    def record_usage(self, user, kind):
        key = f"{resolve_user(user).namespace}:{kind}"
        self._usage.setdefault(key, []).append(time.time())

    def count_usage_since(self, user, kind, since_ts):
        key = f"{resolve_user(user).namespace}:{kind}"
        now = time.time()
        stamps = [t for t in self._usage.get(key, []) if t >= since_ts]
        self._usage[key] = stamps
        return len(stamps)

    def clear_all_user_data(self, user):
        paths = user_paths(user)
        counts = {"notes": 0, "reminders": 0, "memories": 0, "screenshots": 0}
        if paths.notes_dir.exists():
            for fp in list(paths.notes_dir.glob("*.md")):
                try:
                    fp.unlink()
                    counts["notes"] += 1
                except Exception:
                    pass
        if paths.screenshots_dir.exists():
            for fp in list(paths.screenshots_dir.glob("*.png")):
                try:
                    fp.unlink()
                    counts["screenshots"] += 1
                except Exception:
                    pass
        counts["reminders"] = len(self.list_reminders(user, include_completed=True))
        if paths.reminders_file.exists():
            paths.reminders_file.unlink()
        counts["memories"] = self.clear_memories(user)
        return counts


# ---------------------------------------------------------------------------
# Postgres backend (production on Vercel + Neon)
# ---------------------------------------------------------------------------

class PostgresUserStore(UserStore):
    name = "postgres"

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._schema_ready = False

    def _connect(self):
        import psycopg

        return psycopg.connect(self.dsn, autocommit=True)

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
        self._schema_ready = True

    def _ensure_user(self, cur, user: UserIdentity) -> None:
        cur.execute(
            "INSERT INTO jarvis_users (user_ns, email, display_name) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_ns) DO UPDATE SET email = EXCLUDED.email, "
            "display_name = EXCLUDED.display_name, updated_at = now()",
            (user.namespace, user.email, user.name),
        )

    @staticmethod
    def _decode_row(row: Dict[str, Any]) -> Dict[str, Any]:
        """Decode any bytes values to str.

        Defensive: a Postgres whose database encoding is not UTF-8 (e.g. a
        misconfigured self-hosted server; Neon/Supabase are UTF-8) makes
        psycopg return TEXT columns as bytes. Decoding here keeps every
        caller working with plain strings either way.
        """
        return {
            k: (v.decode("utf-8", "replace") if isinstance(v, bytes) and k != "encrypted_key" else v)
            for k, v in row.items()
        }

    def _fetch(self, sql: str, params=()):
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [d.name for d in cur.description] if cur.description else []
                return [self._decode_row(dict(zip(cols, row))) for row in cur.fetchall()]

    def _exec(self, sql: str, params=(), fetch_one=False):
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if fetch_one:
                    row = cur.fetchone()
                    if row is None:
                        return None
                    cols = [d.name for d in cur.description]
                    return self._decode_row(dict(zip(cols, row)))
                return cur.rowcount

    # notes
    def create_note(self, user, title, content):
        from app.core.security import sanitize_filename

        clean = sanitize_filename(title)
        filename = f"{clean}.md"
        now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        formatted = f"# {title.strip()}\n*Created: {now_iso}*\n\n{content}\n"
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._ensure_user(cur, user)
                cur.execute(
                    "SELECT filename FROM jarvis_notes WHERE user_ns=%s AND filename=%s",
                    (user.namespace, filename),
                )
                if cur.fetchone():
                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"{clean}_{ts}.md"
                cur.execute(
                    "INSERT INTO jarvis_notes (user_ns, title, filename, content) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (user_ns, filename) DO UPDATE "
                    "SET title=EXCLUDED.title, content=EXCLUDED.content, updated_at=now()",
                    (user.namespace, title.strip(), filename, formatted),
                )
        return {"title": title.strip(), "filename": filename,
                "relative_path": filename, "bytes_written": len(formatted.encode("utf-8"))}

    def delete_note(self, user, filename):
        p = user_paths(user).notes_dir / Path(filename).name
        if p.exists() and p.is_file():
            p.unlink()
            return True
        return False

    def search_notes(self, user, query):
        rows = self._fetch(
            "SELECT filename, content FROM jarvis_notes WHERE user_ns=%s ORDER BY updated_at DESC",
            (user.namespace,),
        )
        term = query.strip().lower()
        matches = []
        for row in rows:
            lines = (row["content"] or "").splitlines()
            hits = [{"line_number": i + 1, "text": ln.strip()[:200]}
                    for i, ln in enumerate(lines) if term in ln.lower()]
            if hits:
                matches.append({"filename": row["filename"], "relative_path": row["filename"],
                                "total_matches_in_file": len(hits), "snippets": hits[:5]})
        return matches

    def list_notes(self, user):
        rows = self._fetch(
            "SELECT filename, title, content, updated_at FROM jarvis_notes "
            "WHERE user_ns=%s ORDER BY updated_at DESC",
            (user.namespace,),
        )
        return [{"filename": r["filename"], "title": r["title"], "content": r["content"],
                 "modified_at": r["updated_at"].isoformat() if r.get("updated_at") else None}
                for r in rows]

    def delete_note(self, user, filename):
        n = self._exec("DELETE FROM jarvis_notes WHERE user_ns=%s AND filename=%s",
                       (user.namespace, filename))
        return n > 0

    # memories
    def list_memories(self, user):
        rows = self._fetch(
            "SELECT memory_key AS key, content, created_at, updated_at FROM jarvis_memories "
            "WHERE user_ns=%s ORDER BY memory_key",
            (user.namespace,),
        )
        return [{"key": r["key"], "content": r["content"],
                 "created_at": r["created_at"].isoformat() if r.get("created_at") else _utcnow_iso(),
                 "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else _utcnow_iso()}
                for r in rows]

    def put_memory(self, user, key, content):
        clean_key = key.strip().lower()
        now = _utcnow_iso()
        # User row must exist first (jarvis_memories references jarvis_users).
        self._exec(
            "INSERT INTO jarvis_users (user_ns, email, display_name) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_ns) DO NOTHING",
            (user.namespace, user.email, user.name),
        )
        row = self._exec(
            "INSERT INTO jarvis_memories (user_ns, memory_key, content) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_ns, memory_key) DO UPDATE SET content=EXCLUDED.content, "
            "updated_at=now() RETURNING memory_key AS key, content, created_at, updated_at",
            (user.namespace, clean_key, content.strip()), fetch_one=True,
        )
        # _exec opens its own connection; ensure user row exists first via a
        # separate upsert (no-op if already present).
        if row:
            row["created_at"] = row["created_at"].isoformat() if row.get("created_at") else now
            row["updated_at"] = row["updated_at"].isoformat() if row.get("updated_at") else now
            return row
        return {"key": clean_key, "content": content.strip(), "created_at": now, "updated_at": now}

    def delete_memory(self, user, key):
        n = self._exec("DELETE FROM jarvis_memories WHERE user_ns=%s AND memory_key=%s",
                       (user.namespace, key.strip().lower()))
        return n > 0

    def clear_memories(self, user):
        n = self._exec("DELETE FROM jarvis_memories WHERE user_ns=%s", (user.namespace,))
        return n or 0

    # reminders
    def list_reminders(self, user, include_completed=False):
        sql = ("SELECT id, title, due_time, notes, completed, created_at, completed_at "
               "FROM jarvis_reminders WHERE user_ns=%s")
        params: list = [user.namespace]
        if not include_completed:
            sql += " AND completed = FALSE"
        sql += " ORDER BY created_at"
        rows = self._fetch(sql, tuple(params))
        out = []
        for r in rows:
            r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else _utcnow_iso()
            r["completed_at"] = r["completed_at"].isoformat() if r.get("completed_at") else None
            out.append(r)
        return out

    def add_reminder(self, user, title, due_time, notes):
        rid = f"rem_{secrets.token_hex(4)}"
        now = _utcnow_iso()
        self._exec(
            "INSERT INTO jarvis_users (user_ns, email, display_name) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_ns) DO NOTHING",
            (user.namespace, user.email, user.name),
        )
        self._exec(
            "INSERT INTO jarvis_reminders (id, user_ns, title, due_time, notes) VALUES (%s, %s, %s, %s, %s)",
            (rid, user.namespace, title.strip(), due_time.strip(), notes.strip() if notes else None),
        )
        return {"id": rid, "title": title.strip(), "due_time": due_time.strip(),
                "notes": notes.strip() if notes else None, "completed": False,
                "created_at": now, "completed_at": None}

    def complete_reminder(self, user, reminder_id):
        row = self._exec(
            "UPDATE jarvis_reminders SET completed=TRUE, completed_at=now() "
            "WHERE user_ns=%s AND id=%s RETURNING id, title, due_time, notes, completed, created_at, completed_at",
            (user.namespace, reminder_id), fetch_one=True,
        )
        if not row:
            return None
        row["created_at"] = row["created_at"].isoformat() if row.get("created_at") else _utcnow_iso()
        row["completed_at"] = row["completed_at"].isoformat() if row.get("completed_at") else None
        return row

    def delete_reminder(self, user, reminder_id):
        n = self._exec("DELETE FROM jarvis_reminders WHERE user_ns=%s AND id=%s",
                       (user.namespace, reminder_id))
        return n > 0

    def get_reminder(self, user, reminder_id):
        rows = self._fetch(
            "SELECT id, title, due_time, notes, completed, created_at, completed_at "
            "FROM jarvis_reminders WHERE user_ns=%s AND id=%s",
            (user.namespace, reminder_id),
        )
        if not rows:
            return None
        r = rows[0]
        r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else _utcnow_iso()
        r["completed_at"] = r["completed_at"].isoformat() if r.get("completed_at") else None
        return r

    # BYOK key
    def save_key(self, user, encrypted, hint):
        self._exec(
            "INSERT INTO jarvis_users (user_ns, email, display_name) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_ns) DO NOTHING",
            (user.namespace, user.email, user.name),
        )
        self._exec(
            "INSERT INTO jarvis_user_keys (user_ns, encrypted_key, key_hint) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_ns) DO UPDATE SET encrypted_key=EXCLUDED.encrypted_key, "
            "key_hint=EXCLUDED.key_hint, created_at=now()",
            (user.namespace, encrypted, hint),
        )

    def load_key(self, user):
        rows = self._fetch("SELECT encrypted_key FROM jarvis_user_keys WHERE user_ns=%s",
                           (user.namespace,))
        if not rows:
            return None
        val = rows[0]["encrypted_key"]
        return bytes(val) if val is not None else None

    def key_meta(self, user):
        rows = self._fetch("SELECT key_hint AS hint, created_at FROM jarvis_user_keys WHERE user_ns=%s",
                           (user.namespace,))
        if not rows:
            return None
        return {"hint": rows[0].get("hint"),
                "created_at": rows[0]["created_at"].isoformat() if rows[0].get("created_at") else None}

    def delete_key(self, user):
        n = self._exec("DELETE FROM jarvis_user_keys WHERE user_ns=%s", (user.namespace,))
        return n > 0

    # chat history
    def append_chat(self, user, role, content):
        self._exec(
            "INSERT INTO jarvis_users (user_ns, email, display_name) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_ns) DO NOTHING",
            (user.namespace, user.email, user.name),
        )
        self._exec("INSERT INTO jarvis_chat_history (user_ns, role, content) VALUES (%s, %s, %s)",
                   (user.namespace, role, content))

    def list_chat(self, user, limit=50):
        rows = self._fetch(
            "SELECT role, content, created_at FROM jarvis_chat_history "
            "WHERE user_ns=%s ORDER BY created_at DESC, id DESC LIMIT %s",
            (user.namespace, limit),
        )
        out = [{"role": r["role"], "content": r["content"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None}
               for r in reversed(rows)]
        return out

    # action log
    def append_action(self, user, entry):
        self._exec(
            "INSERT INTO jarvis_action_log (user_ns, tool_name, status, details, execution_time_ms) "
            "VALUES (%s, %s, %s, %s, %s)",
            (user.namespace, entry.get("tool_name", ""), entry.get("status", ""),
             (entry.get("details") or "")[:300], entry.get("execution_time_ms")),
        )

    def recent_actions(self, user, limit=50):
        rows = self._fetch(
            "SELECT created_at AS timestamp, tool_name, status, details, execution_time_ms "
            "FROM jarvis_action_log WHERE user_ns=%s ORDER BY created_at DESC, id DESC LIMIT %s",
            (user.namespace, limit),
        )
        out = []
        for r in rows:
            r["timestamp"] = r["timestamp"].isoformat() if r.get("timestamp") else _utcnow_iso()
            out.append(r)
        return list(reversed(out))

    # usage
    def record_usage(self, user, kind):
        self._exec("INSERT INTO jarvis_usage (user_ns, kind) VALUES (%s, %s)",
                   (user.namespace, kind))

    def count_usage_since(self, user, kind, since_ts):
        since = datetime.datetime.fromtimestamp(since_ts, tz=datetime.timezone.utc)
        rows = self._fetch(
            "SELECT COUNT(*) AS n FROM jarvis_usage WHERE user_ns=%s AND kind=%s AND created_at >= %s",
            (user.namespace, kind, since),
        )
        return int(rows[0]["n"]) if rows else 0

    def clear_all_user_data(self, user):
        counts: Dict[str, int] = {}
        for table, label in (("jarvis_notes", "notes"), ("jarvis_reminders", "reminders"),
                             ("jarvis_memories", "memories"), ("jarvis_chat_history", "chat")):
            n = self._exec(f"DELETE FROM {table} WHERE user_ns=%s", (user.namespace,))
            counts[label] = n or 0
        counts["screenshots"] = 0  # screenshots cannot exist in cloud mode
        return counts


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_store: Optional[UserStore] = None


def get_user_store() -> UserStore:
    """Return the active store: Postgres when DATABASE_URL is set, else files."""
    global _store
    if _store is not None:
        return _store
    dsn = (settings.DATABASE_URL or "").strip()
    if dsn:
        _store = PostgresUserStore(dsn)
    else:
        _store = FileUserStore()
    return _store


def reset_user_store() -> None:
    global _store
    _store = None


def uses_postgres() -> bool:
    return isinstance(get_user_store(), PostgresUserStore)
