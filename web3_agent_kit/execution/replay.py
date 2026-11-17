"""Replay state for consumed authorizations.

A gate must refuse an authorization it has already used. Keeping that state in
a ``set`` on the interceptor is enough for one process and useless across
restarts or workers: the same signed authorization replays after a redeploy.

Two backends ship here:

``InMemoryReplayStore``
    Bounded, process-local, prunes expired keys. The default.

``SqliteReplayStore``
    Durable and safe across processes. Selected with ``WEB3_REPLAY_DB``.

Both fail closed: if the store raises, the caller denies instead of assuming the
authorization is fresh. ``consume`` is atomic per key, so two workers racing the
same authorization cannot both win.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Protocol, runtime_checkable

DEFAULT_MAX_ENTRIES = 10_000


@runtime_checkable
class ReplayStore(Protocol):
    """Minimal single-use bookkeeping contract."""

    def consume(self, key: str, expires_at: int) -> bool:
        """Record ``key`` and return True the first time, False afterwards."""
        ...

    def prune(self, now: int | None = None) -> int:
        """Drop expired keys and return how many were removed."""
        ...

    def __len__(self) -> int: ...


class InMemoryReplayStore:
    """Process-local store with expiry pruning and a hard size bound."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES) -> None:
        self._entries: dict[str, int] = {}
        self._lock = threading.RLock()
        self._max_entries = max_entries

    def consume(self, key: str, expires_at: int) -> bool:
        now = int(time.time())
        with self._lock:
            self.prune(now)
            if key in self._entries:
                return False
            if len(self._entries) >= self._max_entries:
                # Drop the soonest-to-expire key so the store stays bounded.
                oldest = min(self._entries, key=self._entries.__getitem__)
                self._entries.pop(oldest, None)
            self._entries[key] = expires_at
            return True

    def prune(self, now: int | None = None) -> int:
        now = int(time.time()) if now is None else now
        with self._lock:
            stale = [key for key, expiry in self._entries.items() if expiry <= now]
            for key in stale:
                self._entries.pop(key, None)
        return len(stale)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


class SqliteReplayStore:
    """Durable store backed by SQLite.

    ``INSERT OR IGNORE`` plus ``rowcount`` makes the check-and-set atomic, so
    two processes cannot both consume the same authorization.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS consumed ("
                "key TEXT PRIMARY KEY, expires_at INTEGER NOT NULL)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS consumed_expiry ON consumed (expires_at)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def consume(self, key: str, expires_at: int) -> bool:
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM consumed WHERE expires_at <= ?", (now,))
            cursor = conn.execute(
                "INSERT OR IGNORE INTO consumed (key, expires_at) VALUES (?, ?)",
                (key, expires_at),
            )
            return cursor.rowcount == 1

    def prune(self, now: int | None = None) -> int:
        now = int(time.time()) if now is None else now
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM consumed WHERE expires_at <= ?", (now,))
            return cursor.rowcount

    def __len__(self) -> int:
        with self._lock, self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM consumed").fetchone()[0])


_default_store: ReplayStore | None = None
_default_lock = threading.Lock()


def default_store() -> ReplayStore:
    """Return the process-wide store, honouring ``WEB3_REPLAY_DB``.

    Without the variable the store is in-memory and shared by every gate in the
    process, so two gates cannot each consume the same authorization.
    """
    global _default_store
    with _default_lock:
        if _default_store is None:
            path = os.environ.get("WEB3_REPLAY_DB", "").strip()
            _default_store = SqliteReplayStore(path) if path else InMemoryReplayStore()
        return _default_store


def reset_default_store() -> None:
    """Drop the cached store (tests, or after changing ``WEB3_REPLAY_DB``)."""
    global _default_store
    with _default_lock:
        _default_store = None
