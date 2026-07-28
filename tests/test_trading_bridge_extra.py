"""Extra tests for TokenSniper and BridgeAgent — mocked chain/RPC/HTTP."""

from unittest.mock import MagicMock

import pytest

from web3_agent_kit.bridge.bridge import (
    NATIVE,
    WETH,
    BridgeAgent,
    BridgeRoute,
)
from web3_agent_kit.chains.chain import Chain
from web3_agent_kit.trading.sniper import (
    FACTORIES,
    RiskLevel,
    SniperConfig,
    TokenSniper,
)

WETH_ETH = WETH[Chain.ETHEREUM]
WETH_BASE = WETH[Chain.BASE]


def _mock_w3(reserves=(10**18, 500), block_number=1000, code=b"\x60" * 2000):
    """Build a mocked web3 whose contracts return canned values."""
    w3 = MagicMock()
    w3.to_checksum_address.side_effect = lambda a: a
    w3.from_wei.side_effect = lambda wei, _: wei / 10**18
    w3.eth.block_number = block_number
    w3.eth.get_code.return_value = code

    pair_contract = MagicMock()
    pair_contract.functions.getReserves.return_value.call.return_value = list(
        reserves
    ) + [0]
    pair_contract.functions.token0.return_value.call.return_value = WETH_BASE

    token_contract = MagicMock()
    token_contract.functions.name.return_value.call.return_value = "Test Token"
    token_contract.functions.symbol.return_value.call.return_value = "TT"

    factory_contract = MagicMock()

    def _contract(address=None, abi=None):
        # Distinguish contract types by ABI content
        names = [item.get("name") for item in abi]
        if "PairCreated" in names:
            return factory_contract
        if "getReserves" in names:
            return pair_contract
        return token_contract

    w3.eth.contract.side_effect = _contract
    return w3, factory_contract, pair_contract, token_contract


class TestSniperScan:
    def test_scan_unsupported_chain(self):
        sniper = TokenSniper(MagicMock(), MagicMock())
        with pytest.raises(ValueError, match="Factory not configured"):
            sniper.scan_recent_blocks(chain=Chain.SOLANA)

    def test_scan_no_events(self):
        cm = MagicMock()
        w3, factory, _, _ = _mock_w3()
        factory.events.PairCreated.get_logs.return_value = []
        cm.get_web3.return_value = w3
        sniper = TokenSniper(cm, MagicMock())
        assert sniper.scan_recent_blocks(chain=Chain.BASE) == []

    def test_scan_with_event(self):
        cm = MagicMock()
        w3, factory, _, _ = _mock_w3(reserves=(5 * 10**18, 1000))
        event = MagicMock()
        event.args.pair = "0xPAIR"
        event.args.token0 = WETH_BASE
        event.args.token1 = "0xTOKEN"
        event.blockNumber = 999
        factory.events.PairCreated.get_logs.return_value = [event]
        cm.get_web3.return_value = w3
        sniper = TokenSniper(cm, MagicMock(), SniperConfig(auto_buy=False))
        pairs = sniper.scan_recent_blocks(chain=Chain.BASE)
        assert len(pairs) == 1
        assert pairs[0].token_symbol == "TT"
        assert pairs[0].liquidity_eth == 5.0
        assert len(sniper.detected_pairs) == 1


class TestSniperAnalyze:
    def test_analyze_skips_non_weth(self):
        cm = MagicMock()
        w3, *_ = _mock_w3()
        cm.get_web3.return_value = w3
        sniper = TokenSniper(cm, MagicMock())
        result = sniper._analyze_pair(
            "0xPAIR", "0xAAA", "0xBBB", Chain.BASE, 1
        )
        assert result is None

    def test_analyze_reserves_error(self):
        cm = MagicMock()
        w3, _, pair, _ = _mock_w3()
        pair.functions.getReserves.return_value.call.side_effect = RuntimeError(
            "boom"
        )
        cm.get_web3.return_value = w3
        sniper = TokenSniper(cm, MagicMock())
        result = sniper._analyze_pair(
            "0xPAIR", WETH_BASE, "0xTOKEN", Chain.BASE, 1
        )
        assert result is None

    def test_analyze_token_meta_fallback(self):
        cm = MagicMock()
        w3, _, _, token = _mock_w3()
        token.functions.name.return_value.call.side_effect = RuntimeError("x")
        cm.get_web3.return_value = w3
        sniper = TokenSniper(cm, MagicMock())
        result = sniper._analyze_pair(
            "0xPAIR", WETH_BASE, "0xTOKEN", Chain.BASE, 1
        )
        assert result.token_symbol == "???"
        assert result.token_name == "Unknown"

    def test_analyze_blacklisted(self):
        cm = MagicMock()
        w3, *_ = _mock_w3()
        cm.get_web3.return_value = w3
        config = SniperConfig(blacklisted_tokens=["0xTOKEN"])
        sniper = TokenSniper(cm, MagicMock(), config)
        result = sniper._analyze_pair(
            "0xPAIR", WETH_BASE, "0xTOKEN", Chain.BASE, 1
        )
        assert result is None


