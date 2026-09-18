"""Enforced pre-sign authorization — a runnable demonstration.

This script needs no network access and no funded key. It shows the gate
refusing to sign an unauthorized call, then authorizing a permitted one.

Run:
    python examples/enforced_signing.py
"""

from __future__ import annotations

from web3_agent_kit import Chain
from web3_agent_kit.execution import (
    ActionType,
    EnforcementDenied,
    ExecutionPolicy,
    PreSignInterceptor,
)
from web3_agent_kit.wallet.wallet import Wallet, WalletConfig

# An unfunded, throwaway key. Never send funds to this address.
DEMO_KEY = "0x" + "22" * 32

UNISWAP_ROUTER_BASE = "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4"
UNKNOWN_CONTRACT = "0x" + "dE" * 20


def build_policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        allowed_chains=frozenset({Chain.BASE}),
        allowed_actions=frozenset({ActionType.SWAP}),
        allowed_contracts=frozenset({UNISWAP_ROUTER_BASE}),
        max_native_value_wei=10**18,
        require_confirmation=False,
    )


def make_tx(to: str, value: int = 0) -> dict:
    return {
        "to": to,
        "data": "0xdeadbeef",
        "value": value,
        "nonce": 1,
        "chainId": 8453,
        "gas": 300_000,
        "gasPrice": 1_000_000_000,
    }


def main() -> int:
    wallet = Wallet(WalletConfig(private_key=DEMO_KEY))
    gate = PreSignInterceptor(policy=build_policy(), signer=wallet._raw_signer)
    wallet.bind_enforcement(gate)

    print("1. Attempting a swap against an unknown contract")
    try:
        wallet.sign_transaction(
            make_tx(UNKNOWN_CONTRACT), Chain.BASE, action=ActionType.SWAP
        )
    except EnforcementDenied as exc:
        print(f"   DENIED — {exc}")

    print()
    print("2. Attempting a swap above the native value ceiling")
    try:
        wallet.sign_transaction(
            make_tx(UNISWAP_ROUTER_BASE, value=10**19),
            Chain.BASE,
            action=ActionType.SWAP,
        )
    except EnforcementDenied as exc:
        print(f"   DENIED — {exc}")

    print()
    print("3. Attempting a call to the allowlisted router")
    raw = wallet.sign_transaction(
        make_tx(UNISWAP_ROUTER_BASE), Chain.BASE, action=ActionType.SWAP
    )
    print(f"   AUTHORIZED — {len(raw)} signed bytes produced")

    print()
    print("Audit log")
    for entry in gate.audit_log:
        state = entry.verdict.value
        reason = ", ".join(entry.reasons) if entry.reasons else "-"
        print(f"   #{entry.sequence} {state:<12} {entry.action:<12} {reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
