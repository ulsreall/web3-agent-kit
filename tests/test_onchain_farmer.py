"""Chain resolution and signing through the gate, on-chain farmer.

`_send_transaction` is the only place this module produces a signature, and it
builds the authorization request itself — including the chain the gate will
compare the transaction's ``chainId`` against. A chain resolved to the wrong
member refuses every write, so the mapping is pinned here rather than assumed.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from eth_account import Account

from web3_agent_kit.airdrop.onchain import (
    OnChainAirdropFarmer,
    OnChainConfig,
    TransactionResult,
)
from web3_agent_kit.chains import Chain as EvmChain
from web3_agent_kit.execution import (
    ActionType,
    AuthorizationEvidence,
    CallableAuthorizationProvider,
    ExecutionPolicy,
)

SENDER_KEY = "0x" + "11" * 32
SENDER = Account.from_key(SENDER_KEY).address
TARGET = "0x" + "22" * 20


def _policy(chain: EvmChain) -> ExecutionPolicy:
    return ExecutionPolicy(
        allowed_chains=frozenset({chain}),
        allowed_actions=frozenset(ActionType),
        allowed_contracts=frozenset({TARGET}),
        max_native_value_wei=10**18,
        require_confirmation=False,
    )


def _provider():
    def verify(context):
        now = int(time.time())
        return AuthorizationEvidence(
            authorization_id="auth-1",
            envelope_digest=context.envelope_digest,
            executor=context.envelope.executor,
            authorizer=SENDER,
            valid_from=now - 5,
            valid_until=now + 300,
            nonce="1",
            policy_commitment_digest=context.policy_commitment.digest(),
        )

    return CallableAuthorizationProvider(verify)


def _no_connect():
    class NoConnect:
        HTTPProvider = staticmethod(lambda url: SimpleNamespace(endpoint_uri=url))

        def __init__(self, provider):
            pass

    return NoConnect


def _tx(chain_id: int) -> dict:
    return {
        "from": SENDER,
        "to": TARGET,
        "nonce": 0,
        "chainId": chain_id,
        "value": 0,
        "data": "0x" + "aa" * 4,
        "gas": 100_000,
        "maxFeePerGas": 10**9,
        "maxPriorityFeePerGas": 10**9,
    }


def _farmer(chain: str, *, gate_chain: EvmChain | None = None) -> OnChainAirdropFarmer:
    resolved = gate_chain or EvmChain(str(chain)) if chain not in ("bnb",) else EvmChain.BSC
    farmer = OnChainAirdropFarmer(
        OnChainConfig(chain=chain, private_key=SENDER_KEY),
        policy=_policy(resolved),
        authorization_provider=_provider(),
    )
    farmer._account = Account.from_key(SENDER_KEY)
    return farmer


class TestChainResolution:
    @pytest.mark.parametrize(
        ("configured", "expected"),
        [
            ("base", EvmChain.BASE),
            ("ethereum", EvmChain.ETHEREUM),
            ("arbitrum", EvmChain.ARBITRUM),
            ("BASE", EvmChain.BASE),
        ],
    )
    def test_canonical_names_resolve(self, configured, expected):
        farmer = OnChainAirdropFarmer(OnChainConfig(chain=configured))
        assert farmer._resolve_chain() == expected

    def test_bnb_is_bsc(self):
        # This module's enum says "bnb"; the gate's says "bsc". The old lookup
        # fell through to Ethereum and the gate then refused the 56 chainId.
        assert _farmer("bnb")._resolve_chain() == EvmChain.BSC

    def test_avalanche_resolves(self):
        assert _farmer("avalanche")._resolve_chain() == EvmChain.AVALANCHE

    def test_unknown_chain_names_itself(self):
        farmer = OnChainAirdropFarmer(OnChainConfig(chain="zksync"))
        with pytest.raises(ValueError, match="no EIP-155 envelope"):
            farmer._resolve_chain()


class TestSendTransaction:
    def _fake_web3(self):
        captured = {}

        def send_raw(signed):
            captured["signed"] = signed
            return "0x" + "ab" * 32

        web3 = SimpleNamespace(
            eth=SimpleNamespace(
                send_raw_transaction=send_raw,
                wait_for_transaction_receipt=lambda tx_hash, timeout=None: SimpleNamespace(
                    transactionHash=SimpleNamespace(hex=lambda: "0xdead")
                ),
            )
        )
        return web3, captured

    def test_transaction_is_signed_through_the_gate_and_sent(self):
        farmer = _farmer("base")
        farmer._web3, captured = self._fake_web3()
        assert farmer._send_transaction(_tx(8453)) == "0xdead"
        assert captured["signed"]

    def test_wrong_chain_is_refused_before_sending(self):
        # Gate policy says Base, transaction says Base Sepolia.
        farmer = _farmer("base")
        farmer._web3, captured = self._fake_web3()
        assert farmer._send_transaction(_tx(84532)) is None
        assert "signed" not in captured

    def test_uninitialized_web3_returns_none(self):
        farmer = _farmer("base")
        farmer._web3 = None
        assert farmer._send_transaction(_tx(8453)) is None

    def test_uninitialized_account_returns_none(self):
        farmer = _farmer("base")
        farmer._web3, _ = self._fake_web3()
        farmer._account = None
        assert farmer._send_transaction(_tx(8453)) is None

    def test_gate_is_reused_across_sends(self):
        farmer = _farmer("base")
        first = farmer._gate()
        assert farmer._gate() is first


class TestDailyLimit:
    def test_limit_is_exclusive(self):
        farmer = OnChainAirdropFarmer(OnChainConfig(max_daily_txs=2))
        assert farmer._check_daily_limit() is True
        farmer._tx_count = 2
        assert farmer._check_daily_limit() is False


class TestExecutePreview:
    """Every execute_* currently previews under dry_run and admits the rest."""

    @pytest.mark.parametrize("dry_run", [True, False])
    def test_swap(self, dry_run):
        farmer = OnChainAirdropFarmer(OnChainConfig(dry_run=dry_run))
        result = farmer.execute_swap("uniswap", "base", "ETH", "USDC", 0.001)
        assert result.status == ("preview" if dry_run else "unsupported")
        assert result.error
        assert "ETH -> USDC" in result.amount

    @pytest.mark.parametrize("dry_run", [True, False])
    def test_bridge(self, dry_run):
        farmer = OnChainAirdropFarmer(OnChainConfig(dry_run=dry_run))
        result = farmer.execute_bridge("base", "arbitrum", 0.001)
        assert result.status == ("preview" if dry_run else "unsupported")

    @pytest.mark.parametrize("dry_run", [True, False])
    def test_lend(self, dry_run):
        farmer = OnChainAirdropFarmer(OnChainConfig(dry_run=dry_run))
        result = farmer.execute_lend("base", "aave", "USDC", 0.01)
        assert result.status == ("preview" if dry_run else "unsupported")

    @pytest.mark.parametrize("dry_run", [True, False])
    def test_stake(self, dry_run):
        farmer = OnChainAirdropFarmer(OnChainConfig(dry_run=dry_run))
        result = farmer.execute_stake("base", "lido", 0.01)
        assert result.status == ("preview" if dry_run else "unsupported")

    def test_results_accumulate(self):
        farmer = OnChainAirdropFarmer(OnChainConfig())
        farmer.execute_swap("uniswap", "base", "ETH", "USDC", 0.001)
        farmer.execute_stake("base", "lido", 0.01)
        assert len(farmer.get_results()) == 2

    def test_summary_counts_previews_separately_from_failures(self):
        farmer = OnChainAirdropFarmer(OnChainConfig())
        farmer.execute_swap("uniswap", "base", "ETH", "USDC", 0.001)
        summary = farmer.get_summary()
        assert summary["preview"] == 1
        assert summary["failed"] == 0
        assert summary["total_transactions"] == 1

    def test_summary_of_nothing_has_no_division_error(self):
        assert OnChainAirdropFarmer(OnChainConfig()).get_summary()["success_rate"] == 0.0


class TestPlans:
    @pytest.mark.asyncio
    async def test_unknown_plan_returns_empty(self):
        assert await OnChainAirdropFarmer(OnChainConfig()).farm_plan("nope") == []

    @pytest.mark.asyncio
    async def test_farm_all_uses_the_chain_plans(self):
        farmer = OnChainAirdropFarmer(OnChainConfig(chain="base", delay_between_txs=0))
        executed = []

        async def fake_execute(plan):
            executed.append(plan.name)

        farmer._execute_plan = fake_execute
        await farmer.farm_all()
        assert executed
        assert farmer.get_plans_for_chain("base")


class TestInit:
    def test_connection_status_is_probed_and_balance_logged(self, monkeypatch):
        calls = []

        class FakeWeb3:
            HTTPProvider = staticmethod(lambda url: SimpleNamespace(endpoint_uri=url))

            def __init__(self, provider):
                calls.append("constructed")

            def is_connected(self):
                return True

            @property
            def eth(self):
                return SimpleNamespace(get_balance=lambda address: 10**18)

            @staticmethod
            def from_wei(value, unit):
                return value / 10**18

        monkeypatch.setattr("web3.Web3", FakeWeb3)
        farmer = OnChainAirdropFarmer(
            OnChainConfig(chain="base", private_key=SENDER_KEY, rpc_url="https://rpc.test")
        )

        assert calls == ["constructed"]
        assert farmer._account.address == SENDER
        assert farmer._web3 is not None

    def test_missing_rpc_leaves_the_farmer_uninitialized(self, monkeypatch):
        monkeypatch.setattr("web3.Web3", _no_connect())
        farmer = OnChainAirdropFarmer(
            OnChainConfig(chain="not-a-chain", private_key=SENDER_KEY, rpc_url="")
        )
        assert farmer._web3 is None
        assert farmer._account is None

    def test_invalid_key_is_reported_not_raised(self, monkeypatch):
        monkeypatch.setattr("web3.Web3", _no_connect())
        farmer = OnChainAirdropFarmer(
            OnChainConfig(chain="base", private_key="0xnope", rpc_url="https://rpc.test")
        )
        assert farmer._account is None

    def test_custom_rpc_is_used_verbatim(self, monkeypatch):
        seen = {}

        class FakeWeb3:
            HTTPProvider = staticmethod(lambda url: SimpleNamespace(endpoint_uri=url))

            def __init__(self, provider):
                seen["url"] = provider.endpoint_uri

            def is_connected(self):
                return False

        monkeypatch.setattr("web3.Web3", FakeWeb3)
        OnChainAirdropFarmer(
            OnChainConfig(chain="base", private_key=SENDER_KEY, rpc_url="https://mine.test")
        )
        assert seen["url"] == "https://mine.test"


class TestResultSerialization:
    def test_to_dict_carries_the_fields_and_drops_timestamp(self):
        result = TransactionResult(
            protocol="uniswap", action="swap", chain="base", status="preview"
        )
        payload = result.to_dict()
        assert payload["status"] == "preview"
        assert "timestamp" not in payload
