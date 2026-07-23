"""Tests for src/defi/uniswap_v3.py — Uniswap V3 integration."""

import pytest
from unittest.mock import MagicMock, patch

from web3_agent_kit.defi.uniswap_v3 import (
    UniswapV3,
    V3SwapResult,
    PoolInfo,
    PositionInfo,
    FEE_TIERS,
    SWAP_ROUTER,
    SWAP_ROUTER_02,
    QUOTER_V2,
    NONFUNGIBLE_POSITION_MANAGER,
    FACTORY,
    SWAP_ROUTER_ABI,
    QUOTER_V2_ABI,
    FACTORY_ABI,
    POOL_ABI,
    NONFUNGIBLE_POSITION_MANAGER_ABI,
    MIN_TICK,
    MAX_TICK,
    get_sqrt_ratio_at_tick,
    get_tick_at_sqrt_ratio,
    nearest_usable_tick,
)
from web3_agent_kit.chains.chain import Chain, ChainManager, CHAIN_IDS


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
    receipt.gasUsed = 200_000
    w3.eth.wait_for_transaction_receipt.return_value = receipt
    return w3


def _mock_chain_manager(w3=None):
    """Return a mocked ChainManager that hands back *w3*."""
    cm = MagicMock(spec=ChainManager)
    cm.get_web3.return_value = w3 or _mock_w3()
    return cm


def _mock_wallet():
    """Return a mocked Wallet."""
    w = MagicMock()
    w.address = "0xDeadBeef00000000000000000000000000000000"
    w.sign_transaction.return_value = b"signed_tx_bytes"
    return w


def _setup_token_contract(decimals=18):
    """Return a mock ERC20 contract."""
    token = MagicMock()
    token.functions.decimals.return_value.call.return_value = decimals
    token.functions.allowance.return_value.call.return_value = 0
    token.functions.approve.return_value.build_transaction.return_value = {"dummy": "approve"}
    return token


def _setup_quoter_mock(amount_out_raw=1500 * 10**6, gas_estimate=150_000):
    """Return a mock QuoterV2 contract."""
    quoter = MagicMock()
    quoter.functions.quoteExactInputSingle.return_value.call.return_value = (
        amount_out_raw,
        79228162514264337593543950336,  # sqrtPriceX96After
        3,                              # initializedTicksCrossed
        gas_estimate,                   # gasEstimate
    )
    return quoter


def _setup_factory_mock(pool_addr="0xPoolAddress1234567890abcdef1234567890abcdef"):
    """Return a mock Factory contract."""
    factory = MagicMock()
    factory.functions.getPool.return_value.call.return_value = pool_addr
    factory.functions.createPool.return_value.build_transaction.return_value = {"dummy": "create_pool"}
    return factory


def _setup_pool_mock(liquidity=1_000_000, sqrt_price_x96=79228162514264337593543950336, tick=0):
    """Return a mock Pool contract."""
    pool = MagicMock()
    pool.functions.liquidity.return_value.call.return_value = liquidity
    pool.functions.slot0.return_value.call.return_value = (
        sqrt_price_x96,
        tick,
        0, 0, 0, 0, True
    )
    return pool


def _setup_nfp_mock():
    """Return a mock NonfungiblePositionManager contract."""
    nfp = MagicMock()
    # positions() returns (nonce, operator, token0, token1, fee, tickLower, tickUpper,
    #                      liquidity, feeGrowthInside0LastX128, feeGrowthInside1LastX128,
    #                      tokensOwed0, tokensOwed1)
    nfp.functions.positions.return_value.call.return_value = (
        0,                                    # nonce
        "0xOperator",                         # operator
        "0xToken0Addr",                       # token0
        "0xToken1Addr",                       # token1
        3000,                                 # fee
        -600,                                 # tickLower
        600,                                  # tickUpper
        500_000,                              # liquidity
        0, 0,                                 # feeGrowth
        100 * 10**6,                          # tokensOwed0
        50 * 10**18,                          # tokensOwed1
    )
    nfp.functions.mint.return_value.build_transaction.return_value = {"dummy": "mint"}
    nfp.functions.increaseLiquidity.return_value.build_transaction.return_value = {"dummy": "increase"}
    nfp.functions.decreaseLiquidity.return_value.build_transaction.return_value = {"dummy": "decrease"}
    nfp.functions.collect.return_value.build_transaction.return_value = {"dummy": "collect"}
    return nfp


