"""Comprehensive tests for Aave, Curve, and UniswapV3 DeFi modules."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from web3_agent_kit.defi import (
    Aave,
    Curve,
    UniswapV3,
    SwapResult,
    YieldOpportunity,
    AaveUserData,
    AaveReserveData,
    CurvePoolInfo,
    V3SwapResult,
    PoolInfo,
    PositionInfo,
    AAVE_POOL_ABI,
    AAVE_RATE_MODE_VARIABLE,
    AAVE_RATE_MODE_STABLE,
    CURVE_POOL_ABI,
    ERC20_ABI,
    NATIVE,
    WETH,
    FEE_TIERS,
    SWAP_ROUTER,
    SWAP_ROUTER_02,
    QUOTER_V2,
    NONFUNGIBLE_POSITION_MANAGER,
    FACTORY,
)
from web3_agent_kit.defi.uniswap_v3 import (
    MIN_TICK,
    MAX_TICK,
    get_sqrt_ratio_at_tick,
    get_tick_at_sqrt_ratio,
    nearest_usable_tick,
    SWAP_ROUTER_ABI,
    QUOTER_V2_ABI,
    FACTORY_ABI,
    POOL_ABI,
    NONFUNGIBLE_POSITION_MANAGER_ABI,
)
from web3_agent_kit.chains.chain import Chain, ChainManager, CHAIN_IDS
from web3_agent_kit.wallet.wallet import Wallet


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
    w = MagicMock(spec=Wallet)
    w.address = "0xDeadBeef00000000000000000000000000000000"
    w.sign_transaction.return_value = b"signed_tx_bytes"
    return w


def _setup_token_contract(w3, decimals=18):
    """Return a mock ERC20 contract."""
    token_contract = MagicMock()
    token_contract.functions.decimals.return_value.call.return_value = decimals
    token_contract.functions.allowance.return_value.call.return_value = 2**256 - 1
    token_contract.functions.approve.return_value.build_transaction.return_value = {"dummy": "approve"}
    return token_contract


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


# ===========================================================================
# Aave V3 Tests
# ===========================================================================


class TestAaveBasics:
    """Basic Aave class properties."""

    def test_name(self):
        assert Aave.name == "aave"

    def test_supported_chains(self):
        assert Chain.ETHEREUM in Aave.supported_chains
        assert Chain.BASE in Aave.supported_chains
        assert Chain.ARBITRUM in Aave.supported_chains
        assert Chain.OPTIMISM in Aave.supported_chains
        assert Chain.POLYGON in Aave.supported_chains

    def test_pool_addresses_defined(self):
        aave = Aave()
        for chain in Aave.supported_chains:
            assert chain in aave.POOL_ADDRESSES

    def test_pool_address_ethereum(self):
        aave = Aave()
        assert aave.POOL_ADDRESSES[Chain.ETHEREUM] == "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"

    def test_abis_parsed(self):
        assert isinstance(AAVE_POOL_ABI, list)
        assert len(AAVE_POOL_ABI) > 0

    def test_rate_modes(self):
        assert AAVE_RATE_MODE_VARIABLE == 2
        assert AAVE_RATE_MODE_STABLE == 1


class TestAaveExecute:
    """Test Aave.execute dispatching."""

    def test_execute_supply_dispatches(self):
        aave = Aave(chain_manager=_mock_chain_manager())
        aave.supply = MagicMock(return_value={"tx_hash": "0x1"})
        result = aave.execute(_mock_wallet(), "supply", asset="0xToken", amount=1.0)
        aave.supply.assert_called_once()
        assert result["tx_hash"] == "0x1"

    def test_execute_withdraw_dispatches(self):
        aave = Aave(chain_manager=_mock_chain_manager())
        aave.withdraw = MagicMock(return_value={"tx_hash": "0x2"})
        result = aave.execute(_mock_wallet(), "withdraw", asset="0xToken", amount=1.0)
        aave.withdraw.assert_called_once()

    def test_execute_borrow_dispatches(self):
        aave = Aave(chain_manager=_mock_chain_manager())
        aave.borrow = MagicMock(return_value={"tx_hash": "0x3"})
        result = aave.execute(_mock_wallet(), "borrow", asset="0xToken", amount=1.0)
        aave.borrow.assert_called_once()

    def test_execute_repay_dispatches(self):
        aave = Aave(chain_manager=_mock_chain_manager())
        aave.repay = MagicMock(return_value={"tx_hash": "0x4"})
        result = aave.execute(_mock_wallet(), "repay", asset="0xToken", amount=1.0)
        aave.repay.assert_called_once()

    def test_execute_unknown_action_raises(self):
        aave = Aave(chain_manager=_mock_chain_manager())
        with pytest.raises(ValueError, match="Unknown Aave action"):
            aave.execute(_mock_wallet(), "liquidate")

    def test_no_chain_manager_raises(self):
        aave = Aave()
        with pytest.raises(ValueError, match="ChainManager required"):
            aave.execute(_mock_wallet(), "supply", asset="0xToken", amount=1.0)

    def test_unsupported_chain_raises(self):
        aave = Aave(chain_manager=_mock_chain_manager())
        with pytest.raises(ValueError, match="not supported"):
            aave.execute(_mock_wallet(), "supply", asset="0xToken", amount=1.0, chain=Chain.SOLANA)


class TestAaveSupply:
    """Test Aave.supply method."""

    def _prepare_aave(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        pool_contract = MagicMock()
        pool_contract.functions.supply.return_value.build_transaction.return_value = {"dummy": "supply"}

        token_contract = _setup_token_contract(w3, decimals=6)

        def contract_factory(address, abi):
            if abi == AAVE_POOL_ABI:
                return pool_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        return Aave(chain_manager=cm), wallet, w3, pool_contract

    def test_supply_token(self):
        aave, wallet, w3, pool = self._prepare_aave()
        result = aave.supply(wallet, "0xUSDC", 100.0, chain=Chain.ETHEREUM)

        assert result["tx_hash"] == "0xabc123"
        assert result["gas_used"] == 200_000
        assert result["chain"] == "ethereum"
        pool.functions.supply.assert_called_once()

    def test_supply_native_eth_raises(self):
        aave, wallet, w3, pool = self._prepare_aave()
        with pytest.raises(ValueError, match="wrapping to WETH"):
            aave.supply(wallet, "ETH", 1.0, chain=Chain.ETHEREUM)

    def test_supply_on_other_chains(self):
        aave, wallet, w3, pool = self._prepare_aave()
        for chain in [Chain.BASE, Chain.ARBITRUM, Chain.OPTIMISM, Chain.POLYGON]:
            pool.functions.supply.reset_mock()
            result = aave.supply(wallet, "0xToken", 10.0, chain=chain)
            assert result["chain"] == chain.value
            pool.functions.supply.assert_called_once()


class TestAaveWithdraw:
    """Test Aave.withdraw method."""

    def _prepare_aave(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        pool_contract = MagicMock()
        pool_contract.functions.withdraw.return_value.build_transaction.return_value = {"dummy": "withdraw"}

        token_contract = _setup_token_contract(w3, decimals=18)

        def contract_factory(address, abi):
            if abi == AAVE_POOL_ABI:
                return pool_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        return Aave(chain_manager=cm), wallet, w3, pool_contract

    def test_withdraw_amount(self):
        aave, wallet, w3, pool = self._prepare_aave()
        result = aave.withdraw(wallet, "0xWETH", 1.5, chain=Chain.ETHEREUM)
        assert result["tx_hash"] == "0xabc123"
        pool.functions.withdraw.assert_called_once()

    def test_withdraw_max(self):
        aave, wallet, w3, pool = self._prepare_aave()
        result = aave.withdraw(wallet, "0xWETH", float('inf'), chain=Chain.ETHEREUM)
        assert result["tx_hash"] == "0xabc123"
        # Should use max uint256
        call_args = pool.functions.withdraw.call_args
        assert call_args[0][1] == 2**256 - 1

    def test_withdraw_negative_uses_max(self):
        aave, wallet, w3, pool = self._prepare_aave()
        result = aave.withdraw(wallet, "0xWETH", -1, chain=Chain.ETHEREUM)
        call_args = pool.functions.withdraw.call_args
        assert call_args[0][1] == 2**256 - 1


class TestAaveBorrow:
    """Test Aave.borrow method."""

    def _prepare_aave(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        pool_contract = MagicMock()
        pool_contract.functions.borrow.return_value.build_transaction.return_value = {"dummy": "borrow"}

        token_contract = _setup_token_contract(w3, decimals=6)

        def contract_factory(address, abi):
            if abi == AAVE_POOL_ABI:
                return pool_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        return Aave(chain_manager=cm), wallet, w3, pool_contract

    def test_borrow_variable_rate(self):
        aave, wallet, w3, pool = self._prepare_aave()
        result = aave.borrow(wallet, "0xUSDC", 500.0, rate_mode="variable", chain=Chain.ETHEREUM)
        assert result["tx_hash"] == "0xabc123"
        pool.functions.borrow.assert_called_once()
        call_args = pool.functions.borrow.call_args[0]
        assert call_args[2] == AAVE_RATE_MODE_VARIABLE

    def test_borrow_stable_rate(self):
        aave, wallet, w3, pool = self._prepare_aave()
        result = aave.borrow(wallet, "0xUSDC", 500.0, rate_mode="stable", chain=Chain.ETHEREUM)
        call_args = pool.functions.borrow.call_args[0]
        assert call_args[2] == AAVE_RATE_MODE_STABLE


class TestAaveRepay:
    """Test Aave.repay method."""

    def _prepare_aave(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        pool_contract = MagicMock()
        pool_contract.functions.repay.return_value.build_transaction.return_value = {"dummy": "repay"}

        token_contract = _setup_token_contract(w3, decimals=6)

        def contract_factory(address, abi):
            if abi == AAVE_POOL_ABI:
                return pool_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        return Aave(chain_manager=cm), wallet, w3, pool_contract

    def test_repay_amount(self):
        aave, wallet, w3, pool = self._prepare_aave()
        result = aave.repay(wallet, "0xUSDC", 500.0, rate_mode="variable", chain=Chain.ETHEREUM)
        assert result["tx_hash"] == "0xabc123"
        pool.functions.repay.assert_called_once()

    def test_repay_max(self):
        aave, wallet, w3, pool = self._prepare_aave()
        result = aave.repay(wallet, "0xUSDC", -1, rate_mode="variable", chain=Chain.ETHEREUM)
        call_args = pool.functions.repay.call_args[0]
        assert call_args[1] == 2**256 - 1

    def test_repay_stable_mode(self):
        aave, wallet, w3, pool = self._prepare_aave()
        aave.repay(wallet, "0xUSDC", 100.0, rate_mode="stable", chain=Chain.ETHEREUM)
        call_args = pool.functions.repay.call_args[0]
        assert call_args[2] == AAVE_RATE_MODE_STABLE


class TestAaveGetUserData:
    """Test Aave.get_user_data method."""

    def test_get_user_data_success(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        pool_contract = MagicMock()
        pool_contract.functions.getUserAccountData.return_value.call.return_value = (
            10_000_000_000,    # 100 USD collateral (8 decimals)
            5_000_000_000,     # 50 USD debt
            3_000_000_000,     # 30 USD available
            8500,              # 85% liquidation threshold
            8000,              # 80% LTV
            2 * 10**18,        # health factor = 2.0
        )

        def contract_factory(address, abi):
            return pool_contract

        w3.eth.contract.side_effect = contract_factory
        aave = Aave(chain_manager=cm)

        data = aave.get_user_data("0xUser", chain=Chain.ETHEREUM)

        assert isinstance(data, AaveUserData)
        assert data.total_collateral_eth == 100.0
        assert data.total_debt_eth == 50.0
        assert data.available_borrows_eth == 30.0
        assert data.current_liquidation_threshold == pytest.approx(0.85)
        assert data.ltv == pytest.approx(0.80)
        assert data.health_factor == pytest.approx(2.0)

    def test_get_user_data_zero_health_factor(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        pool_contract = MagicMock()
        pool_contract.functions.getUserAccountData.return_value.call.return_value = (0, 0, 0, 0, 0, 0)

        w3.eth.contract.return_value = pool_contract
        aave = Aave(chain_manager=cm)

        data = aave.get_user_data("0xUser", chain=Chain.ETHEREUM)
        assert data.health_factor == float('inf')

    def test_get_user_data_rpc_failure_returns_defaults(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        pool_contract = MagicMock()
        pool_contract.functions.getUserAccountData.return_value.call.side_effect = ConnectionError("RPC down")

        w3.eth.contract.return_value = pool_contract
        aave = Aave(chain_manager=cm)

        data = aave.get_user_data("0xUser", chain=Chain.ETHEREUM)
        assert data.total_collateral_eth == 0.0
        assert data.health_factor == float('inf')

    def test_get_user_data_no_chain_manager(self):
        aave = Aave()
        data = aave.get_user_data("0xUser", chain=Chain.ETHEREUM)
        assert isinstance(data, AaveUserData)
        assert data.total_collateral_eth == 0.0
        assert data.health_factor == float('inf')


class TestAaveGetReserveData:
    """Test Aave.get_reserve_data method."""

    def test_get_reserve_data_success(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        pool_contract = MagicMock()

        config_data = 8500 | (8500 << 16)  # LTV=8500 in bits 0-15, LT=8500 in bits 16-31

        ray = 10 ** 27
        supply_rate_ray = int(ray * 0.034)
        variable_rate_ray = int(ray * 0.05)
        stable_rate_ray = int(ray * 0.06)

        reserve_tuple = (
            (config_data,),  # configuration (nested tuple)
            1 * 10**27,  # liquidityIndex
            supply_rate_ray,  # currentLiquidityRate
            1 * 10**27,  # variableBorrowIndex
            variable_rate_ray,  # currentVariableBorrowRate
            stable_rate_ray,  # currentStableBorrowRate
            1700000000,  # lastUpdateTimestamp
            1,  # id
            "0xaToken",  # aTokenAddress
            "0xStableDebt",  # stableDebtTokenAddress
            "0xVariableDebt",  # variableDebtTokenAddress
            "0xStrategy",  # interestRateStrategyAddress
            0,  # accruedToTreasury
            0,  # unbacked
            0,  # isolationModeTotalDebt
        )

        pool_contract.functions.getReserveData.return_value.call.return_value = reserve_tuple

        def contract_factory(address, abi):
            return pool_contract

        w3.eth.contract.side_effect = contract_factory
        aave = Aave(chain_manager=cm)

        data = aave.get_reserve_data("0xUSDC", chain=Chain.ETHEREUM)

        assert isinstance(data, AaveReserveData)
        assert data.asset == "0xUSDC"
        assert data.supply_apy > 0
        assert data.variable_borrow_apy > 0
        assert data.stable_borrow_apy > 0
        assert 0 < data.ltv <= 1.0
        assert 0 < data.liquidation_threshold <= 1.0

    def test_get_reserve_data_rpc_failure_returns_fallback(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        pool_contract = MagicMock()
        pool_contract.functions.getReserveData.return_value.call.side_effect = ConnectionError("RPC down")

        w3.eth.contract.return_value = pool_contract
        aave = Aave(chain_manager=cm)

        data = aave.get_reserve_data("0xUSDC", chain=Chain.ETHEREUM)
        assert data.supply_apy == 3.5  # fallback value
        assert data.variable_borrow_apy == 5.2
        assert data.ltv == 0.80

    def test_get_reserve_data_unsupported_chain(self):
        aave = Aave(chain_manager=_mock_chain_manager())
        with pytest.raises(ValueError, match="not supported"):
            aave.get_reserve_data("0xUSDC", chain=Chain.SOLANA)


class TestAaveGetYieldOpportunities:
    """Test Aave.get_yield_opportunities method."""

    def test_returns_opportunities(self):
        aave = Aave(chain_manager=_mock_chain_manager())
        aave.get_reserve_data = MagicMock(return_value=AaveReserveData(
            asset="0xToken",
            supply_apy=4.5,
            variable_borrow_apy=6.0,
            stable_borrow_apy=7.0,
            ltv=0.80,
            liquidation_threshold=0.85,
            total_supply=0.0,
            total_variable_debt=0.0,
            total_stable_debt=0.0,
        ))

        opps = aave.get_yield_opportunities(Chain.ETHEREUM)
        assert len(opps) > 0
        assert all(isinstance(o, YieldOpportunity) for o in opps)
        assert opps[0].protocol == "aave-v3"
        assert opps[0].apy == 4.5

    def test_skips_failed_assets(self):
        aave = Aave(chain_manager=_mock_chain_manager())
        aave.get_reserve_data = MagicMock(side_effect=ConnectionError("fail"))
        opps = aave.get_yield_opportunities(Chain.ETHEREUM)
        assert len(opps) == 0


class TestAaveDataClasses:
    """Test Aave-related data classes."""

    def test_aave_user_data(self):
        data = AaveUserData(
            total_collateral_eth=100.0,
            total_debt_eth=50.0,
            available_borrows_eth=30.0,
            current_liquidation_threshold=0.85,
            ltv=0.80,
            health_factor=2.0,
        )
        assert data.health_factor == 2.0
        assert data.total_collateral_eth == 100.0

    def test_aave_reserve_data(self):
        data = AaveReserveData(
            asset="0xUSDC",
            supply_apy=3.5,
            variable_borrow_apy=5.2,
            stable_borrow_apy=6.0,
            ltv=0.80,
            liquidation_threshold=0.85,
            total_supply=1000000.0,
            total_variable_debt=500000.0,
            total_stable_debt=100000.0,
        )
        assert data.supply_apy == 3.5
        assert data.ltv == 0.80

    def test_aave_user_data_fields(self):
        data = AaveUserData(10.0, 5.0, 3.0, 0.85, 0.80, 1.5)
        assert data.total_collateral_eth == 10.0
        assert data.total_debt_eth == 5.0
        assert data.available_borrows_eth == 3.0
        assert data.current_liquidation_threshold == 0.85
        assert data.ltv == 0.80
        assert data.health_factor == 1.5

    def test_aave_reserve_data_fields(self):
        data = AaveReserveData("0xToken", 4.0, 6.0, 7.0, 0.75, 0.80, 1e6, 5e5, 1e5)
        assert data.asset == "0xToken"
        assert data.total_supply == 1e6
        assert data.total_variable_debt == 5e5
        assert data.total_stable_debt == 1e5


# ===========================================================================
# Curve Finance Tests
# ===========================================================================


class TestCurveBasics:
    """Basic Curve class properties."""

    def test_name(self):
        assert Curve.name == "curve"

    def test_supported_chains(self):
        assert Chain.ETHEREUM in Curve.supported_chains
        assert Chain.ARBITRUM in Curve.supported_chains
        assert Chain.POLYGON in Curve.supported_chains
        assert Chain.BASE in Curve.supported_chains
        assert Chain.OPTIMISM in Curve.supported_chains

    def test_abi_parsed(self):
        assert isinstance(CURVE_POOL_ABI, list)
        assert len(CURVE_POOL_ABI) > 0


class TestCurveExecute:
    """Test Curve.execute dispatching."""

    def test_execute_calls_swap(self):
        curve = Curve(chain_manager=_mock_chain_manager())
        curve.swap = MagicMock(return_value=SwapResult(
            tx_hash="0x1", token_in="0xA", token_out="0xB",
            amount_in=1.0, amount_out=1.0, gas_used=100000, chain=Chain.ETHEREUM
        ))
        result = curve.execute(
            _mock_wallet(), "0xPool", "0xA", "0xB", 1.0, chain=Chain.ETHEREUM
        )
        curve.swap.assert_called_once()
        assert isinstance(result, SwapResult)

    def test_no_chain_manager_raises(self):
        curve = Curve()
        with pytest.raises(ValueError, match="ChainManager required"):
            curve.execute(_mock_wallet(), "0xPool", "0xA", "0xB", 1.0)

    def test_unsupported_chain_raises(self):
        curve = Curve(chain_manager=_mock_chain_manager())
        with pytest.raises(ValueError, match="not supported"):
            curve.execute(_mock_wallet(), "0xPool", "0xA", "0xB", 1.0, chain=Chain.SOLANA)


class TestCurveSwap:
    """Test Curve.swap method."""

    def _prepare_curve(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        pool_contract = MagicMock()
        _coin_map = {0: "0xTokenA", 1: "0xTokenB"}
        def _make_coin_mock(i):
            m = MagicMock()
            m.call.return_value = _coin_map.get(i, "0x0000000000000000000000000000000000000000")
            return m
        pool_contract.functions.coins.side_effect = _make_coin_mock
        pool_contract.functions.get_dy.return_value.call.return_value = 990000  # ~0.99 with 6 dec
        pool_contract.functions.exchange.return_value.build_transaction.return_value = {"dummy": "swap"}
        pool_contract.functions.fee.return_value.call.return_value = 4000000  # 0.04%

        token_contract = _setup_token_contract(w3, decimals=6)

        def contract_factory(address, abi):
            if abi == CURVE_POOL_ABI:
                return pool_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        return Curve(chain_manager=cm, slippage=0.5), wallet, w3, pool_contract

    def test_swap_basic(self):
        curve, wallet, w3, pool = self._prepare_curve()
        result = curve.swap(wallet, "0xPool", "0xTokenA", "0xTokenB", 1.0, chain=Chain.ETHEREUM)

        assert isinstance(result, SwapResult)
        assert result.tx_hash == "0xabc123"
        assert result.amount_in == 1.0
        assert result.chain == Chain.ETHEREUM
        pool.functions.exchange.assert_called_once()

    def test_swap_with_min_amount(self):
        curve, wallet, w3, pool = self._prepare_curve()
        result = curve.swap(
            wallet, "0xPool", "0xTokenA", "0xTokenB", 1.0,
            min_amount=0.98, chain=Chain.ETHEREUM
        )
        assert isinstance(result, SwapResult)

    def test_swap_token_not_in_pool_raises(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        pool_contract = MagicMock()
        def _bad_coin_mock(i):
            m = MagicMock()
            m.call.side_effect = Exception("out of range")
            return m
        pool_contract.functions.coins.side_effect = _bad_coin_mock
        pool_contract.functions.get_coins.return_value.call.return_value = [
            "0x0000000000000000000000000000000000000000"
        ] * 8

        token_contract = _setup_token_contract(w3)

        def contract_factory(address, abi):
            if abi == CURVE_POOL_ABI:
                return pool_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        curve = Curve(chain_manager=cm)

        with pytest.raises(ValueError, match="not found in Curve pool"):
            curve.swap(wallet, "0xPool", "0xMissing", "0xTokenB", 1.0)

    def test_swap_returns_correct_amounts(self):
        curve, wallet, w3, pool = self._prepare_curve()
        result = curve.swap(wallet, "0xPool", "0xTokenA", "0xTokenB", 2.0, chain=Chain.ETHEREUM)
        assert result.amount_in == 2.0
        assert result.amount_out > 0


class TestCurveGetSwapEstimate:
    """Test Curve.get_swap_estimate method."""

    def test_quote_success(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        pool_contract = MagicMock()
        _coin_map = {0: "0xTokenA", 1: "0xTokenB"}
        def _make_coin_mock(i):
            m = MagicMock()
            m.call.return_value = _coin_map.get(i, "0x0000000000000000000000000000000000000000")
            return m
        pool_contract.functions.coins.side_effect = _make_coin_mock
        pool_contract.functions.get_dy.return_value.call.return_value = 999000
        pool_contract.functions.fee.return_value.call.return_value = 4000000

        token_contract = _setup_token_contract(w3, decimals=6)

        def contract_factory(address, abi):
            if abi == CURVE_POOL_ABI:
                return pool_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        curve = Curve(chain_manager=cm)

        result = curve.get_swap_estimate("0xPool", "0xTokenA", "0xTokenB", 1.0, chain=Chain.ETHEREUM)

        assert "amount_out" in result
        assert result["amount_in"] == 1.0
        assert result["chain"] == "ethereum"
        assert "fee" in result

    def test_quote_error_returns_error_dict(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        pool_contract = MagicMock()
        pool_contract.functions.coins.side_effect = Exception("no pool")

        w3.eth.contract.return_value = pool_contract
        curve = Curve(chain_manager=cm)

        result = curve.get_swap_estimate("0xPool", "0xA", "0xB", 1.0, chain=Chain.ETHEREUM)
        assert "error" in result

    def test_quote_no_chain_manager_raises(self):
        curve = Curve()
        with pytest.raises(ValueError, match="ChainManager required"):
            curve.get_swap_estimate("0xPool", "0xA", "0xB", 1.0)

    def test_quote_price_calculation(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        pool_contract = MagicMock()
        _coin_map = {0: "0xTokenA", 1: "0xTokenB"}
        def _make_coin_mock(i):
            m = MagicMock()
            m.call.return_value = _coin_map.get(i, "0x0000000000000000000000000000000000000000")
            return m
        pool_contract.functions.coins.side_effect = _make_coin_mock
        pool_contract.functions.get_dy.return_value.call.return_value = 1000000  # exactly 1.0
        pool_contract.functions.fee.return_value.call.return_value = 4000000

        token_contract = _setup_token_contract(w3, decimals=6)

        def contract_factory(address, abi):
            if abi == CURVE_POOL_ABI:
                return pool_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        curve = Curve(chain_manager=cm)

        result = curve.get_swap_estimate("0xPool", "0xTokenA", "0xTokenB", 1.0, chain=Chain.ETHEREUM)
        assert result["price"] == pytest.approx(1.0)


class TestCurveGetPoolInfo:
    """Test Curve.get_pool_info method."""

    def test_pool_info_success(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        pool_contract = MagicMock()
        pool_contract.functions.get_coins.return_value.call.return_value = [
            "0xTokenA", "0xTokenB", "0x0000000000000000000000000000000000000000",
        ] + ["0x0000000000000000000000000000000000000000"] * 5
        pool_contract.functions.get_balances.return_value.call.return_value = [
            1_000_000 * 10**6, 1_000_000 * 10**6, 0, 0, 0, 0, 0, 0
        ]
        pool_contract.functions.fee.return_value.call.return_value = 4000000
        pool_contract.functions.A.return_value.call.return_value = 1000
        pool_contract.functions.totalSupply.return_value.call.return_value = 2_000_000 * 10**18

        token_contract = _setup_token_contract(w3, decimals=6)

        def contract_factory(address, abi):
            if abi == CURVE_POOL_ABI:
                return pool_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        curve = Curve(chain_manager=cm)

        info = curve.get_pool_info("0xPool", chain=Chain.ETHEREUM)

        assert isinstance(info, CurvePoolInfo)
        assert len(info.coins) == 2
        assert info.A == 1000

    def test_pool_info_rpc_failure_returns_fallback(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        pool_contract = MagicMock()
        pool_contract.functions.get_coins.return_value.call.side_effect = ConnectionError("RPC down")
        pool_contract.functions.get_balances.return_value.call.side_effect = ConnectionError("RPC down")
        def _fail_coin(i):
            m = MagicMock()
            m.call.side_effect = ConnectionError("RPC down")
            return m
        pool_contract.functions.coins.side_effect = _fail_coin
        pool_contract.functions.fee.return_value.call.side_effect = ConnectionError("RPC down")
        pool_contract.functions.A.return_value.call.side_effect = ConnectionError("RPC down")
        pool_contract.functions.totalSupply.return_value.call.side_effect = ConnectionError("RPC down")

        w3.eth.contract.return_value = pool_contract
        curve = Curve(chain_manager=cm)

        info = curve.get_pool_info("0xPool", chain=Chain.ETHEREUM)
        assert isinstance(info, CurvePoolInfo)
        assert info.coins == []
        assert info.fee == 0.0004


class TestCurveAddLiquidity:
    """Test Curve.add_liquidity method."""

    def _prepare_curve(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        pool_contract = MagicMock()
        # add_liquidity checks len(amounts) == len(raw_coins) so return exactly 2
        pool_contract.functions.get_coins.return_value.call.return_value = [
            "0xTokenA", "0xTokenB"
        ]
        pool_contract.functions.add_liquidity.return_value.build_transaction.return_value = {"dummy": "add_liq"}

        token_contract = _setup_token_contract(w3, decimals=6)

        def contract_factory(address, abi):
            if abi == CURVE_POOL_ABI:
                return pool_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        return Curve(chain_manager=cm), wallet, w3, pool_contract

    def test_add_liquidity_2coins(self):
        curve, wallet, w3, pool = self._prepare_curve()
        result = curve.add_liquidity(wallet, "0xPool", [1000.0, 1000.0], chain=Chain.ETHEREUM)

        assert result["tx_hash"] == "0xabc123"
        pool.functions.add_liquidity.assert_called_once()

    def test_add_liquidity_wrong_amount_count(self):
        curve, wallet, w3, pool = self._prepare_curve()
        with pytest.raises(ValueError, match="Expected 2 amounts"):
            curve.add_liquidity(wallet, "0xPool", [1000.0, 1000.0, 1000.0], chain=Chain.ETHEREUM)

    def test_add_liquidity_zero_amounts(self):
        curve, wallet, w3, pool = self._prepare_curve()
        result = curve.add_liquidity(wallet, "0xPool", [0.0, 0.0], chain=Chain.ETHEREUM)
        assert result["tx_hash"] == "0xabc123"


class TestCurveRemoveLiquidity:
    """Test Curve.remove_liquidity method."""

    def _prepare_curve(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        pool_contract = MagicMock()
        pool_contract.functions.get_coins.return_value.call.return_value = [
            "0xTokenA", "0xTokenB"
        ] + ["0x0000000000000000000000000000000000000000"] * 6
        pool_contract.functions.remove_liquidity.return_value.build_transaction.return_value = {"dummy": "rm_liq"}

        token_contract = _setup_token_contract(w3, decimals=6)

        def contract_factory(address, abi):
            if abi == CURVE_POOL_ABI:
                return pool_contract
            return token_contract

        w3.eth.contract.side_effect = contract_factory
        return Curve(chain_manager=cm), wallet, w3, pool_contract

    def test_remove_liquidity(self):
        curve, wallet, w3, pool = self._prepare_curve()
        result = curve.remove_liquidity(wallet, "0xPool", 100.0, chain=Chain.ETHEREUM)

        assert result["tx_hash"] == "0xabc123"
        pool.functions.remove_liquidity.assert_called_once()


class TestCurveDataClasses:
    """Test Curve-related data classes."""

    def test_curve_pool_info(self):
        info = CurvePoolInfo(
            pool_address="0xPool",
            coins=["0xA", "0xB"],
            balances=[100.0, 200.0],
            fee=0.0004,
            A=1000,
            total_supply=300.0,
        )
        assert info.pool_address == "0xPool"
        assert len(info.coins) == 2
        assert info.A == 1000

    def test_curve_pool_info_defaults(self):
        info = CurvePoolInfo(
            pool_address="0xEmpty",
            coins=[],
            balances=[],
            fee=0.0,
            A=0,
            total_supply=0.0,
        )
        assert info.coins == []
        assert info.total_supply == 0.0


# ===========================================================================
# UniswapV3 Tests
# ===========================================================================


class TestV3Constants:
    """Verify module-level constants and dataclasses."""

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


class TestV3DataClasses:
    """Test UniswapV3 dataclasses."""

    def test_v3_swap_result(self):
        sr = V3SwapResult(
            tx_hash="0x123", token_in="0xA", token_out="0xB",
            amount_in=1.0, amount_out=1500.0, gas_used=200_000, fee_tier=3000,
        )
        assert sr.tx_hash == "0x123"
        assert sr.fee_tier == 3000

    def test_pool_info(self):
        pi = PoolInfo(
            pool_address="0xPool", token0="0xA", token1="0xB", fee=3000,
            liquidity=1_000_000, sqrt_price_x96=79228162514264337593543950336, tick=0,
        )
        assert pi.pool_address == "0xPool"
        assert pi.liquidity == 1_000_000

    def test_position_info(self):
        pi = PositionInfo(
            token_id=1, token0="0xA", token1="0xB", fee=3000,
            tick_lower=-600, tick_upper=600, liquidity=500_000,
        )
        assert pi.token_id == 1
        assert pi.tick_lower == -600

    def test_v3_swap_result_all_fields(self):
        sr = V3SwapResult("0x1", "0xA", "0xB", 1.0, 1500.0, 150000, 500)
        assert sr.amount_in == 1.0
        assert sr.amount_out == 1500.0
        assert sr.gas_used == 150000


class TestTickMath:
    """Test tick math helpers."""

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

    def test_sqrt_ratio_symmetry(self):
        """Positive and negative ticks of same magnitude should be inverses."""
        pos = get_sqrt_ratio_at_tick(500)
        neg = get_sqrt_ratio_at_tick(-500)
        # pos * neg should be approximately 2^192
        product = pos * neg
        expected = 2**192
        assert abs(product - expected) / expected < 0.001


class TestUniswapV3Init:
    """Test UniswapV3 constructor."""

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

    def test_no_chain_manager_raises_for_w3(self):
        v3 = UniswapV3()
        with pytest.raises(ValueError, match="ChainManager required"):
            v3._get_w3()


class TestResolveToken:
    """Test UniswapV3._resolve_token and _is_native."""

    def test_native_eth(self):
        v3 = UniswapV3()
        w3 = _mock_w3()
        result = v3._resolve_token("ETH", w3)
        assert result == "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"

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

    def test_is_native(self):
        v3 = UniswapV3()
        assert v3._is_native("ETH") is True
        assert v3._is_native("eth") is True
        assert v3._is_native("NATIVE") is True
        assert v3._is_native("MATIC") is True
        assert v3._is_native("0xToken") is False

    def test_resolve_native_on_base(self):
        v3 = UniswapV3(chain=Chain.BASE)
        w3 = _mock_w3()
        result = v3._resolve_token("ETH", w3)
        assert result == WETH[Chain.BASE]


class TestSortTokens:
    """Test _sort_tokens static method."""

    def test_already_sorted(self):
        a = "0x0000000000000000000000000000000000000001"
        b = "0x0000000000000000000000000000000000000002"
        assert UniswapV3._sort_tokens(a, b) == (a, b)

    def test_reverse_sorted(self):
        a = "0x0000000000000000000000000000000000000002"
        b = "0x0000000000000000000000000000000000000001"
        assert UniswapV3._sort_tokens(a, b) == (b, a)


class TestV3GetQuote:
    """Test UniswapV3.get_quote method."""

    def _build_v3(self, decimals=6):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        quoter = _setup_quoter_mock(amount_out_raw=1500 * 10**decimals)
        token = _setup_token_contract(w3, decimals=decimals)

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
        token = _setup_token_contract(w3)

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

    def test_quote_all_fee_tiers(self):
        """Test that all valid fee tiers work in quotes."""
        for tier in [100, 500, 3000, 10000]:
            v3, w3 = self._build_v3()
            result = v3.get_quote("0xTokenIn", "0xTokenOut", 1.0, fee_tier=tier)
            assert "amount_out" in result
            assert result["fee_tier"] == tier

    def test_quote_returns_amount_out_raw_as_string(self):
        v3, w3 = self._build_v3()
        result = v3.get_quote("0xTokenIn", "0xTokenOut", 1.0, fee_tier=3000)
        assert isinstance(result["amount_out_raw"], str)


class TestV3GetPoolInfo:
    """Test UniswapV3.get_pool_info method."""

    def test_pool_info(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        factory = _setup_factory_mock("0xPool123")
        pool = _setup_pool_mock(liquidity=5_000_000, tick=100)
        token = _setup_token_contract(w3)

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
        token = _setup_token_contract(w3)

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

    def test_pool_info_no_chain_manager(self):
        v3 = UniswapV3()
        with pytest.raises(ValueError, match="ChainManager required"):
            v3.get_pool_info("0xA", "0xB", fee_tier=3000)


class TestV3Swap:
    """Test UniswapV3.swap method."""

    def _build_v3_for_swap(self, out_decimals=6):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        quoter = _setup_quoter_mock(amount_out_raw=1500 * 10**out_decimals)
        token = _setup_token_contract(w3, decimals=18)

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

    def test_swap_no_chain_manager(self):
        v3 = UniswapV3()
        with pytest.raises(ValueError, match="ChainManager required"):
            v3.swap("0xA", "0xB", 1.0, fee_tier=3000)

    def test_swap_with_custom_slippage(self):
        v3, w3, router = self._build_v3_for_swap()
        result = v3.swap("0xTokenIn", "0xTokenOut", 1.0, fee_tier=3000, slippage=1.0)
        assert isinstance(result, V3SwapResult)

    def test_swap_with_eth_input(self):
        v3, w3, router = self._build_v3_for_swap()
        result = v3.swap("ETH", "0xTokenOut", 0.1, fee_tier=3000)
        assert isinstance(result, V3SwapResult)


class TestV3SwapWithWallet:
    """Test UniswapV3.swap_with_wallet method."""

    def test_swap_eth_for_tokens(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        wallet = _mock_wallet()

        quoter = _setup_quoter_mock(amount_out_raw=1500 * 10**6)
        token = _setup_token_contract(w3, decimals=18)

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
        token = _setup_token_contract(w3, decimals=6)
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

    def test_swap_with_wallet_no_chain_manager(self):
        v3 = UniswapV3()
        wallet = _mock_wallet()
        with pytest.raises(ValueError, match="ChainManager required"):
            v3.swap_with_wallet(wallet, "0xA", "0xB", 1.0, fee_tier=3000)

    def test_swap_with_wallet_invalid_fee_tier(self):
        v3 = UniswapV3(chain_manager=_mock_chain_manager())
        wallet = _mock_wallet()
        with pytest.raises(ValueError, match="Invalid fee tier"):
            v3.swap_with_wallet(wallet, "0xA", "0xB", 1.0, fee_tier=999)


class TestV3SwapExactOutput:
    """Test UniswapV3.swap_exact_output method."""

    def test_returns_params(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)
        token = _setup_token_contract(w3, decimals=6)

        def contract_factory(address, abi):
            return token

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        result = v3.swap_exact_output("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                                       "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                       100.0, fee_tier=3000)

        assert result["function"] == "exactOutputSingle"
        assert result["params"]["fee"] == 3000
        assert result["params"]["amountOut"] == 100 * 10**6

    def test_invalid_fee_tier(self):
        v3 = UniswapV3(chain_manager=_mock_chain_manager())
        with pytest.raises(ValueError, match="Invalid fee tier"):
            v3.swap_exact_output("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                                  "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                  100.0, fee_tier=999)


class TestV3MintPosition:
    """Test UniswapV3.mint_position method."""

    def test_mint_basic(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        nfp = _setup_nfp_mock()
        token = _setup_token_contract(w3, decimals=18)

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

    def test_mint_no_chain_manager(self):
        v3 = UniswapV3()
        with pytest.raises(ValueError, match="ChainManager required"):
            v3.mint_position("0xA", "0xB", 3000, -600, 600, 1.0, 1.0)

    def test_mint_slippage_applied(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        nfp = _setup_nfp_mock()
        token = _setup_token_contract(w3, decimals=18)

        def contract_factory(address, abi):
            if abi == NONFUNGIBLE_POSITION_MANAGER_ABI:
                return nfp
            return token

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm, slippage=1.0)
        result = v3.mint_position("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                                   "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                   3000, -600, 600, 1.0, 1500.0)

        # amount0Min should be 99% of amount0Desired (1% slippage)
        assert result["params"]["amount0Min"] == int(result["params"]["amount0Desired"] * 0.99)


class TestV3IncreaseLiquidity:
    """Test UniswapV3.increase_liquidity method."""

    def test_increase_basic(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        nfp = _setup_nfp_mock()
        token = _setup_token_contract(w3, decimals=18)

        def contract_factory(address, abi):
            if abi == NONFUNGIBLE_POSITION_MANAGER_ABI:
                return nfp
            return token

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        result = v3.increase_liquidity(token_id=1, amount0=0.5, amount1=750.0)

        assert result["function"] == "increaseLiquidity"
        assert result["params"]["tokenId"] == 1

    def test_increase_no_chain_manager(self):
        v3 = UniswapV3()
        with pytest.raises(ValueError, match="ChainManager required"):
            v3.increase_liquidity(token_id=1, amount0=0.5, amount1=750.0)


class TestV3DecreaseLiquidity:
    """Test UniswapV3.decrease_liquidity method."""

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

    def test_decrease_with_min_amounts(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        nfp = _setup_nfp_mock()

        def contract_factory(address, abi):
            if abi == NONFUNGIBLE_POSITION_MANAGER_ABI:
                return nfp
            return MagicMock()

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        result = v3.decrease_liquidity(token_id=1, liquidity=50_000, amount0_min=100, amount1_min=200)

        assert result["params"]["amount0Min"] == 100
        assert result["params"]["amount1Min"] == 200


class TestV3CollectFees:
    """Test UniswapV3.collect_fees method."""

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

    def test_collect_no_chain_manager(self):
        v3 = UniswapV3()
        with pytest.raises(ValueError, match="ChainManager required"):
            v3.collect_fees(token_id=1)

    def test_collect_reads_position_data(self):
        w3 = _mock_w3()
        cm = _mock_chain_manager(w3)

        nfp = _setup_nfp_mock()
        nfp.functions.positions.return_value.call.return_value = (
            0, "0xOp", "0xT0", "0xT1", 3000, -600, 600, 500000,
            0, 0,
            999 * 10**6,   # tokensOwed0
            888 * 10**18,  # tokensOwed1
        )

        def contract_factory(address, abi):
            if abi == NONFUNGIBLE_POSITION_MANAGER_ABI:
                return nfp
            return MagicMock()

        w3.eth.contract.side_effect = contract_factory

        v3 = UniswapV3(chain_manager=cm)
        result = v3.collect_fees(token_id=42)

        assert result["tokens_owed0"] == 999 * 10**6
        assert result["tokens_owed1"] == 888 * 10**18
        assert result["params"]["amount0Max"] == 999 * 10**6
        assert result["params"]["amount1Max"] == 888 * 10**18
