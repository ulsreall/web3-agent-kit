"""PoC — gate findings, runnable offline.

    python3 poc_gate.py

Each case prints OK when the branch behaves correctly and GAP when it does not.
Each case is a finding that was fixed; all should print OK.
"""

import os
import tempfile
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
from web3_agent_kit.execution.replay import reset_default_store

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
            # Tied to the envelope, as an issuing service would be: re-submitting
            # the same authorization must reproduce the same identifier.
            authorization_id=f"auth-{ctx.envelope_digest[:16]}",
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
shared = req(tx(nonce=7))
first = gate()
first.sign(shared)
print("   gate 1 signed, authorization:", first.audit_log[-1].authorization_id)
try:
    gate().sign(shared)
    print("   GAP gate 2 accepted the same authorization again")
except Exception as exc:
    print("   OK  gate 2 denied:", str(exc)[:60])

print("\nC2. after a restart, with WEB3_REPLAY_DB set")
db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
os.environ["WEB3_REPLAY_DB"] = db
reset_default_store()  # the store is cached per process; re-select after the env change
try:
    durable = req(tx(nonce=8))
    gate().sign(durable)
    reset_default_store()  # what a process restart does to the cached store
    try:
        gate().sign(durable)
        print("   GAP the durable store forgot a consumed authorization")
    except Exception as exc:
        print("   OK  still denied after the reset:", str(exc)[:55])
finally:
    os.environ.pop("WEB3_REPLAY_DB")
    reset_default_store()

print("\nD. bogus policy commitment in the evidence")
try:
    gate(commitment_override="0xdeadbeef").sign(req(tx(nonce=9)))
    print("   GAP accepted a commitment the policy never produced")
except EnforcementDenied as exc:
    print("   OK  denied:", str(exc)[:90])
