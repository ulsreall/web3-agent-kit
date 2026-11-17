"""PoC — gate findings, runnable offline.

    python3 poc_gate.py

Each case prints OK when the branch behaves correctly and GAP when it does not.
C is the known remaining gap: replay protection is per-process.
"""

import time

from eth_account import Account

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import (
    ActionType,
    AuthorizationEvidence,
    AuthorizationRequest,
    CallableAuthorizationProvider,
    EnforcementDenied,
    ExecutionPolicy,
    PreSignInterceptor,
)

acct = Account.create()
SENDER = acct.address
TARGET = "0x" + "11" * 20

policy = ExecutionPolicy(
    allowed_chains=frozenset({Chain.BASE}),
    allowed_actions=frozenset(ActionType),
    allowed_contracts=frozenset({TARGET}),
    max_native_value_wei=10**18,
    require_confirmation=False,
)


def provider(commitment_override=None):
    def verify(ctx):
        now = int(time.time())
        return AuthorizationEvidence(
            authorization_id=f"auth-{now}-{id(ctx)}",
            envelope_digest=ctx.envelope_digest,
            executor=ctx.envelope.executor,
            authorizer=SENDER,
            valid_from=now - 5,
            valid_until=now + 300,
            nonce=str(now),
            policy_commitment_digest=commitment_override or ctx.policy_commitment.digest(),
        )

    return CallableAuthorizationProvider(verify)


def gate(commitment_override=None):
    return PreSignInterceptor(
        policy=policy,
        signer=lambda tx: Account.sign_transaction(tx, acct.key).raw_transaction,
        authorization_provider=provider(commitment_override),
    )


def tx(**over):
    base = {
        "from": SENDER,
        "to": TARGET,
        "nonce": 1,
        "chainId": 8453,
        "value": 0,
        "data": "0x" + "aa" * 4,
        "gas": 100000,
        "maxFeePerGas": 10**9,
        "maxPriorityFeePerGas": 10**9,
    }
    base.update(over)
    return base


def req(transaction, action=ActionType.CONTRACT_CALL):
    return AuthorizationRequest(chain=Chain.BASE, action=action, transaction=transaction)


print("A. contract creation (to=None)")
try:
    result = gate().sign(req(tx(to=None, nonce=0, data="0x6080604052")))
    profile = req(tx(to=None, data="0x6080")).envelope_v2().execution_profile
    print(f"   OK  signed, profile={profile}, raw bytes={len(result.raw_transaction)}")
except Exception as exc:
    print(f"   GAP {type(exc).__name__}: {exc}")

print("\nB. calldata carried as `input` (no `data` key)")
input_only = tx()
input_only.pop("data")
input_only["input"] = "0x" + "bb" * 4
try:
    gate().sign(req(input_only))
    print("   OK  signed, calldataHash =", req(input_only).envelope_v2().calldata_hash[:18], "…")
except Exception as exc:
    print(f"   GAP {type(exc).__name__}: {exc}")

print("\nC. replay against a fresh gate instance")
shared = tx(nonce=7)
first = gate()
first.sign(req(shared))
print("   gate 1 signed, authorization:", first.audit_log[-1].authorization_id)
try:
    gate().sign(req(shared))
    print("   GAP gate 2 accepted the same authorization (process-local replay set)")
except Exception as exc:
    print("   OK  gate 2 denied:", str(exc)[:70])

print("\nD. bogus policy commitment in the evidence")
try:
    gate(commitment_override="0xdeadbeef").sign(req(tx(nonce=9)))
    print("   GAP accepted a commitment the policy never produced")
except EnforcementDenied as exc:
    print("   OK  denied:", str(exc)[:90])
