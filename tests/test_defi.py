"""Tests for src/defi/__init__.py — Uniswap V2 integration."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.defi import (
    Uniswap,
    Aerodrome,
    Aave,
    Curve,
    DeFiTool,
    SwapResult,
    YieldOpportunity,
    UNISWAP_V2_ROUTER_ABI,
    ERC20_ABI,
    WETH,
    NATIVE,
    STABLECOINS,
)
from src.chains.chain import Chain, ChainManager, CHAIN_IDS
from src.wallet.wallet import Wallet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_w3():
    """Return a fully-mocked Web3 instance."""
    w3 = MagicMock()
    w3.to_checksum_address.side_effect = lambda addr: addr
    w3.eth.gas_price = 20_000_000_000
    w3.eth.get_transaction_count.return_value = 42
    w3.eth.send_raw_transaction.return_value = MagicMock(hex=lambda: "0xabc123")
    receipt = MagicMock()
    receipt.gasUsed = 150_000
    w3.eth.wait_for_transaction_receipt.return_value = receipt
    return w3


def _mock_chain_manager(w3=None):
    """Return a mocked ChainManager that hands back *w3*."""
    cm = MagicMock(spec=ChainManager)
    cm.get_web3.return_value = w3 or _mock_w3()
    return cm


def _mock_wallet():
    """Return a mocked Wallet."""
    w = MagicMock(spec=Wallet)
    w.address = "0xDeadBeef00000000000000000000000000000000"
    w.sign_transaction.return_value = b"signed_tx_bytes"
    return w


def _setup_router_mock(w3):
    """Set up router contract mock with getAmountsOut."""
    router_contract = MagicMock()
    router_contract.functions.getAmountsOut.return_value.call.return_value = [
        10**18, 1500 * 10**6
    ]
    router_contract.functions.swapExactETHForTokens.return_value.build_transaction.return_value = {"dummy": "eth_for_tokens"}
    router_contract.functions.swapExactTokensForETH.return_value.build_transaction.return_value = {"dummy": "tokens_for_eth"}
    router_contract.functions.swapExactTokensForTokens.return_value.build_transaction.return_value = {"dummy": "tokens_for_tokens"}
    return router_contract


def _setup_token_contract(w3, decimals=18):
    """Return a mock ERC20 contract attached to w3."""
    token_contract = MagicMock()
    token_contract.functions.decimals.return_value.call.return_value = decimals
    token_contract.functions.allowance.return_value.call.return_value = 0
    token_contract.functions.approve.return_value.build_transaction.return_value = {"dummy": "approve"}
    return token_contract


def _make_uniswap(chain_manager, slippage=0.5):
    """Convenience: create an Uniswap instance."""
    return Uniswap(chain_manager=chain_manager, slippage=slippage)


# ---------------------------------------------------------------------------
# Constants & data classes
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants are well-formed."""

    def test_weth_addresses_defined(self):
        assert Chain.ETHEREUM in WETH
        assert Chain.BASE in WETH
        assert Chain.ARBITRUM in WETH

    def test_weth_ethereum_address(self):
        assert WETH[Chain.ETHEREUM] == "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

    def test_native_address(self):
        assert NATIVE == "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

    def test_stablecoins_ethereum_has_usdc(self):
        assert "USDC" in STABLECOINS[Chain.ETHEREUM]

    def test_abi_parsed(self):
        assert isinstance(UNISWAP_V2_ROUTER_ABI, list)
        assert len(UNISWAP_V2_ROUTER_ABI) == 4
        assert isinstance(ERC20_ABI, list)
        assert len(ERC20_ABI) == 3


class TestSwapResult:
    def test_fields(self):
        sr = SwapResult(
            tx_hash="0x123", token_in="ETH", token_out="USDC",
            amount_in=1.0, amount_out=1500.0, gas_used=150_000,
            chain=Chain.ETHEREUM,
        )
        assert sr.tx_hash == "0x123"
        assert sr.chain == Chain.ETHEREUM


class TestYieldOpportunity:
    def test_fields(self):
        yo = YieldOpportunity(
            protocol="aave", pool="USDC", apy=5.0,
            tvl=1_000_000, chain=Chain.ETHEREUM, risk_score=2.0,
        )
        assert yo.apy == 5.0