class TestSniperRisk:
    def _sniper(self, code=b"\x60" * 2000):
        cm = MagicMock()
        w3, *_ = _mock_w3(code=code)
        cm.get_web3.return_value = w3
        return TokenSniper(cm, MagicMock())

    def test_low_risk_high_liquidity(self):
        sniper = self._sniper()
        risk, score = sniper._assess_risk("0xT", 5.0, Chain.BASE)
        # 50 + 15 (liq) + 10 (code) + 5 (honeypot) = 80 -> LOW
        assert risk == RiskLevel.LOW
        assert score == 80.0

    def test_scam_low_liquidity_tiny_code(self):
        sniper = self._sniper(code=b"\x00" * 10)
        risk, score = sniper._assess_risk("0xT", 0.001, Chain.BASE)
        # 50 - 30 - 40 + 5 = -15 -> SCAM
        assert risk == RiskLevel.SCAM

    def test_code_fetch_error(self):
        cm = MagicMock()
        w3, *_ = _mock_w3()
        w3.eth.get_code.side_effect = RuntimeError("x")
        cm.get_web3.return_value = w3
        sniper = TokenSniper(cm, MagicMock())
        risk, score = sniper._assess_risk("0xT", 5.0, Chain.BASE)
        # 50 + 15 - 20 + 5 = 50 -> MEDIUM
        assert risk == RiskLevel.MEDIUM


class TestSniperBuy:
    def test_buy_no_uniswap(self):
        sniper = TokenSniper(MagicMock(), MagicMock())
        from web3_agent_kit.trading.sniper import NewPair
        pair = NewPair("0xP", WETH_BASE, "0xT", Chain.BASE, 0, RiskLevel.LOW)
        assert sniper.buy(pair) is None

    def test_buy_success(self):
        uni = MagicMock()
        uni.execute.return_value.tx_hash = "0xTX"
        sniper = TokenSniper(MagicMock(), MagicMock(), uniswap=uni)
        from web3_agent_kit.trading.sniper import NewPair
        pair = NewPair("0xP", WETH_BASE, "0xT", Chain.BASE, 0, RiskLevel.LOW)
        assert sniper.buy(pair) == "0xTX"

    def test_buy_failure(self):
        uni = MagicMock()
        uni.execute.side_effect = RuntimeError("swap failed")
        sniper = TokenSniper(MagicMock(), MagicMock(), uniswap=uni)
        from web3_agent_kit.trading.sniper import NewPair
        pair = NewPair("0xP", WETH_BASE, "0xT", Chain.BASE, 0, RiskLevel.LOW)
        assert sniper.buy(pair) is None

    def test_repr_lists_factories(self):
        sniper = TokenSniper(MagicMock(), MagicMock())
        r = repr(sniper)
        assert "TokenSniper" in r
        for chain in FACTORIES:
            assert chain.value in r


# ─── Bridge ──────────────────────────────────────────────────────


def _bridge(wallet_addr="0xWALLET"):
    cm = MagicMock()
    wallet = MagicMock()
    wallet.address = wallet_addr
    return BridgeAgent(cm, wallet), cm, wallet