# ---------------------------------------------------------------------------
# Constants & Addresses
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify module-level constants."""

    def test_swap_router_address(self):
        assert SWAP_ROUTER == "0xE592427A0AEce92De3Edee1F18E0157C05861564"

    def test_swap_router02_address(self):
        assert SWAP_ROUTER_02 == "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"

    def test_quoter_v2_address(self):
        assert QUOTER_V2 == "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"

    def test_nfp_manager_address(self):
        assert NONFUNGIBLE_POSITION_MANAGER == "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"

    def test_factory_address(self):
        assert FACTORY == "0x1F98431c8aD98523631AE4a59f267346ea31F984"

    def test_fee_tiers(self):
        assert 100 in FEE_TIERS
        assert 500 in FEE_TIERS
        assert 3000 in FEE_TIERS
        assert 10000 in FEE_TIERS
        assert len(FEE_TIERS) == 4

    def test_fee_tier_tick_spacings(self):
        assert FEE_TIERS[100] == 1
        assert FEE_TIERS[500] == 10
        assert FEE_TIERS[3000] == 60
        assert FEE_TIERS[10000] == 200

    def test_abi_parsed(self):
        assert isinstance(SWAP_ROUTER_ABI, list)
        assert len(SWAP_ROUTER_ABI) >= 2
        assert isinstance(QUOTER_V2_ABI, list)
        assert len(QUOTER_V2_ABI) >= 2
        assert isinstance(NONFUNGIBLE_POSITION_MANAGER_ABI, list)
        assert len(NONFUNGIBLE_POSITION_MANAGER_ABI) >= 4
        assert isinstance(FACTORY_ABI, list)
        assert len(FACTORY_ABI) >= 2
        assert isinstance(POOL_ABI, list)
        assert len(POOL_ABI) >= 2


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class TestV3SwapResult:
    def test_fields(self):
        sr = V3SwapResult(
            tx_hash="0x123", token_in="0xA", token_out="0xB",
            amount_in=1.0, amount_out=1500.0, gas_used=200_000, fee_tier=3000,
        )
        assert sr.tx_hash == "0x123"
        assert sr.fee_tier == 3000


class TestPoolInfo:
    def test_fields(self):
        pi = PoolInfo(
            pool_address="0xPool", token0="0xA", token1="0xB", fee=3000,
            liquidity=1_000_000, sqrt_price_x96=79228162514264337593543950336, tick=0,
        )
        assert pi.pool_address == "0xPool"
        assert pi.liquidity == 1_000_000


class TestPositionInfo:
    def test_fields(self):
        pi = PositionInfo(
            token_id=1, token0="0xA", token1="0xB", fee=3000,
            tick_lower=-600, tick_upper=600, liquidity=500_000,
        )
        assert pi.token_id == 1
        assert pi.tick_lower == -600


# ---------------------------------------------------------------------------
# Tick math
# ---------------------------------------------------------------------------

class TestTickMath:
    def test_sqrt_ratio_at_tick_zero(self):
        """Tick 0 should give sqrt(1) * 2^96 = 2^96."""
        result = get_sqrt_ratio_at_tick(0)
        assert result == 2**96

    def test_sqrt_ratio_at_tick_positive(self):
        result = get_sqrt_ratio_at_tick(1000)
        assert result > 0
        assert result > 2**96  # price > 1 for positive tick

    def test_sqrt_ratio_at_tick_negative(self):
        result = get_sqrt_ratio_at_tick(-1000)
        assert result > 0
        assert result < 2**96  # price < 1 for negative tick

    def test_sqrt_ratio_at_tick_out_of_range(self):
        with pytest.raises(ValueError, match="out of range"):
            get_sqrt_ratio_at_tick(MIN_TICK - 1)
        with pytest.raises(ValueError, match="out of range"):
            get_sqrt_ratio_at_tick(MAX_TICK + 1)

    def test_get_tick_at_sqrt_ratio(self):
        """Roundtrip: tick -> sqrt_ratio -> tick."""
        for tick in [0, 100, -100, 1000, -1000]:
            sqrt_price = get_sqrt_ratio_at_tick(tick)
            recovered = get_tick_at_sqrt_ratio(sqrt_price)
            # Should be within 1 tick due to floor rounding
            assert abs(recovered - tick) <= 1, f"tick={tick}, recovered={recovered}"

    def test_get_tick_at_sqrt_ratio_out_of_range(self):
        with pytest.raises(ValueError, match="out of valid range"):
            get_tick_at_sqrt_ratio(0)
        with pytest.raises(ValueError, match="out of valid range"):
            get_tick_at_sqrt_ratio(2**160)

    def test_nearest_usable_tick_basic(self):
        assert nearest_usable_tick(5, 60) == 0
        assert nearest_usable_tick(31, 60) == 60
        assert nearest_usable_tick(-31, 60) == -60
        assert nearest_usable_tick(60, 60) == 60

    def test_nearest_usable_tick_min_boundary(self):
        result = nearest_usable_tick(MIN_TICK + 1, 60)
        assert result >= MIN_TICK
        assert result % 60 == 0

    def test_nearest_usable_tick_max_boundary(self):
        result = nearest_usable_tick(MAX_TICK - 1, 60)
        assert result <= MAX_TICK
        assert result % 60 == 0


# ---------------------------------------------------------------------------
# UniswapV3 constructor
# ---------------------------------------------------------------------------

class TestUniswapV3Init:
    def test_default_init(self):
        v3 = UniswapV3()
        assert v3.slippage == 0.5
        assert v3.chain == Chain.ETHEREUM
        assert v3.swap_router_address == SWAP_ROUTER

    def test_custom_init(self):
        cm = _mock_chain_manager()
        v3 = UniswapV3(chain_manager=cm, slippage=1.0, chain=Chain.BASE)
        assert v3.slippage == 1.0
        assert v3.chain == Chain.BASE

    def test_supported_fee_tiers_property(self):
        v3 = UniswapV3()
        tiers = v3.supported_fee_tiers
        assert 100 in tiers
        assert 3000 in tiers
        assert 10000 in tiers


# ---------------------------------------------------------------------------
# UniswapV3._resolve_token
# ---------------------------------------------------------------------------

class TestResolveToken:
    def test_native_eth(self):
        v3 = UniswapV3()
        w3 = _mock_w3()
        result = v3._resolve_token("ETH", w3)
        assert result == "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"  # WETH

    def test_native_case_insensitive(self):
        v3 = UniswapV3()
        w3 = _mock_w3()
        result = v3._resolve_token("eth", w3)
        assert result == "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

    def test_checksum_address_passthrough(self):
        v3 = UniswapV3()
        w3 = _mock_w3()
        addr = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
        result = v3._resolve_token(addr, w3)
        assert result == addr


# ---------------------------------------------------------------------------
# UniswapV3._is_native
# ---------------------------------------------------------------------------

class TestIsNative:
    def test_eth(self):
        v3 = UniswapV3()
        assert v3._is_native("ETH") is True
        assert v3._is_native("eth") is True
        assert v3._is_native("NATIVE") is True
        assert v3._is_native("MATIC") is True
        assert v3._is_native("0xToken") is False


# ---------------------------------------------------------------------------
# UniswapV3.get_quote
# ---------------------------------------------------------------------------

class TestGetQuote:
    def _build_v3(self, decimals=6):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        quoter = _setup_quoter_mock(amount_out_raw=1500 * 10**decimals)
        token = _setup_token_contract(decimals=decimals)

        def contract_factory(address, abi):
            if abi == QUOTER_V2_ABI:
                return quoter
            return token

        w3.eth.contract.side_effect = contract_factory
        return UniswapV3(chain_manager=cm), w3

    def test_quote_basic(self):
        v3, w3 = self._build_v3()
        result = v3.get_quote("0xTokenIn", "0xTokenOut", 1.0, fee_tier=3000)
        assert "amount_out" in result
        assert result["amount_in"] == 1.0
        assert result["fee_tier"] == 3000
        assert "price" in result
        assert "gas_estimate" in result

    def test_quote_error_returns_error_dict(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        quoter = MagicMock()
        quoter.functions.quoteExactInputSingle.return_value.call.side_effect = Exception("No pool")
        token = _setup_token_contract()

        def contract_factory(address, abi):
            if abi == QUOTER_V2_ABI:
                return quoter
            return token

        w3.eth.contract.side_effect = contract_factory
        v3 = UniswapV3(chain_manager=cm)
        result = v3.get_quote("0xTokenIn", "0xTokenOut", 1.0, fee_tier=3000)
        assert "error" in result
        assert "No pool" in result["error"]

    def test_quote_invalid_fee_tier(self):
        v3 = UniswapV3(chain_manager=_mock_chain_manager())
        result = v3.get_quote("0xA", "0xB", 1.0, fee_tier=999)
        assert "error" in result
        assert "Invalid fee tier" in result["error"]

    def test_quote_no_chain_manager(self):
        v3 = UniswapV3()
        with pytest.raises(ValueError, match="ChainManager required"):
            v3.get_quote("0xA", "0xB", 1.0)


# ---------------------------------------------------------------------------
# UniswapV3.get_pool_info
# ---------------------------------------------------------------------------

class TestGetPoolInfo:
    def test_pool_info(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        factory = _setup_factory_mock("0xPool123")
        pool = _setup_pool_mock(liquidity=5_000_000, tick=100)
        token = _setup_token_contract()

        def contract_factory(address, abi):
            if abi == FACTORY_ABI:
                return factory
            if abi == POOL_ABI:
                return pool
            return token

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        info = v3.get_pool_info("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                                 "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                 fee_tier=3000)

        assert isinstance(info, PoolInfo)
        assert info.pool_address == "0xPool123"
        assert info.liquidity == 5_000_000
        assert info.tick == 100
        assert info.fee == 3000

    def test_pool_not_found(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        factory = MagicMock()
        factory.functions.getPool.return_value.call.return_value = "0x0000000000000000000000000000000000000000"
        token = _setup_token_contract()

        def contract_factory(address, abi):
            if abi == FACTORY_ABI:
                return factory
            return token

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        with pytest.raises(ValueError, match="Pool does not exist"):
            v3.get_pool_info("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                              "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                              fee_tier=3000)


# ---------------------------------------------------------------------------
# UniswapV3.create_pool
# ---------------------------------------------------------------------------

class TestCreatePool:
    def test_create_pool_default_price(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        factory = _setup_factory_mock()
        token = _setup_token_contract()

        def contract_factory(address, abi):
            if abi == FACTORY_ABI:
                return factory
            return token

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        result = v3.create_pool("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                                 "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                 fee_tier=3000)

        assert result["function"] == "createPool"
        assert result["fee"] == 3000
        assert result["sqrt_price_x96"] > 0

    def test_create_pool_invalid_fee(self):
        v3 = UniswapV3(chain_manager=_mock_chain_manager())
        with pytest.raises(ValueError, match="Invalid fee tier"):
            v3.create_pool("0xA", "0xB", fee_tier=999)


# ---------------------------------------------------------------------------
# UniswapV3.swap
# ---------------------------------------------------------------------------

class TestSwap:
    def _build_v3_for_swap(self, out_decimals=6):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        quoter = _setup_quoter_mock(amount_out_raw=1500 * 10**out_decimals)
        token = _setup_token_contract(decimals=18)

        router = MagicMock()
        router.functions.exactInputSingle.return_value.build_transaction.return_value = {"dummy": "swap"}

        def contract_factory(address, abi):
            if abi == QUOTER_V2_ABI:
                return quoter
            if abi == SWAP_ROUTER_ABI:
                return router
            return token

        w3.eth.contract.side_effect = contract_factory
        return UniswapV3(chain_manager=cm), w3, router

    def test_swap_returns_v3_result(self):
        v3, w3, router = self._build_v3_for_swap()
        result = v3.swap("0xTokenIn", "0xTokenOut", 1.0, fee_tier=3000)
        assert isinstance(result, V3SwapResult)
        assert result.fee_tier == 3000
        assert result.amount_in == 1.0

    def test_swap_invalid_fee_tier(self):
        v3 = UniswapV3(chain_manager=_mock_chain_manager())
        with pytest.raises(ValueError, match="Invalid fee tier"):
            v3.swap("0xA", "0xB", 1.0, fee_tier=999)


# ---------------------------------------------------------------------------
# UniswapV3.swap_with_wallet
# ---------------------------------------------------------------------------

class TestSwapWithWallet:
    def test_swap_eth_for_tokens(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        quoter = _setup_quoter_mock(amount_out_raw=1500 * 10**6)
        token = _setup_token_contract(decimals=18)

        router = MagicMock()
        router.functions.exactInputSingle.return_value.build_transaction.return_value = {"dummy": "swap"}

        def contract_factory(address, abi):
            if abi == QUOTER_V2_ABI:
                return quoter
            if abi == SWAP_ROUTER_ABI:
                return router
            return token

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        result = v3.swap_with_wallet(wallet, "ETH", "0xTokenOut", 0.1, fee_tier=3000)

        assert isinstance(result, V3SwapResult)
        assert result.tx_hash == "0xabc123"
        assert result.gas_used == 200_000
        router.functions.exactInputSingle.assert_called_once()

    def test_swap_token_for_token_with_approval(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        quoter = _setup_quoter_mock(amount_out_raw=999 * 10**6)
        token = _setup_token_contract(decimals=6)
        token.functions.allowance.return_value.call.return_value = 0  # needs approval

        router = MagicMock()
        router.functions.exactInputSingle.return_value.build_transaction.return_value = {"dummy": "swap"}

        def contract_factory(address, abi):
            if abi == QUOTER_V2_ABI:
                return quoter
            if abi == SWAP_ROUTER_ABI:
                return router
            return token

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        result = v3.swap_with_wallet(wallet, "0xTokenIn", "0xTokenOut", 100.0, fee_tier=3000)

        assert isinstance(result, V3SwapResult)
        assert result.tx_hash == "0xabc123"
        # Should have sent approval tx + swap tx
        assert w3.eth.send_raw_transaction.call_count == 2


# ---------------------------------------------------------------------------
# UniswapV3.swap_exact_output
# ---------------------------------------------------------------------------

class TestSwapExactOutput:
    def test_returns_params(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        token = _setup_token_contract(decimals=6)

        def contract_factory(address, abi):
            return token

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        result = v3.swap_exact_output("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                                       "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                       100.0, fee_tier=3000,
                                       amount_in_max=200.0,
                                       recipient="0x1234567890123456789012345678901234567890")

        assert result["function"] == "exactOutputSingle"
        assert result["params"]["fee"] == 3000
        assert result["params"]["amountOut"] == 100 * 10**6

    def test_invalid_fee_tier(self):
        v3 = UniswapV3(chain_manager=_mock_chain_manager())
        with pytest.raises(ValueError, match="Invalid fee tier"):
            v3.swap_exact_output("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                                  "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                  100.0, fee_tier=999,
                                  amount_in_max=200.0,
                                  recipient="0x1234567890123456789012345678901234567890")


# ---------------------------------------------------------------------------
# UniswapV3.mint_position
# ---------------------------------------------------------------------------

class TestMintPosition:
    def test_mint_basic(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        nfp = _setup_nfp_mock()
        token = _setup_token_contract(decimals=18)

        def contract_factory(address, abi):
            if abi == NONFUNGIBLE_POSITION_MANAGER_ABI:
                return nfp
            return token

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm, slippage=0.5)
        result = v3.mint_position("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                                   "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                   3000, -600, 600, 1.0, 1500.0)

        assert result["function"] == "mint"
        assert result["params"]["fee"] == 3000
        assert result["params"]["tickLower"] == -600
        assert result["params"]["tickUpper"] == 600


# ---------------------------------------------------------------------------
# UniswapV3.increase_liquidity
# ---------------------------------------------------------------------------

class TestIncreaseLiquidity:
    def test_increase_basic(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        nfp = _setup_nfp_mock()
        token = _setup_token_contract(decimals=18)

        def contract_factory(address, abi):
            if abi == NONFUNGIBLE_POSITION_MANAGER_ABI:
                return nfp
            return token

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        result = v3.increase_liquidity(token_id=1, amount0=0.5, amount1=750.0)

        assert result["function"] == "increaseLiquidity"
        assert result["params"]["tokenId"] == 1


# ---------------------------------------------------------------------------
# UniswapV3.decrease_liquidity
# ---------------------------------------------------------------------------

class TestDecreaseLiquidity:
    def test_decrease_basic(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        nfp = _setup_nfp_mock()

        def contract_factory(address, abi):
            if abi == NONFUNGIBLE_POSITION_MANAGER_ABI:
                return nfp
            return MagicMock()

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        result = v3.decrease_liquidity(token_id=1, liquidity=100_000, amount0_min=0, amount1_min=0)

        assert result["function"] == "decreaseLiquidity"
        assert result["params"]["tokenId"] == 1
        assert result["params"]["liquidity"] == 100_000


# ---------------------------------------------------------------------------
# UniswapV3.collect_fees
# ---------------------------------------------------------------------------

class TestCollectFees:
    def test_collect_basic(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        nfp = _setup_nfp_mock()

        def contract_factory(address, abi):
            if abi == NONFUNGIBLE_POSITION_MANAGER_ABI:
                return nfp
            return MagicMock()

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        result = v3.collect_fees(token_id=1)

        assert result["function"] == "collect"
        assert result["params"]["tokenId"] == 1
        assert result["tokens_owed0"] == 100 * 10**6
        assert result["tokens_owed1"] == 50 * 10**18


# ---------------------------------------------------------------------------
# _sort_tokens
# ---------------------------------------------------------------------------

class TestSortTokens:
    def test_already_sorted(self):
        a = "0x0000000000000000000000000000000000000001"
        b = "0x0000000000000000000000000000000000000002"
        assert UniswapV3._sort_tokens(a, b) == (a, b)

    def test_reverse_sorted(self):
        a = "0x0000000000000000000000000000000000000002"
        b = "0x0000000000000000000000000000000000000001"
        assert UniswapV3._sort_tokens(a, b) == (b, a)
