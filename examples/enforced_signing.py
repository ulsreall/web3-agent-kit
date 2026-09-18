"""Offline demonstration of the enforced pre-sign authorization gate.

Runs with no network, no funded key and no real credentials. It shows the four
stages a transaction now passes through -- normalize, policy, optional
confirmation, principal authorization -- and how each one can stop a signature
before the raw signer is reached.

Run:
    python examples/enforced_signing.py
"""

from __future__ import annotations

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import (
    CALL_ENVELOPE_SCHEMA,
    POLICY_DECISION_SCHEMA,
    ActionType,
    AuthorizationDenied,
    AuthorizationEvidence,
    AuthorizationRequest,
    CallEnvelopeError,
    EnforcementDenied,
    ExecutionPolicy,
    PolicyDecisionCommitment,
    PreSignInterceptor,
)

ROUTER = "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4"
SENDER = "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"
THROWAWAY_KEY = "0x" + "11" * 32  # never funded; used only to derive an address


class _DemonstrationSigner:
    """Stands in for Account.sign_transaction. Never touches a real key."""

    def __init__(self) -> None:
        self.reached = 0

    def __call__(self, tx) -> bytes:
        self.reached += 1
        return b"\x01" * 64


class _DemoProvider:
    """A principal authorization verifier.

    ``approve`` controls whether it issues evidence or denies. The digest it
    returns is bound to the exact call under evaluation, which is what makes
    the evidence usable for this call and no other.
    """

    def __init__(self, *, approve: bool = True) -> None:
        self._approve = approve

    @property
    def policy_id(self) -> str:
        return "demo-provider"

    def authorize(self, context) -> AuthorizationEvidence:
        if not self._approve:
            raise AuthorizationDenied("principal did not authorize this call")
        return AuthorizationEvidence(
            authorization_id="demo-authorization",
            envelope_digest=context.envelope_digest,
            executor=context.envelope.executor,
            authorizer="0x" + "99" * 20,
            valid_from=0,
            valid_until=2**31,
            nonce="1",
            policy_commitment_digest=context.policy_commitment.digest(),
        )


def _policy(**overrides) -> ExecutionPolicy:
    kwargs: dict = {
        "allowed_chains": frozenset({Chain.BASE}),
        "allowed_actions": frozenset({ActionType.SWAP}),
        "allowed_contracts": frozenset({ROUTER}),
        "max_native_value_wei": 10**18,
        "require_confirmation": False,
    }
    kwargs.update(overrides)
    return ExecutionPolicy(**kwargs)


def _transaction(**overrides) -> dict:
    tx = {
        "to": ROUTER,
        "from": SENDER,
        "data": "0xdeadbeef",
        "value": 1_000_000_000_000,
        "nonce": 265,
        "chainId": 8453,
        "gas": 300_000,
        "gasPrice": 1_000_000_000,
    }
    tx.update(overrides)
    return tx


def _request(**overrides) -> AuthorizationRequest:
    return AuthorizationRequest(Chain.BASE, ActionType.SWAP, _transaction(**overrides))


def _rule(label: str) -> None:
    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")


