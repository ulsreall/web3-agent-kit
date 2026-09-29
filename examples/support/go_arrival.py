"""GO-arrival metadata read from a Hermes session store.

The only timestamp that proves when an explicit, run-specific GO arrived is the real
delivery time of the GO message in the session store. An executor-internal placeholder
such as ``floor(Date.now()/1000) - 5`` measures nothing about arrival and must never be
labelled as arrival.

This module is read-only. Importing it performs no I/O; every function opens the
sqlite database in read-only URI mode and never writes.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "wak-p1.go-arrival-metadata.v1"
GO_MESSAGES_TABLE = "messages"


class GoArrivalError(ValueError):
    """Raised when the session store cannot prove a GO delivery time."""


def _readonly_connection(db_path: str | Path) -> sqlite3.Connection:
    resolved = Path(db_path).resolve()
    if not resolved.exists():
        raise GoArrivalError(f"session store does not exist: {resolved}")
    uri = f"file:{resolved}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:  # pragma: no cover - sqlite driver specific
        raise GoArrivalError(f"cannot open session store read-only: {exc}") from exc
    con.row_factory = sqlite3.Row
    return con


def query_go_messages(
    db_path: str | Path,
    *,
    message_id: int | None = None,
    role: str | None = None,
    since_epoch: int | None = None,
    content_hint: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return candidate GO messages from the session store, oldest first.

    Args:
        db_path: path to the Hermes state database (``state.db``).
        message_id: exact message id to fetch.
        role: filter by message role (``user``/``assistant``/...).
        since_epoch: only messages delivered at or after this Unix epoch (seconds).
        content_hint: substring the GO text is expected to contain.
        limit: maximum rows returned.
    """
    if message_id is None and role is None and since_epoch is None and content_hint is None:
        raise GoArrivalError("at least one filter is required")
    clauses: list[str] = []
    params: list[Any] = []
    if message_id is not None:
        clauses.append("id = ?")
        params.append(int(message_id))
    if role is not None:
        clauses.append("role = ?")
        params.append(str(role))
    if since_epoch is not None:
        clauses.append("timestamp >= ?")
        params.append(int(since_epoch))
    if content_hint is not None:
        clauses.append("CAST(substr(content, 1, 2000) AS TEXT) LIKE ? ESCAPE '\\'")
        params.append(f"%{content_hint}%")
    sql = (
        "SELECT id, role, substr(content, 1, 120) AS content_head, timestamp "
        f"FROM {GO_MESSAGES_TABLE} WHERE " + " AND ".join(clauses)
    )
    sql += " ORDER BY timestamp ASC, id ASC LIMIT ?"
    params.append(int(limit))
    with _readonly_connection(db_path) as con:
        rows = con.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _epoch_to_iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_go_arrival(
    rows: Sequence[Mapping[str, Any]],
    *,
    prefer: str = "latest",
    stated_arrival_deadline_epoch: int | None = None,
    receiver_floor_seconds: int = 120,
) -> Mapping[str, Any]:
    """Build the v1 GO-arrival metadata payload from queried rows.

    ``prefer="latest"`` picks the most recently delivered candidate (the GO message is
    normally the newest matching user message); ``prefer="earliest"`` picks the oldest.
    ``stated_arrival_deadline_epoch`` is the GO message's own stated arrival deadline
    (``offChainValidity`` semantics) if the GO text carries one.
    """
    if not rows:
        raise GoArrivalError("no GO message matched the filters")
    chosen = rows[-1] if prefer == "latest" else rows[0]
    delivery = int(chosen["timestamp"])
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "source": "Hermes session store (messages table)",
        "messageId": int(chosen["id"]),
        "messageRole": chosen.get("role"),
        "deliveryTimestampEpoch": delivery,
        "deliveryTimestampIso": _epoch_to_iso(delivery),
        "receiverFloorSeconds": int(receiver_floor_seconds),
        "candidatesMatched": len(rows),
    }
    if stated_arrival_deadline_epoch is not None:
        deadline = int(stated_arrival_deadline_epoch)
        payload["statedArrivalDeadlineEpoch"] = deadline
        payload["statedArrivalDeadlineIso"] = _epoch_to_iso(deadline)
        payload["secondsBeforeStatedArrivalDeadline"] = deadline - delivery
    return payload


def floor_satisfied(payload: Mapping[str, Any], latest_broadcast_at: int) -> bool:
    """True when real arrival leaves at least ``receiverFloorSeconds`` to cutoff."""
    runway = int(latest_broadcast_at) - int(payload["deliveryTimestampEpoch"])
    return runway >= int(payload["receiverFloorSeconds"])