# ---------------------------------------------------------------------------
# DeFiTool ABC
# ---------------------------------------------------------------------------

class TestDeFiTool:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            DeFiTool()


# ---------------------------------------------------------------------------
# Uniswap.resolve_token
# ---------------------------------------------------------------------------

class TestResolveToken:
    def setup_method(self):
        self.uni = Uniswap()

    def test_eth(self):
        assert self.uni.resolve_token("ETH", Chain.ETHEREUM) == NATIVE

    def test_native(self):
        assert self.uni.resolve_token("NATIVE", Chain.ETHEREUM) == NATIVE

    def test_matic(self):
        assert self.uni.resolve_token("MATIC", Chain.ETHEREUM) == NATIVE

    def test_case_insensitive(self):
        assert self.uni.resolve_token("eth", Chain.ETHEREUM) == NATIVE

    def test_usdc_ethereum(self):
        expected = STABLECOINS[Chain.ETHEREUM]["USDC"]
        assert self.uni.resolve_token("USDC", Chain.ETHEREUM) == expected

    def test_usdc_lower(self):
        expected = STABLECOINS[Chain.ETHEREUM]["USDC"]
        assert self.uni.resolve_token("usdc", Chain.ETHEREUM) == expected

    def test_usdt_ethereum(self):
        expected = STABLECOINS[Chain.ETHEREUM]["USDT"]
        assert self.uni.resolve_token("USDT", Chain.ETHEREUM) == expected

    def test_weth_ethereum(self):
        assert self.uni.resolve_token("WETH", Chain.ETHEREUM) == WETH[Chain.ETHEREUM]

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown token symbol"):
            self.uni.resolve_token("DOGE", Chain.ETHEREUM)

    def test_unknown_chain_raises(self):
        with pytest.raises((ValueError, KeyError)):
            self.uni.resolve_token("USDC", Chain.SOLANA)


# ---------------------------------------------------------------------------
# Uniswap.get_quote
# ---------------------------------------------------------------------------

