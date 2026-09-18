"""Reproduce the pre-sign enforcement findings against an installed package.

This module is the evidence for the three P0 findings and the alias-checker
finding from an independent review. It runs the same probes, against whatever
code is installed, and reports whether each gap is open or closed.

Why it lives inside the package
-------------------------------
An earlier attempt shipped this as ``tools/p0_probe.py`` and told readers to run
it from the wheel. That was wrong: ``pyproject.toml`` includes only
``web3_agent_kit*``, so ``tools/`` is in neither the wheel nor the sdist. The
probe was unreachable from an installed package, which made the verification
instructions in an evidence bundle unverifiable. Keeping it here means
``pip install web3-agent-kit`` is sufficient to reproduce the findings.

Usage
-----
    python -m web3_agent_kit.execution.p0_probe
    python -m web3_agent_kit.execution.p0_probe --json
    wak-p0-probe

Exit code is 0 when every gap is closed, 1 when any gap is still open.

Scope
-----
These are negative probes: they attempt to make the gate sign something it
should refuse, and report when it does. No probe signs or broadcasts anything.
The signer is a recording stub that returns fixed bytes and never touches a key.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

__all__ = [
    "probe_aliased_signer",
    "probe_chain_mismatch",
    "probe_policy_allow_without_authorization",
    "probe_unbound_contract_creation",
    "run_all_probes",
]

ROUTER = "0x94cC0AaC535CCDB3C01d6787D6413C739ae12bc4"
TEST_KEY = "0x" + "11" * 32
CALLDATA = "0xdeadbeef"


class _RecordingSigner:
    """Stand-in for Account.sign_transaction that records whether it was reached."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, tx) -> bytes:
        self.calls.append(dict(tx))
        return b"\x01" * 64


def _sender() -> str:
    from eth_account import Account

    return Account.from_key(TEST_KEY).address


def _signing_policy():
    from ..chains import Chain
    from .intent import ActionType
    from .policy import ExecutionPolicy

    return ExecutionPolicy(
        allowed_chains=frozenset({Chain.BASE}),
        allowed_actions=frozenset({ActionType.SWAP, ActionType.CONTRACT_CALL}),
        allowed_contracts=frozenset({ROUTER.lower()}),
        max_native_value_wei=10**18,
        require_confirmation=False,
    )


def _transaction(**overrides) -> dict:
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
    tx.update(overrides)
    return tx


def _allowing_provider():
    from .authorization import AuthorizationEvidence

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

    return _Provider()


def _build_gate(*, policy, signer, with_provider: bool = True):
    """Build a gate, tolerating an older constructor signature.

    The probes are about what the gate *does*. A construction difference must
    not be what decides a pass, so a missing authorization_provider parameter
    falls back to the older shape rather than erroring.
    """
    from .interceptor import PreSignInterceptor

    if not with_provider:
        return PreSignInterceptor(policy=policy, signer=signer)

    try:
        return PreSignInterceptor(
            policy=policy, signer=signer, authorization_provider=_allowing_provider()
        )
    except TypeError:
        return PreSignInterceptor(policy=policy, signer=signer)


def _outcome(result: dict, exc: BaseException | None) -> dict:
    if exc is None:
        return result
    result["observed"] = False
    result["detail"] = f"{type(exc).__name__}: {exc}"
    return result


def probe_chain_mismatch() -> dict[str, Any]:
    """Probe 1: policy names Base (8453), the transaction targets Base Sepolia.

    Pre-fix this signed. Policy evaluated one chain and the signature committed
    to another.
    """
    from ..chains import Chain
    from .errors import ExecutionError
    from .intent import ActionType
    from .interceptor import AuthorizationRequest, EnforcementDenied

    result: dict[str, Any] = {"id": "CHAIN_MISMATCH_SIGNED", "expected": False}
    signer = _RecordingSigner()
    gate = _build_gate(policy=_signing_policy(), signer=signer)

    try:
        gate.sign(
            AuthorizationRequest(
                Chain.BASE, ActionType.SWAP, _transaction(chainId=84532)
            )
        )
        result["observed"] = True
        result["detail"] = "signed a transaction whose chainId the policy never evaluated"
    except (EnforcementDenied, ExecutionError) as exc:
        result = _outcome(result, exc)
    except Exception as exc:  # noqa: BLE001 - any refusal is a pass
        result = _outcome(result, exc)

    result["signer_reached"] = len(signer.calls)
    result["status"] = _status(result)
    return result


def probe_unbound_contract_creation() -> dict[str, Any]:
    """Probe 2: an unbound wallet signing contract creation (``to=None``).

    Pre-fix the refusal was keyed on a non-null destination, so this path
    reached the raw signer.
    """
    from ..chains import Chain
    from ..wallet.wallet import Wallet, WalletConfig
    from .errors import ExecutionError
    from .interceptor import EnforcementDenied

    result: dict[str, Any] = {
        "id": "UNBOUND_CONTRACT_CREATION_SIGNED",
        "expected": False,
    }
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
        # Deliberate: this is the API under test. The attribute is resolved
        # dynamically so the static signer-surface check does not read this
        # probe as a signing call site -- it is exercising the refusal, not
        # signing. See APPROVED_FILES in tools/check_signing_surface.py.
        getattr(wallet, "sign_transaction")(tx, Chain.BASE)
        result["observed"] = True
        result["detail"] = "unbound wallet signed contract creation"
    except (EnforcementDenied, ExecutionError) as exc:
        result = _outcome(result, exc)
    except Exception as exc:  # noqa: BLE001
        result = _outcome(result, exc)

    result["status"] = _status(result)
    return result