class TestBridgeResolveDecimals:
    def test_resolve_native(self):
        agent, *_ = _bridge()
        assert agent._resolve_token("ETH", Chain.ETHEREUM) == NATIVE
        assert agent._resolve_token("MATIC", Chain.POLYGON) == NATIVE

    def test_resolve_weth(self):
        agent, *_ = _bridge()
        assert agent._resolve_token("WETH", Chain.BASE) == WETH_BASE

    def test_resolve_known_token(self):
        agent, *_ = _bridge()
        result = agent._resolve_token("USDC", Chain.ETHEREUM)
        assert result.startswith("0x")

    def test_resolve_unknown_returns_input(self):
        agent, *_ = _bridge()
        assert agent._resolve_token("0xCUSTOM", Chain.ETHEREUM) == "0XCUSTOM"

    def test_get_decimals_native(self):
        agent, *_ = _bridge()
        assert agent._get_decimals(NATIVE, Chain.ETHEREUM) == 18

    def test_get_decimals_token(self):
        agent, cm, _ = _bridge()
        w3 = MagicMock()
        w3.to_checksum_address.side_effect = lambda a: a
        w3.eth.contract.return_value.functions.decimals.return_value.call.return_value = 6
        cm.get_web3.return_value = w3
        assert agent._get_decimals("0xUSDC", Chain.ETHEREUM) == 6

    def test_get_decimals_error_default(self):
        agent, cm, _ = _bridge()
        w3 = MagicMock()
        w3.to_checksum_address.side_effect = lambda a: a
        w3.eth.contract.return_value.functions.decimals.return_value.call.side_effect = RuntimeError(
            "x"
        )
        cm.get_web3.return_value = w3
        assert agent._get_decimals("0xUSDC", Chain.ETHEREUM) == 18


class TestBridgeRoutes:
    def test_lifi_unsupported_chain(self):
        agent, *_ = _bridge()
        assert agent._get_lifi_routes(
            "ETH", 1.0, Chain.SOLANA, Chain.BASE
        ) == []

    def test_socket_unsupported_chain(self):
        agent, *_ = _bridge()
        assert agent._get_socket_routes(
            "ETH", 1.0, Chain.SOLANA, Chain.BASE
        ) == []

    def test_lifi_routes_parsed(self):
        agent, *_ = _bridge()
        resp = MagicMock()
        resp.json.return_value = {
            "routes": [
                {
                    "toAmount": str(99 * 10**16),
                    "tags": ["fast"],
                    "gasCostUSD": "3.5",
                    "duration": 200,
                    "steps": [],
                }
            ]
        }
        agent.session.get = MagicMock(return_value=resp)
        routes = agent._get_lifi_routes("ETH", 1.0, Chain.ETHEREUM, Chain.BASE)
        assert len(routes) == 1
        assert routes[0].bridge_name == "fast"
        assert routes[0].amount_out == 0.99

    def test_socket_routes_parsed(self):
        agent, *_ = _bridge()
        resp = MagicMock()
        resp.json.return_value = {
            "result": {
                "routes": [
                    {
                        "toAmount": str(98 * 10**16),
                        "bridgeName": "hop",
                        "gasFees": {"gasAmountUSD": "1.2"},
                        "serviceTime": 150,
                    }
                ]
            }
        }
        agent.session.get = MagicMock(return_value=resp)
        routes = agent._get_socket_routes(
            "ETH", 1.0, Chain.ETHEREUM, Chain.BASE
        )
        assert len(routes) == 1
        assert routes[0].bridge_name == "hop"
        assert routes[0].amount_out == 0.98

    def test_get_routes_aggregates_and_sorts(self):
        agent, *_ = _bridge()
        r_lo = BridgeRoute(
            "a", Chain.ETHEREUM, Chain.BASE, "0x", "0x", 1.0, 0.9, 1, 10, 1, []
        )
        r_hi = BridgeRoute(
            "b", Chain.ETHEREUM, Chain.BASE, "0x", "0x", 1.0, 0.99, 1, 10, 1, []
        )
        agent._get_lifi_routes = MagicMock(return_value=[r_lo])
        agent._get_socket_routes = MagicMock(return_value=[r_hi])
        routes = agent.get_routes("ETH", 1.0, Chain.ETHEREUM, Chain.BASE)
        assert [r.amount_out for r in routes] == [0.99, 0.9]

    def test_get_routes_handles_provider_errors(self):
        agent, *_ = _bridge()
        agent._get_lifi_routes = MagicMock(side_effect=RuntimeError("lifi down"))
        agent._get_socket_routes = MagicMock(
            side_effect=RuntimeError("socket down")
        )
        assert agent.get_routes("ETH", 1.0, Chain.ETHEREUM, Chain.BASE) == []