class TestGetQuote:
    def _build_quote_uniswap(self):
        """Build an Uniswap with mocked chain_manager for quoting."""
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        router_contract = _setup_router_mock(w3)
        token_contract = _setup_token_contract(w3, decimals=6)

        def contract_factory(address, abi):
            if abi == UNISWAP_V2_ROUTER_ABI:
                return router_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        return Uniswap(chain_manager=cm), w3

    def test_quote_eth_to_token(self):
        uni, w3 = self._build_quote_uniswap()
        result = uni.get_quote("ETH", "USDC", 1.0, chain=Chain.ETHEREUM)
        assert "amount_out" in result
        assert result["amount_in"] == 1.0
        assert result["chain"] == "ethereum"
        assert "price" in result

    def test_quote_token_to_eth(self):
        uni, w3 = self._build_quote_uniswap()
        result = uni.get_quote("USDC", "ETH", 1500.0, chain=Chain.ETHEREUM)
        assert "amount_out" in result

    def test_quote_token_to_token(self):
        uni, w3 = self._build_quote_uniswap()
        result = uni.get_quote("USDC", "USDT", 100.0, chain=Chain.ETHEREUM)
        assert "amount_out" in result

    def test_quote_unsupported_chain(self):
        uni = Uniswap(chain_manager=_mock_chain_manager())
        with pytest.raises(ValueError, match="not supported"):
            uni.get_quote("ETH", "USDC", 1.0, chain=Chain.SOLANA)

    def test_quote_no_chain_manager(self):
        uni = Uniswap()
        with pytest.raises(ValueError, match="ChainManager required"):
            uni.get_quote("ETH", "USDC", 1.0)

    def test_quote_error_returns_error_dict(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        router_contract = MagicMock()
        router_contract.functions.getAmountsOut.return_value.call.side_effect = Exception("No liquidity")
        token_contract = _setup_token_contract(w3)

        def contract_factory(address, abi):
            if abi == UNISWAP_V2_ROUTER_ABI:
                return router_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        uni = Uniswap(chain_manager=cm)
        result = uni.get_quote("ETH", "USDC", 1.0, chain=Chain.ETHEREUM)
        assert "error" in result
        assert "No liquidity" in result["error"]


# ---------------------------------------------------------------------------
# Uniswap._approve_token
# ---------------------------------------------------------------------------

class TestApproveToken:
    def test_approve_when_no_allowance(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        token_contract = MagicMock()
        token_contract.functions.allowance.return_value.call.return_value = 0
        token_contract.functions.approve.return_value.build_transaction.return_value = {"dummy": "approve"}
        w3.eth.contract.return_value = token_contract

        uni = Uniswap(chain_manager=cm)
        uni._approve_token(wallet, "0xToken", "0xSpender", 1000, w3, Chain.ETHEREUM, 0)

        w3.eth.send_raw_transaction.assert_called_once()
        w3.eth.wait_for_transaction_receipt.assert_called_once()

    def test_skip_when_already_approved(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        token_contract = MagicMock()
        token_contract.functions.allowance.return_value.call.return_value = 999999
        w3.eth.contract.return_value = token_contract

        uni = Uniswap(chain_manager=cm)
        uni._approve_token(wallet, "0xToken", "0xSpender", 1000, w3, Chain.ETHEREUM, 0)

        w3.eth.send_raw_transaction.assert_not_called()


# ---------------------------------------------------------------------------
# Uniswap.execute — full swap flows
# ---------------------------------------------------------------------------

class TestExecuteSwap:
    def _prepare_swap(self, is_eth_in=True, is_eth_out=False, decimals=18, out_decimals=6):
        """Common setup for execute tests."""
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        router_contract = _setup_router_mock(w3)
        in_token = _setup_token_contract(w3, decimals=decimals)
        out_token = _setup_token_contract(w3, decimals=out_decimals)

        def contract_factory(address, abi):
            if abi == UNISWAP_V2_ROUTER_ABI:
                return router_contract
            return in_token

        w3.eth.contract.side_effect = contract_factory
        return Uniswap(chain_manager=cm), wallet, w3, router_contract

    def test_swap_eth_for_tokens(self):
        uni, wallet, w3, router = self._prepare_swap(is_eth_in=True)
        result = uni.execute(wallet, "ETH", "USDC", 0.1, chain=Chain.ETHEREUM)

        assert isinstance(result, SwapResult)
        assert result.tx_hash == "0xabc123"
        assert result.amount_in == 0.1
        assert result.chain == Chain.ETHEREUM
        assert result.gas_used == 150_000
        router.functions.swapExactETHForTokens.assert_called_once()

    def test_swap_tokens_for_eth(self):
        """TOKEN→ETH path: calls approve then swapExactTokensForETH."""
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        router_contract = MagicMock()
        router_contract.functions.getAmountsOut.return_value.call.return_value = [
            1000 * 10**6, 10**18
        ]
        router_contract.functions.swapExactTokensForETH.return_value.build_transaction.return_value = {"dummy": "tfe"}

        token_contract = MagicMock()
        token_contract.functions.decimals.return_value.call.return_value = 6
        token_contract.functions.allowance.return_value.call.return_value = 0
        token_contract.functions.approve.return_value.build_transaction.return_value = {"dummy": "approve"}

        def contract_factory(address, abi):
            if abi == UNISWAP_V2_ROUTER_ABI:
                return router_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        uni = Uniswap(chain_manager=cm)
        result = uni.execute(wallet, "USDC", "ETH", 1000, chain=Chain.ETHEREUM)

        assert isinstance(result, SwapResult)
        router_contract.functions.swapExactTokensForETH.assert_called_once()

    def test_swap_tokens_for_tokens(self):
        """TOKEN→TOKEN path: calls approve then swapExactTokensForTokens."""
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        router_contract = MagicMock()
        router_contract.functions.getAmountsOut.return_value.call.return_value = [
            1000 * 10**6, 999 * 10**6
        ]
        router_contract.functions.swapExactTokensForTokens.return_value.build_transaction.return_value = {"dummy": "tft"}

        token_contract = MagicMock()
        token_contract.functions.decimals.return_value.call.return_value = 6
        token_contract.functions.allowance.return_value.call.return_value = 0
        token_contract.functions.approve.return_value.build_transaction.return_value = {"dummy": "approve"}

        def contract_factory(address, abi):
            if abi == UNISWAP_V2_ROUTER_ABI:
                return router_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        uni = Uniswap(chain_manager=cm)
        result = uni.execute(wallet, "USDC", "USDT", 1000, chain=Chain.ETHEREUM)

        assert isinstance(result, SwapResult)
        router_contract.functions.swapExactTokensForTokens.assert_called_once()

    def test_unsupported_chain_raises(self):
        uni = Uniswap(chain_manager=_mock_chain_manager())
        wallet = _mock_wallet()
        with pytest.raises(ValueError, match="not supported"):
            uni.execute(wallet, "ETH", "USDC", 1.0, chain=Chain.SOLANA)

    def test_no_chain_manager_raises(self):
        uni = Uniswap()
        wallet = _mock_wallet()
        with pytest.raises(ValueError, match="ChainManager required"):
            uni.execute(wallet, "ETH", "USDC", 1.0)

    def test_weth_input_resolves_to_eth_in(self):
        """Passing 'ETH' string as token_in uses the ETH-in swap path."""
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        router_contract = _setup_router_mock(w3)
        token_contract = _setup_token_contract(w3)

        def contract_factory(address, abi):
            if abi == UNISWAP_V2_ROUTER_ABI:
                return router_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory

        uni = Uniswap(chain_manager=cm)
        # 'ETH' resolves to ETH-in path; also verify NATIVE keyword
        result = uni.execute(wallet, "NATIVE", "USDC", 1.0, chain=Chain.ETHEREUM)

        assert isinstance(result, SwapResult)
        router_contract.functions.swapExactETHForTokens.assert_called_once()

    def test_base_chain_swap(self):
        """Verify swapping on Base chain works."""
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        router_contract = _setup_router_mock(w3)
        token_contract = _setup_token_contract(w3)

        def contract_factory(address, abi):
            if abi == UNISWAP_V2_ROUTER_ABI:
                return router_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory

        uni = Uniswap(chain_manager=cm)
        result = uni.execute(wallet, "ETH", "USDC", 0.5, chain=Chain.BASE)

        assert result.chain == Chain.BASE


# ---------------------------------------------------------------------------
# Uniswap — slippage
# ---------------------------------------------------------------------------

class TestSlippage:
    def test_custom_slippage(self):
        uni = Uniswap(slippage=1.0)
        assert uni.slippage == 1.0

    def test_default_slippage(self):
        uni = Uniswap()
        assert uni.slippage == 0.5


# ---------------------------------------------------------------------------
# Aerodrome
# ---------------------------------------------------------------------------

class TestAerodrome:
    def test_name(self):
        assert Aerodrome.name == "aerodrome"

    def test_supported_chains(self):
        assert Chain.BASE in Aerodrome.supported_chains

    def test_inherits_defi_tool(self):
        assert issubclass(Aerodrome, DeFiTool)


# ---------------------------------------------------------------------------
# Aave
# ---------------------------------------------------------------------------

class TestAave:
    def test_name(self):
        assert Aave.name == "aave"

    def test_execute_not_implemented(self):
        aave = Aave()
        with pytest.raises(NotImplementedError):
            aave.execute(MagicMock(), "supply")

    def test_yield_not_implemented(self):
        aave = Aave()
        with pytest.raises(NotImplementedError):
            aave.get_yield_opportunities(Chain.ETHEREUM)


# ---------------------------------------------------------------------------
# Curve
# ---------------------------------------------------------------------------

class TestCurve:
    def test_name(self):
        assert Curve.name == "curve"

    def test_execute_not_implemented(self):
        curve = Curve()
        with pytest.raises(NotImplementedError):
            curve.execute(MagicMock(), "0xpool", "0xin", "0xout", 1.0)


# ---------------------------------------------------------------------------
# Routers dict
# ---------------------------------------------------------------------------

class TestRouters:
    def test_all_supported_chains_have_router(self):
        for chain in Uniswap.supported_chains:
            assert chain in Uniswap.ROUTERS

    def test_ethereum_router_address(self):
        assert Uniswap.ROUTERS[Chain.ETHEREUM] == "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"
