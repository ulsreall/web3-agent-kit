"""GO-arrival metadata read from a Hermes session store.

The only timestamp that proves when an explicit, run-specific GO arrived is the real
delivery time of the GO message in the session store. An executor-internal placeholder
such as ``floor(Date.now()/1000) - 5`` measures nothing about arrival and must never be
labelled as arrival.

This module is read-only. Importing it performs no I/O; every function opens the
sqlite database in read-only URI mode and never writes.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA = "wak-p1.go-arrival-metadata.v1"
GO_MESSAGES_TABLE = "messages"
GO_SHEET_AUTHORIZATION_SCHEMA = "wak-p1.go-sheet-authorization.v1"

# Labels that may prefix the 64-hex run-sheet hash inside a GO message.
_SHEET_HASH_LABELS = (
    "run[ _-]?sheet[ _-]?sha-?256",
    "run[ _-]?sheet[ _-]?hash",
    "sheet[ _-]?hash",
    "runSheetsha256",
    "runSheetSha256",
    "run_sheet_sha256",
    "run-sheet-sha256",
    "runSheetHash",
)
_SHEET_HASH_LABEL_RE = re.compile(
    r"(?i)(?:%s)\s*[=:]?\s*([0-9a-fA-F]{64})" % "|".join(_SHEET_HASH_LABELS)
)
_GO_HASH_DIRECTIVE_RE = re.compile(r"(?i)\bGO[:\s]+([0-9a-fA-F]{64})\b")


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


def _extract_sheet_hash(content: str) -> tuple[str | None, str | None]:
    """Extract a 64-hex run-sheet hash the GO message names, plus its source form.

    Tries, in order: an embedded JSON object carrying a sheet-hash field; a labelled
    ``runSheetSha256 <hash>``-style token; a bare ``GO: <hash>`` / ``GO <hash>``
    directive. Returns ``(hash|None, source|None)``.
    """
    if not content:
        return None, None
    try:
        obj = json.loads(content)
    except (ValueError, TypeError):
        obj = None
    if isinstance(obj, dict):
        for key in (
            "runSheetSha256",
            "run_sheet_sha256",
            "runSheetHash",
            "sheetHash",
            "sheetSha256",
            "run-sheet-sha256",
        ):
            value = obj.get(key)
            if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value):
                return value.lower(), "json"
    label = _SHEET_HASH_LABEL_RE.search(content)
    if label:
        return label.group(1).lower(), "label"
    directive = _GO_HASH_DIRECTIVE_RE.search(content)
    if directive:
        return directive.group(1).lower(), "go-directive"
    return None, None


def authorize_go_message(
    content: str,
    required_run_sheet_sha256: str,
) -> dict[str, Any]:
    """Verify a GO message's own text authorizes the exact run-sheet hash.

    The executing path must confirm the Hermes GO *message itself* (not merely the GO
    file) names the exact sheet it is about to sign/broadcast. Raises
    :class:`GoArrivalError` when the message carries no run-sheet hash or names a
    different one.
    """
    required = str(required_run_sheet_sha256).lower()
    hash_, source = _extract_sheet_hash(content)
    if hash_ is None:
        raise GoArrivalError(
            "GO message does not explicitly authorize a run-sheet hash; "
            "executing runs require the exact runSheetSha256 in the GO message"
        )
    if hash_ != required:
        raise GoArrivalError(
            f"GO message authorizes run-sheet hash {hash_}, "
            f"but the executing path bound {required} -- aborting"
        )
    return {
        "schema": GO_SHEET_AUTHORIZATION_SCHEMA,
        "authorized": True,
        "authorizedRunSheetSha256": hash_,
        "authorizationSource": source,
        "presentInMessage": True,
    }


def fetch_go_message(db_path: str | Path, message_id: int) -> Mapping[str, Any]:
    """Return the full GO message row (id, role, content, timestamp) by id."""
    with _readonly_connection(db_path) as con:
        row = con.execute(
            "SELECT id, role, content, timestamp "
            f"FROM {GO_MESSAGES_TABLE} WHERE id = ?",
            (int(message_id),),
        ).fetchone()
    if row is None:
        raise GoArrivalError(f"no GO message with id {message_id} in the session store")
    return dict(row)


def authorize_go_sheet(
    db_path: str | Path,
    message_id: int,
    required_run_sheet_sha256: str,
) -> dict[str, Any]:
    """Fetch the GO message and require it authorizes the exact sheet hash.

    Returns the authorization payload joined with delivery provenance so the report
    can show both that the message arrived on time and that it named the exact sheet
    the runner is about to execute.
    """
    row = fetch_go_message(db_path, message_id)
    auth = authorize_go_message(str(row.get("content") or ""), required_run_sheet_sha256)
    return {
        **auth,
        "messageId": int(row["id"]),
        "deliveryTimestampEpoch": int(row["timestamp"]),
        "contentSource": "Hermes session store (messages table)",
    }