def main() -> int:
    _rule("0. Canonical call identity")

    request = _request()
    envelope = request.envelope()
    print(f"schema        : {CALL_ENVELOPE_SCHEMA}")
    print(f"profile       : {envelope.execution_profile}")
    print(f"chainId       : {envelope.chain_id}")
    print(f"executor      : {envelope.executor}")
    print(f"nonce         : {envelope.nonce}")
    print(f"target        : {envelope.target}")
    print(f"calldataHash  : {envelope.calldata_hash}")
    print(f"nativeValue   : {envelope.native_value}")
    print(f"envelope      : {envelope.digest()}")

    _rule("1. DENIED - chain mismatch")

    signer = _DemonstrationSigner()
    gate = PreSignInterceptor(
        policy=_policy(), signer=signer, authorization_provider=_DemoProvider()
    )
    try:
        # Policy names Base (8453); this transaction says Base Sepolia (84532).
        gate.sign(_request(chainId=84532))
        print("UNEXPECTED: signed")
        return 1
    except (EnforcementDenied, CallEnvelopeError) as exc:
        print(f"denied        : {exc}")
        print(f"signer reached: {signer.reached}")

    _rule("2. DENIED - policy")

    signer = _DemonstrationSigner()
    gate = PreSignInterceptor(
        policy=_policy(allowed_contracts=frozenset({"0x" + "11" * 20})),
        signer=signer,
        authorization_provider=_DemoProvider(),
    )
    try:
        gate.sign(request)
        print("UNEXPECTED: signed")
        return 1
    except EnforcementDenied as exc:
        print(f"denied        : {exc}")
        print(f"signer reached: {signer.reached}")

    _rule("3. DENIED - policy allows, but no principal authorization")

    signer = _DemonstrationSigner()
    gate = PreSignInterceptor(policy=_policy(), signer=signer)
    try:
        gate.sign(request)
        print("UNEXPECTED: signed")
        return 1
    except EnforcementDenied as exc:
        print(f"denied        : {exc}")
        print(f"signer reached: {signer.reached}")
        print("              policy allow is not authority")

    _rule("4. DENIED - principal refuses")

    signer = _DemonstrationSigner()
    gate = PreSignInterceptor(
        policy=_policy(),
        signer=signer,
        authorization_provider=_DemoProvider(approve=False),
    )
    try:
        gate.sign(request)
        print("UNEXPECTED: signed")
        return 1
    except EnforcementDenied as exc:
        print(f"denied        : {exc}")
        print(f"signer reached: {signer.reached}")

    _rule("5. DENIED - authorization already consumed (single use)")

    signer = _DemonstrationSigner()
    gate = PreSignInterceptor(
        policy=_policy(), signer=signer, authorization_provider=_DemoProvider()
    )
    gate.sign(request)
    before = signer.reached
    try:
        gate.sign(request)
        print("UNEXPECTED: signed twice")
        return 1
    except EnforcementDenied as exc:
        print(f"denied        : {exc}")
        print(f"signer reached: {before} -> {signer.reached}")

    _rule("6. AUTHORIZED - policy allows and principal authorizes")

    signer = _DemonstrationSigner()
    gate = PreSignInterceptor(
        policy=_policy(), signer=signer, authorization_provider=_DemoProvider()
    )
    result = gate.sign(request)

    print(f"signature     : {len(result.raw_transaction)} bytes")
    print(f"call identity : {result.call_fingerprint}")
    print(f"policy digest : {result.policy_commitment.digest()}")
    print(f"authorization : {result.authorization.authorization_id}")
    print(f"authorizer    : {result.authorization.authorizer}")
    print(f"executor      : {result.authorization.executor}")

    _rule("7. Two domains, one binding")

    commitment = result.policy_commitment
    print("The call identity and the policy verdict are distinct commitments.")
    print("An external authorization layer binds to the identity; the policy")
    print("verdict travels separately so 'policy allowed' and 'the principal")
    print("authorized this exact call' stay independently verifiable.")
    print()
    print(f"call identity     : {result.call_fingerprint}")
    print(f"policy commitment : {commitment.as_context_commitment()}")
    print(f"domains differ    : {result.call_fingerprint != commitment.digest()}")

    _rule("8. Diagnostic log (process-local, not durable)")

    for entry in gate.audit_log:
        print(
            f"  #{entry.sequence} {entry.verdict.value:10} "
            f"durable={entry.durable} auth={entry.authorization_id}"
        )
    print()
    print("This log is append-only within one Python object. It is diagnostic")
    print("history, not tamper-evident audit evidence, and it says so.")

    _rule("done")
    print("Every DENIED case above stopped before the raw signer was reached.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
