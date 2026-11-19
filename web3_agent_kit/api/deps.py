"""Shared construction helpers for write-capable API routes.

The API used to build a bare ``Wallet`` per request and hand the route's
``chain`` string straight to a class that wanted a ``ChainManager``. Both are
fixed here so every write route goes through the same, single path:

    chain name -> Chain -> ChainManager -> Wallet (gate bound) -> call

Gate configuration is explicit and fail-closed. Nothing signs unless
``WEB3_AUTO_AUTHORIZE`` is set, because a policy allow is not authority.

Environment
-----------
``WEB3_ALLOWED_CHAINS``     comma-separated chain names; unset = the requested
                            chain only.
``WEB3_ALLOWED_CONTRACTS``  comma-separated addresses; unset = only the target
                            the route already knows (see ``build_gate``).
``WEB3_MAX_NATIVE_WEI``     per-transaction native value cap, default 0.05 ETH.
``WEB3_REPLAY_DB``          file path for durable, cross-process replay state;
                            unset = process-wide in-memory store.
``WEB3_AUTO_AUTHORIZE``     ``true`` attaches an in-process authorization
                            provider. Without it every write fails closed with
                            an explicit message.
"""

from __future__ import annotations

import os
import re
import time
import uuid

from ..chains import Chain, ChainManager
from ..execution import (
    ActionType,
    AuthorizationEvidence,
    ExecutionPolicy,
    PreSignInterceptor,
)
from ..wallet.wallet import Wallet

DEFAULT_MAX_NATIVE_WEI = 5 * 10**16
AUTHORIZATION_TTL_SECONDS = 300


_ADDRESS_RE = re.compile(r"^0[xX][0-9a-fA-F]{40}$")


def _csv(name: str) -> list[str]:
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


def resolve_chain(name: str) -> Chain:
    """Return the :class:`Chain` for an API-supplied chain name."""
    try:
        chain = Chain(str(name).lower())
    except ValueError as exc:
        raise ValueError(f"unsupported chain: {name}") from exc

    allowed = _csv("WEB3_ALLOWED_CHAINS")
    if allowed and chain.value not in {item.lower() for item in allowed}:
        raise ValueError(f"chain {chain.value} is not in WEB3_ALLOWED_CHAINS")
    return chain


def chain_manager(chain: Chain) -> ChainManager:
    """Return a manager scoped to a single chain."""
    return ChainManager([chain])


def resolve_token(chain: Chain, token: str) -> str:
    """Return an address for a symbol, or pass ``ETH``/``NATIVE``/address through."""
    from ..portfolio.tracker import KNOWN_TOKENS

    text = str(token).strip()
    if text.upper() in {"ETH", "NATIVE"}:
        return text.upper()
    if _ADDRESS_RE.match(text):
        return text
    # An address-shaped string that is not hex used to pass this check and only
    # fail deep inside web3, after the request had been accepted.
    if text[:2].lower() == "0x":
        raise ValueError(f"token {token!r} starts with 0x but is not a 20-byte hex address")

    address = KNOWN_TOKENS.get(chain, {}).get(text.upper())
    if address is None:
        raise ValueError(
            f"unknown token {token!r} on {chain.value}; pass a 0x address or one of "
            f"{sorted(KNOWN_TOKENS.get(chain, {}))}"
        )
    return address


class AutoAuthorizationProvider:
    """In-process authorization provider for ``WEB3_AUTO_AUTHORIZE=true``.

    It authorizes the exact envelope it is handed, so it proves nothing about a
    principal — it only keeps the gate's structural checks (digest, executor,
    freshness, single use) in the path. Use a real verifier when the deployment
    has one.
    """

    @property
    def policy_id(self) -> str:
        return "api-auto-authorization"

    def authorize(self, context) -> AuthorizationEvidence:
        now = int(time.time())
        return AuthorizationEvidence(
            authorization_id=f"auto-{uuid.uuid4()}",
            envelope_digest=context.envelope_digest,
            executor=context.envelope.executor,
            authorizer=context.envelope.executor,
            valid_from=now,
            valid_until=now + AUTHORIZATION_TTL_SECONDS,
            nonce=str(uuid.uuid4()),
            policy_commitment_digest=context.policy_commitment.digest(),
        )


def _allowed_contracts(targets: set[str] | None) -> frozenset[str]:
    configured = _csv("WEB3_ALLOWED_CONTRACTS")
    if configured:
        return frozenset(configured)
    return frozenset(targets or ())


def build_gate(chain: Chain, signer, targets: set[str] | None = None) -> PreSignInterceptor | None:
    """Return a gate for ``chain``, or ``None`` when authorization is unconfigured.

    ``targets`` is the contract the route is about to call. It seeds the
    allowlist when ``WEB3_ALLOWED_CONTRACTS`` is unset, so a route that knows its
    router still works out of the box while an operator-supplied allowlist always
    wins.
    """
    if os.environ.get("WEB3_AUTO_AUTHORIZE", "false").lower() not in {"1", "true", "yes"}:
        return None

    try:
        max_native = int(os.environ.get("WEB3_MAX_NATIVE_WEI", DEFAULT_MAX_NATIVE_WEI))
    except ValueError as exc:
        raise ValueError("WEB3_MAX_NATIVE_WEI must be an integer in wei") from exc

    policy = ExecutionPolicy(
        allowed_chains=frozenset({chain}),
        allowed_actions=frozenset(ActionType),
        allowed_contracts=_allowed_contracts(targets),
        max_native_value_wei=max_native,
        require_confirmation=False,
    )
    return PreSignInterceptor(
        policy=policy,
        signer=signer,
        authorization_provider=AutoAuthorizationProvider(),
    )


def build_wallet(chain: Chain, targets: set[str] | None = None) -> Wallet:
    """Return a wallet bound to a gate for ``chain``."""
    wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=chain_manager(chain))
    gate = build_gate(chain, wallet.raw_signer, targets)
    if gate is not None:
        wallet.bind_enforcement(gate)
    return wallet
