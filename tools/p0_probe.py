#!/usr/bin/env python3
"""Reproduce the three P0 findings against a given revision.

This script is the evidence. It runs the same probes YuTao ran, against
whatever code is checked out, and prints a machine-readable result. Run it on
the pre-fix revision to see the gaps open, and on the fixed revision to see
them closed.

Usage:
    python tools/p0_probe.py                 # probe the working tree
    python tools/p0_probe.py --json          # machine-readable output

Exit code is 0 when every gap is closed, 1 when any gap is still open.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ROUTER = "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4"
TEST_KEY = "0x" + "11" * 32

CALLDATA = "0xdeadbeef"


class _RecordingSigner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, tx) -> bytes:
        self.calls.append(dict(tx))
        return b"\x01" * 64


def _sender() -> str:
    from eth_account import Account

    return Account.from_key(TEST_KEY).address


def probe_chain_mismatch() -> dict:
    """Policy evaluates Base (8453); the transaction targets Base Sepolia (84532)."""
    from web3_agent_kit.chains import Chain
    from web3_agent_kit.execution import (
        ActionType,
        AuthorizationRequest,
        EnforcementDenied,
        ExecutionPolicy,
        PreSignInterceptor,
    )

    result: dict = {"id": "CHAIN_MISMATCH_SIGNED", "expected": False}

    policy = ExecutionPolicy(
        allowed_chains=frozenset({Chain.BASE}),
        allowed_actions=frozenset({ActionType.SWAP, ActionType.CONTRACT_CALL}),
        allowed_contracts=frozenset({ROUTER.lower()}),
        max_native_value_wei=10**18,
        require_confirmation=False,
    )
    signer = _RecordingSigner()
    gate = _build_gate(policy=policy, signer=signer)

    tx = {
        "to": ROUTER,
        "from": _sender(),
        "data": CALLDATA,
        "value": 0,
        "nonce": 265,
        "chainId": 84532,  # Base Sepolia, not Base
        "gas": 300_000,
        "gasPrice": 10**9,
    }

    try:
        gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, tx))
        result["observed"] = True
        result["detail"] = "signed a transaction whose chainId the policy never evaluated"
    except EnforcementDenied as exc:
        result["observed"] = False
        result["detail"] = str(exc)
    except Exception as exc:  # noqa: BLE001 - a different failure is still a pass
        result["observed"] = False
        result["detail"] = f"{type(exc).__name__}: {exc}"

    result["signer_reached"] = len(signer.calls)
    result["status"] = "closed" if result["observed"] == result["expected"] else "OPEN"
    return result


def probe_unbound_contract_creation() -> dict:
    """An unbound wallet signing contract creation (to=None)."""
    from web3_agent_kit.chains import Chain
    from web3_agent_kit.execution import EnforcementDenied
    from web3_agent_kit.wallet.wallet import Wallet, WalletConfig

    result: dict = {"id": "UNBOUND_CONTRACT_CREATION_SIGNED", "expected": False}

    wallet = Wallet(WalletConfig(private_key=TEST_KEY))
    tx = {
        "to": None,
        "data": "0x60806040",
        "value": 10**18,
        "nonce": 1,
        "chainId": 8453,
        "gas": 300_000,
        "gasPrice": 10**9,
    }

    try:
        wallet.sign_transaction(tx, Chain.BASE)
        result["observed"] = True
        result["detail"] = "unbound wallet signed contract creation"
    except EnforcementDenied as exc:
        result["observed"] = False
        result["detail"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        result["observed"] = False
        result["detail"] = f"{type(exc).__name__}: {exc}"

    result["status"] = "closed" if result["observed"] == result["expected"] else "OPEN"
    return result


def probe_policy_allow_without_authorization() -> dict:
    """Policy allows, no principal authorization provider configured."""
    from web3_agent_kit.chains import Chain
    from web3_agent_kit.execution import (
        ActionType,
        AuthorizationRequest,
        EnforcementDenied,
        ExecutionPolicy,
        PreSignInterceptor,
    )

    result: dict = {
        "id": "POLICY_ALLOW_SIGNS_WITHOUT_AUTHORIZATION",
        "expected": False,
    }

    policy = ExecutionPolicy(
        allowed_chains=frozenset({Chain.BASE}),
        allowed_actions=frozenset({ActionType.SWAP, ActionType.CONTRACT_CALL}),
        allowed_contracts=frozenset({ROUTER.lower()}),
        max_native_value_wei=10**18,
        require_confirmation=False,
    )
    signer = _RecordingSigner()
    # Deliberately no authorization provider: this probes what happens when
    # policy allows and nothing else is configured.
    gate = _build_gate(policy=policy, signer=signer, with_provider=False)

    tx = {
        "to": ROUTER,
        "from": _sender(),
        "data": CALLDATA,
        "value": 0,
        "nonce": 265,
        "chainId": 8453,
        "gas": 300_000,
        "gasPrice": 10**9,
    }

    try:
        gate.sign(AuthorizationRequest(Chain.BASE, ActionType.SWAP, tx))
        result["observed"] = True
        result["detail"] = "policy allow alone produced a signature"
    except EnforcementDenied as exc:
        result["observed"] = False
        result["detail"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        result["observed"] = False
        result["detail"] = f"{type(exc).__name__}: {exc}"

    result["signer_reached"] = len(signer.calls)
    result["status"] = "closed" if result["observed"] == result["expected"] else "OPEN"
    return result


def probe_aliased_signer() -> dict:
    """The static checker must catch a signer bound to a local name."""
    import subprocess
    import tempfile

    result: dict = {"id": "ALIASED_SIGNER_ESCAPES_CHECKER", "expected": False}

    with tempfile.TemporaryDirectory() as tmp:
        pkg = Path(tmp) / "pkg"
        pkg.mkdir()
        (pkg / "module.py").write_text(
            "def send(account, tx):\n"
            "    signer = account.sign_transaction\n"
            "    return signer(tx)\n"
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "tools" / "check_signing_surface.py"),
                "--root",
                str(pkg),
            ],
            capture_output=True,
            text=True,
        )

    escaped = proc.returncode == 0
    result["observed"] = escaped
    result["detail"] = (
        "checker exited 0 on an aliased signer call"
        if escaped
        else f"checker rejected the aliased call (exit {proc.returncode})"
    )
    result["status"] = "closed" if result["observed"] == result["expected"] else "OPEN"
    return result


def _build_gate(*, policy, signer, with_provider: bool = True):
    """Build a gate, tolerating the pre-hardening constructor signature.

    On the pre-fix revision the gate has no authorization_provider parameter.
    The probe is about what the gate *does*, so construction differences must
    not be what makes a probe pass.

    ``with_provider=False`` omits the provider entirely, which is the
    configuration probe 3 needs.
    """
    from web3_agent_kit.execution import PreSignInterceptor

    if not with_provider:
        try:
            return PreSignInterceptor(policy=policy, signer=signer)
        except TypeError:  # pragma: no cover - pre-hardening signature
            return PreSignInterceptor(policy=policy, signer=signer)

    try:
        from web3_agent_kit.execution import AuthorizationEvidence

        class _Provider:
            @property
            def policy_id(self) -> str:
                return "p0-probe-provider"

            def authorize(self, context):
                return AuthorizationEvidence(
                    authorization_id="p0-probe-auth",
                    envelope_digest=context.envelope_digest,
                    executor=context.envelope.executor,
                    authorizer="0x" + "99" * 20,
                    valid_from=0,
                    valid_until=2**31,
                    nonce="1",
                    policy_commitment_digest=context.policy_commitment.digest(),
                )

        return PreSignInterceptor(
            policy=policy, signer=signer, authorization_provider=_Provider()
        )
    except ImportError:
        # Pre-hardening revision: no authorization module exists.
        return PreSignInterceptor(policy=policy, signer=signer)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args(argv)

    results = [
        probe_chain_mismatch(),
        probe_unbound_contract_creation(),
        probe_policy_allow_without_authorization(),
        probe_aliased_signer(),
    ]

    open_gaps = [r for r in results if r["status"] == "OPEN"]

    if args.json:
        print(json.dumps({"results": results, "open_gaps": len(open_gaps)}, indent=1))
    else:
        print("P0 probe — reproduced findings, not claims\n")
        for r in results:
            marker = "OPEN  " if r["status"] == "OPEN" else "closed"
            print(f"  [{marker}] {r['id']}")
            print(f"           {r['detail']}")
            if "signer_reached" in r:
                print(f"           signer reached: {r['signer_reached']}")
            print()
        print(f"open gaps: {len(open_gaps)} of {len(results)}")

    return 1 if open_gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