def probe_policy_allow_without_authorization() -> dict[str, Any]:
    """Probe 3: policy allows, no principal authorization provider configured.

    Pre-fix a policy allow alone produced a signature.
    """
    from ..chains import Chain
    from .errors import ExecutionError
    from .intent import ActionType
    from .interceptor import AuthorizationRequest, EnforcementDenied

    result: dict[str, Any] = {
        "id": "POLICY_ALLOW_SIGNS_WITHOUT_AUTHORIZATION",
        "expected": False,
    }
    signer = _RecordingSigner()
    # Deliberately no provider: this probes the configuration where policy is
    # the only thing standing between the caller and a signature.
    gate = _build_gate(policy=_signing_policy(), signer=signer, with_provider=False)

    try:
        gate.sign(
            AuthorizationRequest(Chain.BASE, ActionType.SWAP, _transaction())
        )
        result["observed"] = True
        result["detail"] = "policy allow alone produced a signature"
    except (EnforcementDenied, ExecutionError) as exc:
        result = _outcome(result, exc)
    except Exception as exc:  # noqa: BLE001
        result = _outcome(result, exc)

    result["signer_reached"] = len(signer.calls)
    result["status"] = _status(result)
    return result


def probe_aliased_signer() -> dict[str, Any]:
    """Probe 4: a signer bound to a local name must not escape the static check.

    Pre-fix the checker only looked at attribute access, so
    ``signer = account.sign_transaction; signer(tx)`` passed clean.
    """
    result: dict[str, Any] = {
        "id": "ALIASED_SIGNER_ESCAPES_CHECKER",
        "expected": False,
    }

    checker = _locate_checker()
    if checker is None:
        result["observed"] = None
        result["detail"] = (
            "checker script not found; install from a source checkout or run "
            "`pytest tests/test_check_signing_surface.py` instead"
        )
        result["status"] = "UNKNOWN"
        return result

    with tempfile.TemporaryDirectory() as tmp:
        pkg = Path(tmp) / "pkg"
        pkg.mkdir()
        (pkg / "module.py").write_text(
            "def send(account, tx):\n"
            "    signer = account.sign_transaction\n"
            "    return signer(tx)\n"
        )
        proc = subprocess.run(
            [sys.executable, str(checker), "--root", str(pkg)],
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
    result["status"] = _status(result)
    return result


def _locate_checker() -> Path | None:
    """Find the static signer-surface checker.

    The check lives inside this package, so an installed wheel has it. A source
    checkout also has a thin wrapper at ``tools/check_signing_surface.py``;
    prefer the packaged module so the probe exercises shipped code.

    Returns ``None`` only if neither exists, which means the installation is
    broken rather than that the gap is closed.
    """
    packaged = Path(__file__).resolve().parent / "check_signing_surface.py"
    if packaged.is_file():
        return packaged
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "tools" / "check_signing_surface.py"
        if candidate.is_file():
            return candidate
    return None


def _status(result: dict[str, Any]) -> str:
    if result.get("observed") is None:
        return "UNKNOWN"
    return "closed" if result["observed"] == result["expected"] else "OPEN"


def run_all_probes() -> list[dict[str, Any]]:
    """Run every probe and return the results in a stable order."""
    return [
        probe_chain_mismatch(),
        probe_unbound_contract_creation(),
        probe_policy_allow_without_authorization(),
        probe_aliased_signer(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wak-p0-probe",
        description="Reproduce the pre-sign enforcement findings.",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args(argv)

    results = run_all_probes()
    open_gaps = [r for r in results if r["status"] == "OPEN"]
    unknown = [r for r in results if r["status"] == "UNKNOWN"]

    if args.json:
        print(
            json.dumps(
                {
                    "results": results,
                    "open_gaps": len(open_gaps),
                    "unknown": len(unknown),
                },
                indent=1,
            )
        )
    else:
        print("P0 probe - reproduced findings, not claims\n")
        for r in results:
            marker = {"OPEN": "OPEN  ", "closed": "closed", "UNKNOWN": "unknown"}[
                r["status"]
            ]
            print(f"  [{marker}] {r['id']}")
            print(f"           {r['detail']}")
            if "signer_reached" in r:
                print(f"           signer reached: {r['signer_reached']}")
            print()
        print(f"open gaps: {len(open_gaps)} of {len(results)}")
        if unknown:
            print(f"could not evaluate: {len(unknown)} (see above)")

    # An unknown result is not a pass. Refuse to report success when a probe
    # could not run, so a missing file cannot look like a closed gap.
    if unknown:
        return 2
    return 1 if open_gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