class TestBridgeTransfer:
    def _route(self, name):
        return BridgeRoute(
            name, Chain.ETHEREUM, Chain.BASE, NATIVE, NATIVE, 0.1, 0.099,
            2.0, 300, 2.0, [],
        )

    def test_transfer_no_routes(self):
        agent, *_ = _bridge()
        agent.get_routes = MagicMock(return_value=[])
        with pytest.raises(ValueError, match="No bridge routes"):
            agent.transfer("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)

    def test_transfer_picks_best_and_routes_lifi(self):
        agent, *_ = _bridge()
        route = self._route("Li.Fi")
        agent.get_routes = MagicMock(return_value=[route])
        agent._execute_lifi = MagicMock(return_value="lifi-result")
        assert agent.transfer(
            "ETH", 0.1, Chain.ETHEREUM, Chain.BASE
        ) == "lifi-result"

    def test_transfer_routes_socket_default(self):
        agent, *_ = _bridge()
        route = self._route("hop")
        agent._execute_socket = MagicMock(return_value="socket-result")
        assert agent.transfer(
            "ETH", 0.1, Chain.ETHEREUM, Chain.BASE, route=route
        ) == "socket-result"

    def test_execute_lifi(self):
        agent, cm, _ = _bridge()
        resp = MagicMock()
        resp.json.return_value = {
            "transactionRequest": {
                "to": "0xTO",
                "data": "0xdata",
                "value": "0",
                "gasLimit": "300000",
            }
        }
        agent.session.get = MagicMock(return_value=resp)
        w3 = MagicMock()
        w3.to_checksum_address.side_effect = lambda a: a
        w3.eth.gas_price = 10
        w3.eth.get_transaction_count.return_value = 1
        tx_hash = MagicMock()
        tx_hash.hex.return_value = "0xHASH"
        w3.eth.send_raw_transaction.return_value = tx_hash
        cm.get_web3.return_value = w3
        agent.wallet.sign_transaction.return_value = b"\xaa"
        route = self._route("Li.Fi")
        result = agent._execute_lifi(route)
        assert result.tx_hash == "0xHASH"
        assert result.bridge_name == "Li.Fi"

    def test_execute_lifi_no_tx_data(self):
        agent, *_ = _bridge()
        resp = MagicMock()
        resp.json.return_value = {}
        agent.session.get = MagicMock(return_value=resp)
        with pytest.raises(ValueError, match="No transaction data from Li.Fi"):
            agent._execute_lifi(self._route("Li.Fi"))

    def test_execute_socket(self):
        agent, cm, _ = _bridge()
        resp = MagicMock()
        resp.json.return_value = {
            "result": {
                "txData": {
                    "to": "0xTO",
                    "data": "0xdata",
                    "value": "0",
                    "gasLimit": "300000",
                }
            }
        }
        agent.session.get = MagicMock(return_value=resp)
        w3 = MagicMock()
        w3.to_checksum_address.side_effect = lambda a: a
        w3.eth.gas_price = 10
        w3.eth.get_transaction_count.return_value = 1
        tx_hash = MagicMock()
        tx_hash.hex.return_value = "0xSOCK"
        w3.eth.send_raw_transaction.return_value = tx_hash
        cm.get_web3.return_value = w3
        agent.wallet.sign_transaction.return_value = b"\xbb"
        result = agent._execute_socket(self._route("hop"))
        assert result.tx_hash == "0xSOCK"

    def test_execute_socket_no_tx_data(self):
        agent, *_ = _bridge()
        resp = MagicMock()
        resp.json.return_value = {"result": {}}
        agent.session.get = MagicMock(return_value=resp)
        with pytest.raises(ValueError, match="No transaction data from Socket"):
            agent._execute_socket(self._route("hop"))

    def test_repr(self):
        agent, *_ = _bridge()
        assert "BridgeAgent" in repr(agent)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
