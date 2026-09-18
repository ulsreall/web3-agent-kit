"""Regression tests for the P0 hardening round.

Every test in this file fails on the pre-hardening implementation. They were
written against three findings from an independent review, each reproduced
before the fix:

1. **Chain mismatch.** The policy named one chain while the transaction carried
   another chain's ``chainId``, and the gate signed anyway. The policy was
   evaluated against Base (8453) and the signature committed to Base Sepolia
   (84532).
2. **Unbound contract creation.** A wallet with no bound gate refused ordinary
   calls but signed contract creation (``to=None``), because the refusal was
   keyed on a non-null destination. Contract creation spends the nonce and runs
   arbitrary init code.
3. **Policy allow as authority.** With no authorization provider, an allowed
   policy produced a signature. Policy allow and principal authorization are
   different claims, and only the first was being checked.

Plus the P1 items: aliased signer calls escaping the static check, envelope
field normalization, and the removal of the unattended-confirmation bypass.

Each test names the gap it pins so a future refactor that reopens one is
obvious from the failure, not just from the diff.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from web3_agent_kit.chains import Chain
from web3_agent_kit.execution import (
    ActionType,
    AuthorizationDenied,
    AuthorizationEvidence,
    AuthorizationRequest,
    AuthorizationVerdict,
    CallEnvelopeV1,
    EnforcementDenied,
    ExecutionPolicy,
    NullAuthorizationProvider,
    PolicyDecisionCommitment,
    PreSignInterceptor,
)

ROUTER = "0x94cc0aac535ccdb3c01d6787d6413c739ae12bc4"
SENDER = "0x9965507d1a55bcc2695c58ba16fb37d819b0a4dc"
CALLDATA = bytes.fromhex("deadbeef")


def _tx(**overrides) -> dict:
    tx = {
        "to": ROUTER,
        "from": SENDER,
        "data": CALLDATA,
        "value": 0,
        "nonce": 265,
        "chainId": 8453,
        "gas": 300_000,
        "gasPrice": 10**9,
    }
    tx.update(overrides)
    return tx


def _policy(**overrides) -> ExecutionPolicy:
    kwargs: dict = {
        "allowed_chains": frozenset({Chain.BASE}),
        "allowed_actions": frozenset({ActionType.SWAP, ActionType.CONTRACT_CALL}),
        "allowed_contracts": frozenset({ROUTER}),
        "max_native_value_wei": 10**18,
        "require_confirmation": False,
    }
    kwargs.update(overrides)
    return ExecutionPolicy(**kwargs)


class _Signer:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, tx) -> bytes:
        self.calls.append(dict(tx))
        return b"\x01" * 64


class _Provider:
    """Verifier that authorizes exactly the call it is handed."""

    def __init__(self, *, valid_from: int = 0, valid_until: int = 2**31) -> None:
        self._valid_from = valid_from
        self._valid_until = valid_until

    @property
    def policy_id(self) -> str:
        return "p0-test-provider"

    def authorize(self, context) -> AuthorizationEvidence:
        return AuthorizationEvidence(
            authorization_id="p0-auth",
            envelope_digest=context.envelope_digest,
            executor=context.envelope.executor,
            authorizer="0x" + "99" * 20,
            valid_from=self._valid_from,
            valid_until=self._valid_until,
            nonce="1",
            policy_commitment_digest=context.policy_commitment.digest(),
        )


def _gate(signer, **kwargs) -> PreSignInterceptor:
    kwargs.setdefault("policy", _policy())
    kwargs.setdefault("authorization_provider", _Provider())
    return PreSignInterceptor(signer=signer, **kwargs)


# ---------------------------------------------------------------------------
# P0-1 — chain equality
# ---------------------------------------------------------------------------


def test_p0_chain_mismatch_is_denied():
    """Reproduced: policy=Base(8453), tx=Base Sepolia(84532), signature produced."""
    signer = _Signer()
    with pytest.raises(EnforcementDenied) as excinfo:
        _gate(signer).sign(
            AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx(chainId=84532))
        )

    assert "chain mismatch" in str(excinfo.value)
    assert len(signer.calls) == 0


def test_p0_chain_mismatch_reports_both_chain_ids():
    """The denial must name both chains, not just fail."""
    signer = _Signer()
    with pytest.raises(EnforcementDenied) as excinfo:
        _gate(signer).sign(
            AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx(chainId=42161))
        )

    message = str(excinfo.value)
    assert "42161" in message
    assert "8453" in message


def test_p0_matching_chain_still_signs():
    """The guard must not break the legitimate path."""
    signer = _Signer()
    result = _gate(signer).sign(
        AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx())
    )
    assert len(signer.calls) == 1
    assert result.call_fingerprint.startswith("0x")


def test_p0_chain_mismatch_is_recorded_as_a_denial():
    signer = _Signer()
    gate = _gate(signer)
    with pytest.raises(EnforcementDenied):
        gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx(chainId=84532)))

    entry = gate.audit_log[0]
    assert entry.verdict is AuthorizationVerdict.DENIED
    assert "chain_mismatch" in entry.reasons
    assert entry.signature_hash is None


# ---------------------------------------------------------------------------
# P0-2 — unbound wallet must refuse every write-capable transaction
# ---------------------------------------------------------------------------


def test_p0_unbound_wallet_refuses_contract_creation():
    """Reproduced: unbound wallet signed to=None contract creation."""
    from web3_agent_kit.wallet.wallet import Wallet, WalletConfig

    wallet = Wallet(WalletConfig(private_key="0x" + "11" * 32))
    with pytest.raises(EnforcementDenied):
        wallet.sign_transaction(
            {
                "to": None,
                "data": "0x60806040",
                "value": 10**18,
                "nonce": 1,
                "chainId": 8453,
                "gas": 300_000,
                "gasPrice": 10**9,
            },
            Chain.BASE,
        )


def test_p0_unbound_wallet_refuses_ordinary_call():
    from web3_agent_kit.wallet.wallet import Wallet, WalletConfig

    wallet = Wallet(WalletConfig(private_key="0x" + "11" * 32))
    with pytest.raises(EnforcementDenied):
        wallet.sign_transaction(_tx(), Chain.BASE)


def test_p0_unbound_refusal_message_names_contract_creation():
    from web3_agent_kit.wallet.wallet import Wallet, WalletConfig

    wallet = Wallet(WalletConfig(private_key="0x" + "11" * 32))
    with pytest.raises(EnforcementDenied) as excinfo:
        wallet.sign_transaction(_tx(), Chain.BASE)

    assert "to=None" in str(excinfo.value)


# ---------------------------------------------------------------------------
# P0-3 — policy allow is not authority
# ---------------------------------------------------------------------------


def test_p0_policy_allow_without_provider_does_not_sign():
    """Reproduced: allowed policy + no provider produced a signature."""
    signer = _Signer()
    gate = PreSignInterceptor(policy=_policy(), signer=signer)

    with pytest.raises(EnforcementDenied) as excinfo:
        gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx()))

    assert "no principal authorization provider" in str(excinfo.value)
    assert len(signer.calls) == 0


def test_p0_null_provider_denies_even_when_policy_allows():
    signer = _Signer()
    gate = PreSignInterceptor(
        policy=_policy(), signer=signer, authorization_provider=NullAuthorizationProvider()
    )

    with pytest.raises(EnforcementDenied):
        gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx()))

    assert len(signer.calls) == 0


def test_p0_refusing_provider_blocks_signing():
    signer = _Signer()

    class _Refusing:
        @property
        def policy_id(self) -> str:
            return "refusing"

        def authorize(self, context):
            raise AuthorizationDenied("no authorization on file")

    gate = PreSignInterceptor(
        policy=_policy(), signer=signer, authorization_provider=_Refusing()
    )
    with pytest.raises(EnforcementDenied) as excinfo:
        gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx()))

    assert "principal authorization denied" in str(excinfo.value)
    assert len(signer.calls) == 0


def test_p0_evidence_for_another_call_is_rejected():
    signer = _Signer()

    class _WrongCall:
        @property
        def policy_id(self) -> str:
            return "wrong-call"

        def authorize(self, context):
            return AuthorizationEvidence(
                authorization_id="wrong",
                envelope_digest="0x" + "ab" * 32,
                executor=context.envelope.executor,
                authorizer="0x" + "99" * 20,
                valid_from=0,
                valid_until=2**31,
                nonce="1",
                policy_commitment_digest=context.policy_commitment.digest(),
            )

    gate = PreSignInterceptor(
        policy=_policy(), signer=signer, authorization_provider=_WrongCall()
    )
    with pytest.raises(EnforcementDenied) as excinfo:
        gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx()))

    assert "different call" in str(excinfo.value)
    assert len(signer.calls) == 0


def test_p0_evidence_for_another_executor_is_rejected():
    signer = _Signer()

    class _WrongExecutor:
        @property
        def policy_id(self) -> str:
            return "wrong-executor"

        def authorize(self, context):
            return AuthorizationEvidence(
                authorization_id="wrong-exec",
                envelope_digest=context.envelope_digest,
                executor="0x" + "77" * 20,
                authorizer="0x" + "99" * 20,
                valid_from=0,
                valid_until=2**31,
                nonce="1",
                policy_commitment_digest=context.policy_commitment.digest(),
            )

    gate = PreSignInterceptor(
        policy=_policy(), signer=signer, authorization_provider=_WrongExecutor()
    )
    with pytest.raises(EnforcementDenied) as excinfo:
        gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx()))

    assert "names executor" in str(excinfo.value)
    assert len(signer.calls) == 0


def test_p0_expired_evidence_is_rejected():
    signer = _Signer()
    gate = PreSignInterceptor(
        policy=_policy(),
        signer=signer,
        authorization_provider=_Provider(valid_from=0, valid_until=1),
    )
    with pytest.raises(EnforcementDenied) as excinfo:
        gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx()))

    assert "validity window" in str(excinfo.value)
    assert len(signer.calls) == 0


def test_p0_authorization_is_single_use_even_with_a_stateless_verifier():
    """A verifier with no replay state must not make replay possible."""
    signer = _Signer()
    gate = _gate(signer)

    gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx()))
    assert len(signer.calls) == 1

    with pytest.raises(EnforcementDenied) as excinfo:
        gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx()))

    assert "already been consumed" in str(excinfo.value)
    assert len(signer.calls) == 1


def test_p0_stage_order_policy_runs_before_authorization():
    """A policy denial must be reported as such, not as a missing authorization.

    If authorization ran first, a denied transaction would surface an
    authorization error and mask the policy verdict.
    """
    signer = _Signer()
    gate = PreSignInterceptor(
        policy=_policy(allowed_contracts=frozenset({"0x" + "11" * 20})),
        signer=signer,
        authorization_provider=_Provider(),
    )
    with pytest.raises(EnforcementDenied) as excinfo:
        gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx()))

    assert "contract_not_allowed" in str(excinfo.value)
    assert len(signer.calls) == 0


def test_p0_confirmation_cannot_skip_authorization():
    """Confirmation is UX. It must not substitute for authorization."""
    signer = _Signer()
    gate = PreSignInterceptor(
        policy=_policy(require_confirmation=True),
        signer=signer,
        confirmation_fn=lambda request, decision: True,
    )
    with pytest.raises(EnforcementDenied) as excinfo:
        gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, _tx()))

    assert "no principal authorization provider" in str(excinfo.value)
    assert len(signer.calls) == 0


# ---------------------------------------------------------------------------
# Canonical envelope and evidence separation
# ---------------------------------------------------------------------------


def test_envelope_binds_executor():
    """The fingerprint must cover the sender, which the old one omitted."""
    other = _tx()
    other["from"] = "0x" + "55" * 20

    base = CallEnvelopeV1.from_transaction(transaction=_tx(), chain=Chain.BASE)
    changed = CallEnvelopeV1.from_transaction(transaction=other, chain=Chain.BASE)

    assert base.digest() != changed.digest()
    assert base.executor != changed.executor


def test_envelope_treats_equivalent_calldata_identically():
    absent = _tx()
    del absent["data"]
    explicit = _tx(data="0x")

    assert (
        CallEnvelopeV1.from_transaction(transaction=absent, chain=Chain.BASE).digest()
        == CallEnvelopeV1.from_transaction(
            transaction=explicit, chain=Chain.BASE
        ).digest()
    )


def test_envelope_rejects_chain_mismatch_directly():
    from web3_agent_kit.execution import CallEnvelopeError

    with pytest.raises(CallEnvelopeError):
        CallEnvelopeV1.from_transaction(
            transaction=_tx(chainId=84532), chain=Chain.BASE
        )


def test_envelope_rejects_boolean_nonce_and_value():
    """``True`` is an int in Python; it must not be silently read as 1."""
    from web3_agent_kit.execution import CallEnvelopeError

    for field in ("nonce", "value"):
        with pytest.raises(CallEnvelopeError):
            CallEnvelopeV1.from_transaction(
                transaction=_tx(**{field: True}), chain=Chain.BASE
            )


def test_contract_creation_uses_a_distinct_profile():
    envelope = CallEnvelopeV1.from_transaction(
        transaction={"to": None, "from": SENDER, "data": "0x60806040", "nonce": 0,
                     "chainId": 8453},
        chain=Chain.BASE,
    )
    assert envelope.execution_profile == "create"
    assert "target" not in envelope.to_payload()


def test_policy_commitment_is_a_separate_domain():
    envelope = CallEnvelopeV1.from_transaction(transaction=_tx(), chain=Chain.BASE)
    commitment = PolicyDecisionCommitment(
        call_identity=envelope.digest(),
        policy_id="ExecutionPolicy",
        verdict="allow",
        reason_codes=(),
        evaluated_at=1_789_699_093,
    )

    assert commitment.digest() != envelope.digest()
    assert commitment.call_identity == envelope.digest()

    ctx = commitment.as_context_commitment()
    assert ctx["namespace"] == "web3-agent-kit.policy-decision.v1"
    assert ctx["algorithm"] == "sha256"


def test_domain_separation_holds_for_identical_field_sets():
    """Same fields, different domain label, different digest."""
    from web3_agent_kit.execution.envelope import _domain_hash

    payload = {"a": 1, "b": "x"}
    assert _domain_hash("domain-a", payload) != _domain_hash("domain-b", payload)


# ---------------------------------------------------------------------------
# P1-4 — static checker must follow aliases
# ---------------------------------------------------------------------------


def _run_checker(source: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as tmp:
        pkg = Path(tmp) / "pkg"
        pkg.mkdir()
        (pkg / "module.py").write_text(source)
        return subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[1]
                    / "tools"
                    / "check_signing_surface.py"
                ),
                "--root",
                str(pkg),
            ],
            capture_output=True,
            text=True,
        )


@pytest.mark.parametrize(
    "source",
    [
        "def f(acct, tx):\n    return acct.sign_transaction(tx)\n",
        "def f(acct, tx):\n    signer = acct.sign_transaction\n    return signer(tx)\n",
        (
            "def f(acct, tx):\n"
            "    signer = acct.sign_transaction\n"
            "    again = signer\n"
            "    return again(tx)\n"
        ),
        (
            "def f(acct, tx):\n"
            "    signer: object = acct.sign_transaction\n"
            "    return signer(tx)\n"
        ),
        (
            "from eth_account import sign_transaction as st\n"
            "def f(tx):\n"
            "    return st(tx)\n"
        ),
    ],
    ids=["direct", "alias", "alias-chain", "annotated-alias", "import-alias"],
)
def test_p1_static_check_catches_every_signer_shape(source):
    result = _run_checker(source)
    assert result.returncode == 1, (
        f"checker missed a signer shape:\n{result.stdout}"
    )


def test_p1_static_check_does_not_flag_unrelated_methods():
    result = _run_checker("def f(acct, tx):\n    return acct.send_raw_transaction(tx)\n")
    assert result.returncode == 0


def test_p1_static_check_reports_the_alias_origin():
    result = _run_checker(
        "def f(acct, tx):\n    signer = acct.sign_transaction\n    return signer(tx)\n"
    )
    assert "aliased from acct.sign_transaction" in result.stdout
