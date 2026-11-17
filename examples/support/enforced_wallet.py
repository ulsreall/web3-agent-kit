"""Bind a wallet to an enforced pre-sign gate for the examples.

Every write example needs this: `Wallet.sign_transaction()` fails closed when no
gate is bound, so a bare wallet raises `EnforcementDenied` on its first write.

The policy here is deliberately narrow — the listed chains, any action, and a
small native-value cap — and the authorization provider is the in-process one.
That keeps the examples runnable without a principal, while still exercising the
gate. Swap `AutoAuthorizationProvider` for a real verifier in production.
"""

from __future__ import annotations

import time
import uuid

from web3_agent_kit import Chain, Wallet
from web3_agent_kit.execution import (
    ActionType,
    AuthorizationEvidence,
    ExecutionPolicy,
    PreSignInterceptor,
)

MAX_NATIVE_WEI = 5 * 10**16


class AutoAuthorizationProvider:
    """Authorizes the exact envelope it is handed. Proves nothing about a principal."""

    @property
    def policy_id(self) -> str:
        return "example-auto-authorization"

    def authorize(self, context) -> AuthorizationEvidence:
        now = int(time.time())
        return AuthorizationEvidence(
            authorization_id=f"example-{uuid.uuid4()}",
            envelope_digest=context.envelope_digest,
            executor=context.envelope.executor,
            authorizer=context.envelope.executor,
            valid_from=now,
            valid_until=now + 300,
            nonce=str(uuid.uuid4()),
            policy_commitment_digest=context.policy_commitment.digest(),
        )


def enforce(wallet: Wallet, chains: list[Chain]) -> Wallet:
    """Return ``wallet`` with a gate bound for ``chains``."""
    gate = PreSignInterceptor(
        policy=ExecutionPolicy(
            allowed_chains=frozenset(chains),
            allowed_actions=frozenset(ActionType),
            max_native_value_wei=MAX_NATIVE_WEI,
            require_confirmation=False,
        ),
        signer=wallet.raw_signer,
        authorization_provider=AutoAuthorizationProvider(),
    )
    return wallet.bind_enforcement(gate)
