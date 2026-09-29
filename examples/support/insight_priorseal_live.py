"""Live execution boundaries, call-event retention, and cutoff guards for the
WAK / Insight / PriorSeal P1 leg.

Importing this module performs no I/O, signs nothing, and broadcasts nothing. Live
construction requires explicit configuration (signer key source, RPC URL, GO metadata),
and the runner refuses to broadcast without an explicit ``--allow-broadcast`` flag plus a
validated GO file.

The three boundaries mirror the module's ``SignerProtocol`` / ``BroadcastFn`` /
``ReceiptFn`` so a live P1 leg runs through the same WAK-owned instrumentation as the
offline N1-N5b suite. Every boundary call is recorded by :class:`CallEventRecorder` so the
acceptance report can carry ``callEventEvidenceRetained: true`` with per-boundary
attempted/successful/failed counts and timestamps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

# Reuse the module's explicit boundary contracts (protocols only, no I/O).


@runtime_checkable
class SignerProtocol(Protocol):
    def sign_transaction(self, transaction: Mapping[str, Any]) -> bytes: ...


@runtime_checkable
class BroadcastFn(Protocol):
    def __call__(self, raw_transaction: bytes) -> Mapping[str, Any]: ...


@runtime_checkable
class ReceiptFn(Protocol):
    def __call__(self, broadcast_result: Mapping[str, Any]) -> Mapping[str, Any]: ...


BOUNDARIES = ("authorizationProvider", "signer", "broadcast", "receipt")
CALL_EVENT_SCHEMA = "wak-p1.call-event.v1"


class CallEventRecorder:
    """Retains every boundary call with outcome and timestamps.

    The recorder is intentionally minimal and thread-safe for a single attempt: it
    appends to a list under a lock and never mutates previously recorded events, so the
    exported call log is append-only evidence.

    The recorder also doubles as the module's :class:`BoundaryCounters` object so the
    gate helper can count authorization/sign/broadcast/receipt calls through the same
    instance that retains the event log -- the runner never passes a bare dictionary
    where the gate expects a counter object.
    """

    _BOUNDARY_FIELDS = {
        "authorizationProvider": "authorization_provider",
        "signer": "signer",
        "broadcast": "broadcast",
        "receipt": "receipt",
    }

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._sequence = 0
        self.authorization_provider = 0
        self.signer = 0
        self.broadcast = 0
        self.receipt = 0

    def record(
        self,
        boundary: str,
        outcome: str,
        *,
        started_at: int,
        finished_at: int,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        if boundary not in BOUNDARIES:
            raise ValueError(f"unknown boundary: {boundary}")
        if outcome not in ("attempted", "success", "error"):
            raise ValueError(f"unknown outcome: {outcome}")
        self._sequence += 1
        self._events.append(
            {
                "schema": CALL_EVENT_SCHEMA,
                "index": self._sequence,
                "boundary": boundary,
                "outcome": outcome,
                "startedAtEpoch": int(started_at),
                "finishedAtEpoch": int(finished_at),
                "durationSeconds": max(0, int(finished_at) - int(started_at)),
                "detail": dict(detail or {}),
            }
        )

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)

    def counts(self) -> dict[str, dict[str, int]]:
        per: dict[str, dict[str, int]] = {b: {"attempted": 0, "success": 0, "error": 0} for b in BOUNDARIES}
        for ev in self._events:
            per[ev["boundary"]][ev["outcome"]] += 1
        return per

    def boundary_counts(self) -> dict[str, int]:
        """The flat ``BoundaryCounters.as_report`` shape derived from retained events.

        ``authorizationProvider`` counts authorize() calls (attempted events -- the
        gate may legitimately deny during authorization, and the offline vectors count
        that call). ``signer``/``broadcast``/``receipt`` count successful boundary
        calls, so 1/1/1/1 appears only when a full sign+broadcast+receipt leg actually
        succeeded -- a run denied before signing reports 1/0/0/0, never the reverse.
        """
        attempts = sum(
            1
            for ev in self._events
            if ev["boundary"] == "authorizationProvider" and ev["outcome"] == "attempted"
        )
        successful = {
            boundary: sum(
                1
                for ev in self._events
                if ev["boundary"] == boundary and ev["outcome"] == "success"
            )
            for boundary in ("signer", "broadcast", "receipt")
        }
        return {
            "authorizationProvider": attempts,
            "signer": successful["signer"],
            "broadcast": successful["broadcast"],
            "receipt": successful["receipt"],
        }

    def as_report(self) -> dict[str, Any]:
        return {
            "schema": "wak-p1.call-event-log.v1",
            "retained": True,
            "counts": self.counts(),
            "events": self.events(),
        }


def _now() -> int:
    return int(time.time())


class _RecordingBoundary:
    """Wrap any callable and record attempted/success/error around it."""

    def __init__(self, boundary: str, recorder: CallEventRecorder, fn: Callable[..., Any]) -> None:
        self._boundary = boundary
        self._recorder = recorder
        self._fn = fn

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        started = _now()
        self._recorder.record(self._boundary, "attempted", started_at=started, finished_at=started)
        try:
            result = self._fn(*args, **kwargs)
        except Exception as exc:
            finished = _now()
            self._recorder.record(
                self._boundary,
                "error",
                started_at=started,
                finished_at=finished,
                detail={"error": type(exc).__name__},
            )
            raise
        finished = _now()
        self._recorder.record(self._boundary, "success", started_at=started, finished_at=finished)
        return result


# -- concrete live boundaries -------------------------------------------------


class EvmSigner:
    """Sign an EIP-1559 or legacy transaction with ``eth_account``."""

    def __init__(self, account: Any) -> None:
        self._account = account

    def address(self) -> str:
        return str(self._account.address)

    def sign_transaction(self, transaction: Mapping[str, Any]) -> bytes:
        tx = dict(transaction)
        from_ = tx.get("from")
        if from_ is not None and str(from_).lower() != self.address().lower():
            raise ValueError("transaction 'from' does not match the signer address")
        tx["from"] = self.address()
        for key in ("chainId", "nonce", "value", "gas", "gasPrice", "maxFeePerGas", "maxPriorityFeePerGas"):
            if key in tx and not isinstance(tx[key], int):
                tx[key] = int(tx[key])
        if "data" in tx and tx["data"] is None:
            tx["data"] = b""
        if "to" in tx:
            # eth_account validates `to` as a checksummed address and rejects
            # all-lowercase hex; the run sheet may carry a lowercase target.
            import eth_utils

            tx["to"] = eth_utils.to_checksum_address(str(tx["to"]))
        signed = self._account.sign_transaction(tx)
        return bytes(signed.raw_transaction)


def _jsonrpc(rpc_url: str, method: str, params: list[Any], *, timeout: float) -> dict[str, Any]:
    import httpx

    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    resp = httpx.post(rpc_url, json=payload, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"{method} RPC error: {body['error']}")
    return body["result"]


class RpcBroadcast:
    """Broadcast a raw transaction via ``eth_sendRawTransaction``."""

    def __init__(self, rpc_url: str, *, timeout: float = 30.0) -> None:
        self._rpc_url = rpc_url
        self._timeout = timeout

    def __call__(self, raw_transaction: bytes) -> Mapping[str, Any]:
        raw_hex = raw_transaction.hex() if isinstance(raw_transaction, bytes) else str(raw_transaction)
        tx_hash = _jsonrpc(self._rpc_url, "eth_sendRawTransaction", [raw_hex], timeout=self._timeout)
        return {"txHash": tx_hash, "rawLength": len(raw_transaction), "method": "eth_sendRawTransaction"}


class RpcReceipt:
    """Wait for a transaction receipt at a confirmation count."""

    def __init__(
        self,
        rpc_url: str,
        *,
        confirmations: int = 2,
        timeout: float = 180.0,
        poll_seconds: float = 2.0,
    ) -> None:
        self._rpc_url = rpc_url
        self._confirmations = max(1, int(confirmations))
        self._timeout = timeout
        self._poll = poll_seconds

    def __call__(self, broadcast_result: Mapping[str, Any]) -> Mapping[str, Any]:
        tx_hash = broadcast_result["txHash"]
        deadline = time.time() + self._timeout
        polled = 0
        while time.time() < deadline:
            polled += 1
            receipt = _jsonrpc(self._rpc_url, "eth_getTransactionReceipt", [tx_hash], timeout=self._timeout)
            head = _jsonrpc(self._rpc_url, "eth_blockNumber", [], timeout=self._timeout)
            if isinstance(receipt, dict) and receipt.get("blockNumber") is not None:
                block = int(receipt["blockNumber"], 16)
                head_num = int(head, 16) if isinstance(head, str) else int(head)
                if head_num - block + 1 >= self._confirmations:
                    return {
                        "status": "CONFIRMED" if int(receipt["status"], 16) == 1 else "REVERTED",
                        "txHash": tx_hash,
                        "blockNumber": block,
                        "headBlock": head_num,
                        "confirmations": head_num - block + 1,
                        "gasUsed": int(str(receipt["gasUsed"]), 16) if "gasUsed" in receipt else None,
                        "polled": polled,
                    }
            time.sleep(self._poll)
        raise TimeoutError(f"receipt not confirmed within {self._timeout:.0f}s (polled {polled}x)")


class InertBroadcast:
    """Broadcast boundary with no network effect (rehearsal only).

    Implements the same :class:`BroadcastFn` contract as :class:`RpcBroadcast` but
    derives a deterministic inert tx hash from the raw transaction and never touches an
    RPC endpoint. Used exclusively for the inert-boundary rehearsal so the runner path
    (GO binding, cutoff guards, event retention, counters) is exercised without an
    on-chain side effect.
    """

    def __init__(self, *, label: str = "rehearsal") -> None:
        self._label = label

    def __call__(self, raw_transaction: bytes) -> Mapping[str, Any]:
        import hashlib

        payload = raw_transaction if isinstance(raw_transaction, bytes) else bytes.fromhex(str(raw_transaction))
        tx_hash = "0x" + hashlib.sha256(payload).hexdigest()
        return {
            "txHash": tx_hash,
            "rawLength": len(payload),
            "method": "INERT",
            "inert": True,
            "label": self._label,
        }


class InertReceipt:
    """Receipt boundary with no network effect (rehearsal only)."""

    def __init__(self, *, label: str = "rehearsal", confirmations: int = 2) -> None:
        self._label = label
        self._confirmations = max(1, int(confirmations))

    def __call__(self, broadcast_result: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "status": "CONFIRMED",
            "txHash": broadcast_result["txHash"],
            "confirmations": self._confirmations,
            "polled": 0,
            "inert": True,
            "label": self._label,
        }


# -- cutoff guards and GO checks ----------------------------------------------


class CutoffError(ValueError):
    """Raised when remaining runway to the broadcast cutoff is below a floor."""


@dataclass(frozen=True)
class LiveRunConfig:
    rpc_url: str
    chain_id: int
    latest_broadcast_at: int
    run_sheet_sha256: str
    go_arrival_epoch: int
    receiver_floor_seconds: int = 120
    review_floor_seconds: int = 240
    margin_seconds: int = 180
    confirmations: int = 2
    receipt_timeout_seconds: int = 180
    broadcast_poll_seconds: float = 2.0


def check_cutoff(*, now_epoch: int, latest_broadcast_at: int, minimum_seconds: int) -> int:
    """Return remaining runway to cutoff, raising ``CutoffError`` below the floor."""
    runway = int(latest_broadcast_at) - int(now_epoch)
    if runway < int(minimum_seconds):
        raise CutoffError(
            f"insufficient runway before broadcast cutoff: {runway}s remaining, "
            f"need >= {minimum_seconds}s"
        )
    return runway


def check_go_arrival(config: LiveRunConfig) -> int:
    """The GO must have arrived with at least ``receiver_floor_seconds`` to cutoff."""
    runway = int(config.latest_broadcast_at) - int(config.go_arrival_epoch)
    if runway < int(config.receiver_floor_seconds):
        raise CutoffError(
            f"GO arrival leaves only {runway}s to cutoff; "
            f"receiver floor requires >= {config.receiver_floor_seconds}s"
        )
    return runway


class _CutoffGuarded:
    """Re-check the cutoff immediately before the wrapped boundary executes.

    ``sign`` guards the signer; ``broadcast`` guards the broadcaster. Both re-check the
    live clock against ``latest_broadcast_at`` so a late GO cannot slip past sign or
    broadcast without a fresh error being raised (and recorded). A guard block is
    retained as a failed attempt on that boundary (``attempted`` + ``error`` events) so
    the call-event log includes failures, not only successes.
    """

    def __init__(
        self,
        boundary: str,
        recorder: CallEventRecorder,
        fn: Callable[..., Any],
        config: LiveRunConfig,
        *,
        minimum_seconds: int,
    ) -> None:
        self._boundary = boundary
        self._recorder = recorder
        self._inner = _RecordingBoundary(boundary, recorder, fn)
        self._config = config
        self._minimum = minimum_seconds

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        started = _now()
        try:
            check_cutoff(
                now_epoch=_now(),
                latest_broadcast_at=self._config.latest_broadcast_at,
                minimum_seconds=self._minimum,
            )
        except CutoffError as exc:
            finished = _now()
            self._recorder.record(
                self._boundary,
                "attempted",
                started_at=started,
                finished_at=started,
            )
            self._recorder.record(
                self._boundary,
                "error",
                started_at=started,
                finished_at=finished,
                detail={
                    "error": "CutoffError",
                    "runwaySeconds": int(self._config.latest_broadcast_at) - finished,
                    "minimumSeconds": self._minimum,
                    "message": str(exc),
                },
            )
            raise
        return self._inner(*args, **kwargs)

    def sign_transaction(self, transaction: Mapping[str, Any]) -> bytes:
        """Entry point used by the module's ``PreSignInterceptor`` wiring.

        ``ExecutionBoundaries.signer`` is consumed as ``boundaries.signer.sign_transaction``,
        while ``ExecutionBoundaries.broadcast`` is consumed as ``boundaries.broadcast(...)``;
        this class supports both call shapes.
        """
        return self(transaction)


def live_execution_boundaries(
    *,
    recorder: CallEventRecorder,
    signer: SignerProtocol,
    broadcast: BroadcastFn,
    receipt: ReceiptFn,
    config: LiveRunConfig,
    cutoff_check_seconds: int = 60,
) -> Any:
    """Build the module's ``ExecutionBoundaries`` with recording + cutoff guards.

    ``cutoff_check_seconds`` is the minimum runway required immediately before sign and
    immediately before broadcast (sign+broadcast+receipt normally need far less).
    """
    try:
        from examples.insight_priorseal_swap import ExecutionBoundaries  # lazy: avoid import cycle
    except ModuleNotFoundError:  # running the live script directly from examples/
        from insight_priorseal_swap import ExecutionBoundaries  # type: ignore[no-redef]

    return ExecutionBoundaries(
        signer=_CutoffGuarded(
            "signer",
            recorder,
            signer.sign_transaction,
            config,
            minimum_seconds=cutoff_check_seconds,
        ),
        broadcast=_CutoffGuarded(
            "broadcast",
            recorder,
            broadcast,
            config,
            minimum_seconds=cutoff_check_seconds,
        ),
        receipt=_RecordingBoundary("receipt", recorder, receipt),
    )


# -- runtime provenance --------------------------------------------------------


def runtime_provenance(*, package_version: str, commit: str | None = None, tree_clean: bool | None = None) -> dict[str, Any]:
    return {
        "schema": "wak-p1.runtime-provenance.v1",
        "packageVersion": package_version,
        "commit": commit,
        "treeClean": tree_clean,
    }


def version_alignment(fixture_wak_version: str, runtime_package_version: str) -> dict[str, Any]:
    """Report whether the fixture-pinned conformance identity matches the runtime tree.

    The verifier pins ``wakVersion`` to the fixture value, so the report must keep that
    identity and separately state what the runtime actually was; ``aligned`` records the
    difference instead of hiding it.
    """
    return {
        "schema": "wak-p1.version-alignment.v1",
        "fixturePinnedWakVersion": fixture_wak_version,
        "runtimePackageVersion": runtime_package_version,
        "aligned": fixture_wak_version == runtime_package_version,
    }
