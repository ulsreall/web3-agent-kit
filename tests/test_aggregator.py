"""Tests for DEX Aggregator module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from web3_agent_kit.defi.aggregator import (
    DEXAggregator,
    AggregatorConfig,
    AggregatorError,
    Chain,
    ProviderHealth,
)


@pytest.fixture
def aggregator():
    return DEXAggregator(AggregatorConfig(slippage=0.5, timeout=10, max_retries=2))


@pytest.fixture
def mock_1inch_response():
    mock = MagicMock()
    mock.json.return_value = {"toAmount": "500000000"}
    mock.raise_for_status = MagicMock()
    return mock


@pytest.fixture
def mock_paraswap_response():
    mock = MagicMock()
    mock.json.return_value = {"priceRoute": {"destAmount": "550000000"}}
    mock.raise_for_status = MagicMock()
    return mock


@pytest.fixture
def mock_0x_response():
    mock = MagicMock()
    mock.json.return_value = {"buyAmount": "480000000"}
    mock.raise_for_status = MagicMock()
    return mock


class TestAggregatorConfig:
    def test_default_config(self):
        config = AggregatorConfig()
        assert config.slippage == 0.5
        assert config.timeout == 30
        assert config.max_retries == 3
        assert config.fallback_enabled is True
        assert config.per_provider_timeout == 15

    def test_custom_config(self):
        config = AggregatorConfig(slippage=1.0, oneinch_api_key="test_key", fallback_enabled=False)
        assert config.slippage == 1.0
        assert config.oneinch_api_key == "test_key"
        assert config.fallback_enabled is False


class TestChain:
    def test_chain_enum(self):
        assert Chain.ETHEREUM.value == "ethereum"
        assert Chain.SOLANA.value == "solana"
        assert Chain.BASE.value == "base"

    def test_chain_ids(self):
        from web3_agent_kit.defi.aggregator import CHAIN_IDS
        assert CHAIN_IDS[Chain.ETHEREUM] == 1
        assert CHAIN_IDS[Chain.BSC] == 56
        assert CHAIN_IDS[Chain.POLYGON] == 137


class TestProviderHealth:
    def test_init(self):
        health = ProviderHealth()
        assert health.max_failures == 3
        assert health.cooldown == 60
        assert health.active_providers == []

    def test_record_success(self):
        health = ProviderHealth()
        health.record_success("1inch")
        assert health.active_providers == ["1inch"]

    def test_record_failure_then_disable(self):
        health = ProviderHealth(max_failures=2)
        health.record_failure("1inch")
        assert health.is_available("1inch") is True
        health.record_failure("1inch")
        assert health.is_available("1inch") is False

    def test_is_available_after_cooldown(self):
        health = ProviderHealth(max_failures=1, cooldown=0)
        health.record_failure("1inch")
        # Cooldown 0 means immediately available again
        assert health.is_available("1inch") is True

    def test_reset_all(self):
        health = ProviderHealth(max_failures=1)
        health.record_failure("1inch")
        health.record_failure("paraswap")
        health.reset()
        assert health.is_available("1inch") is True
        assert health.is_available("paraswap") is True

    def test_reset_single(self):
        health = ProviderHealth(max_failures=1)
        health.record_failure("1inch")
        health.record_failure("paraswap")
        health.reset("1inch")
        assert health.is_available("1inch") is True
        assert health.is_available("paraswap") is False

    def test_status(self):
        health = ProviderHealth(max_failures=1)
        health.record_failure("1inch")
        health.record_success("paraswap")
        status = health.status
        assert status["1inch"] == "disabled"
        assert status["paraswap"] == "active"


class TestDEXAggregator:
    def test_init(self, aggregator):
        assert aggregator.config.slippage == 0.5
        assert aggregator._client is None
        assert aggregator._health is not None

    @pytest.mark.asyncio
    async def test_oneinch_quote(self, aggregator, mock_1inch_response):
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_1inch_response)):
            quote = await aggregator.oneinch_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "1000000000000000000",
            )
            assert "toAmount" in quote

    @pytest.mark.asyncio
    async def test_oneinch_swap(self, aggregator):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tx": {"data": "0x...", "to": "0x...", "value": "0"},
            "toAmount": "500000000",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            swap = await aggregator.oneinch_swap(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "1000000000000000000",
                "0x1234567890123456789012345678901234567890",
            )
            assert "tx" in swap

    @pytest.mark.asyncio
    async def test_paraswap_quote(self, aggregator, mock_paraswap_response):
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_paraswap_response)):
            quote = await aggregator.paraswap_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "1000000000000000000",
                "0x1234567890123456789012345678901234567890",
            )
            assert "priceRoute" in quote

    @pytest.mark.asyncio
    async def test_zeroex_quote(self, aggregator, mock_0x_response):
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_0x_response)):
            quote = await aggregator.zeroex_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "1000000000000000000",
                "0x1234567890123456789012345678901234567890",
            )
            assert quote["buyAmount"] == "480000000"

    @pytest.mark.asyncio
    async def test_get_best_quote_evm(self, aggregator, mock_1inch_response, mock_paraswap_response, mock_0x_response):
        """Test best quote aggregation across all EVM providers."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = [mock_1inch_response, mock_paraswap_response, mock_0x_response]

            result = await aggregator.get_best_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                1000000000000000000,
            )
            assert result["best_provider"] == "paraswap"
            assert result["amount_out"] == "550000000"
            assert "fallback_used" in result

    @pytest.mark.asyncio
    async def test_get_best_quote_solana(self, aggregator):
        """Test that Solana routes to Jupiter."""
        mock_jupiter = MagicMock()
        mock_jupiter.json.return_value = {
            "inAmount": "1000000000",
            "outAmount": "23000",
            "priceImpactPct": "0.01",
            "routePlan": [],
        }
        mock_jupiter.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_jupiter)):
            result = await aggregator.get_best_quote(
                Chain.SOLANA,
                "So11111111111111111111111111111111111111112",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                1000000000,
            )
            assert result["best_provider"] == "jupiter"
            assert "fallback_used" in result

    @pytest.mark.asyncio
    async def test_get_best_quote_partial_failure(self, aggregator):
        """Test that one provider failing doesn't break the whole aggregation."""
        mock_1inch = MagicMock()
        mock_1inch.json.return_value = {"toAmount": "500000000"}
        mock_1inch.raise_for_status = MagicMock()

        # Paraswap raises an error
        mock_paraswap = MagicMock()
        mock_paraswap.json.side_effect = Exception("Paraswap API error")
        mock_paraswap.raise_for_status = MagicMock()

        mock_0x = MagicMock()
        mock_0x.json.return_value = {"buyAmount": "480000000"}
        mock_0x.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = [mock_1inch, mock_paraswap, mock_0x]

            result = await aggregator.get_best_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                1000000000000000000,
            )
            # Should still return a result with 1inch winning
            assert result["best_provider"] == "1inch"
            assert result["amount_out"] == "500000000"
            assert "error" in result["quotes"]["paraswap"]

    @pytest.mark.asyncio
    async def test_get_best_quote_all_fail_then_fallback(self, aggregator):
        """Test fallback routing when all providers fail."""
        # All providers fail initially
        mock_all = MagicMock()
        mock_all.json.side_effect = Exception("API error")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = [mock_all, mock_all, mock_all]

            result = await aggregator.get_best_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                1000000000000000000,
            )
            # All providers should have failed
            assert result["best_provider"] is None
            assert result["amount_out"] == "0"

    @pytest.mark.asyncio
    async def test_get_best_quote_handles_zero_output(self, aggregator):
        """Test that zero output amounts are handled gracefully."""
        mock_1inch = MagicMock()
        mock_1inch.json.return_value = {"toAmount": "0"}
        mock_1inch.raise_for_status = MagicMock()

        mock_paraswap = MagicMock()
        mock_paraswap.json.return_value = {"priceRoute": {"destAmount": "0"}}
        mock_paraswap.raise_for_status = MagicMock()

        mock_0x = MagicMock()
        mock_0x.json.return_value = {"buyAmount": "0"}
        mock_0x.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = [mock_1inch, mock_paraswap, mock_0x]

            result = await aggregator.get_best_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                1000000000000000000,
            )
            # All zero amounts — last provider wins with >= comparison
            assert result["best_provider"] == "0x"
            assert result["amount_out"] == "0"

    @pytest.mark.asyncio
    async def test_extract_output_amount(self, aggregator):
        assert aggregator._extract_output_amount("1inch", {"toAmount": "1000"}) == 1000
        assert aggregator._extract_output_amount("paraswap", {"priceRoute": {"destAmount": "2000"}}) == 2000
        assert aggregator._extract_output_amount("0x", {"buyAmount": "3000"}) == 3000
        assert aggregator._extract_output_amount("jupiter", {"outAmount": "4000"}) == 4000
        assert aggregator._extract_output_amount("unknown", {}) == 0

    @pytest.mark.asyncio
    async def test_close(self, aggregator):
        mock_client = AsyncMock()
        aggregator._client = mock_client
        await aggregator.close()
        mock_client.aclose.assert_called_once()
        assert aggregator._client is None

    @pytest.mark.asyncio
    async def test_oneinch_quote_with_api_key(self):
        agg = DEXAggregator(AggregatorConfig(oneinch_api_key="test-key-123"))
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"toAmount": "1000000"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            quote = await agg.oneinch_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "1000000000000000000",
            )
            assert quote["toAmount"] == "1000000"

    @pytest.mark.asyncio
    async def test_get_swap_evm_with_preferred_provider(self, aggregator):
        """Test swap with a preferred provider."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "tx": {"data": "0x...", "to": "0x..."},
            "toAmount": "500000000",
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_resp)):
            result = await aggregator.get_swap(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                1000000000000000000,
                "0x1234567890123456789012345678901234567890",
                preferred_provider="1inch",
            )
            assert "tx" in result

    @pytest.mark.asyncio
    async def test_get_swap_solana(self, aggregator):
        """Test Solana swap via Jupiter."""
        with patch("web3_agent_kit.solana.dex.JupiterDEX") as mock_jup_cls:
            mock_jup = AsyncMock()
            mock_jup.swap.return_value = {"swapTransaction": "base64_tx", "lastValidBlockHeight": 200000}
            mock_jup_cls.return_value = mock_jup

            result = await aggregator.get_swap(
                Chain.SOLANA,
                "So11111111111111111111111111111111111111112",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                1000000000,
                "wallet_address",
            )
            assert "swapTransaction" in result

    @pytest.mark.asyncio
    async def test_get_swap_unknown_provider(self, aggregator):
        result = await aggregator.get_swap(
            Chain.ETHEREUM,
            "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            1000000000000000000,
            "0x1234567890123456789012345678901234567890",
            preferred_provider="unknown",
        )
        # Should fall back to get_best_quote first, then get error
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_provider_health(self, aggregator):
        assert isinstance(aggregator.get_provider_health(), dict)

    @pytest.mark.asyncio
    async def test_reset_health(self, aggregator):
        aggregator.reset_health()
        assert aggregator.get_provider_health() == {}
        aggregator._health.record_failure("jupiter")
        aggregator.reset_health("jupiter")
        # After reset, jupiter is still tracked but no longer disabled
        status = aggregator.get_provider_health()
        assert status.get("jupiter") in ("active",)

    @pytest.mark.asyncio
    async def test_safe_api_call_skips_degraded_provider(self, aggregator):
        """Test that degraded providers are skipped."""
        # Degrade a provider
        aggregator._health.record_failure("1inch")
        aggregator._health.record_failure("1inch")
        aggregator._health.record_failure("1inch")

        async def should_not_be_called():
            raise AssertionError("This should not be called")

        result = await aggregator._safe_api_call("1inch", should_not_be_called)
        assert "error" in result
        assert "degraded" in result["error"]

    @pytest.mark.asyncio
    async def test_safe_api_call_timeout(self, aggregator):
        """Test that timeout is handled gracefully."""

        async def slow_method():
            import asyncio
            await asyncio.sleep(100)  # will timeout

        with patch.object(aggregator, "_health") as mock_health:
            mock_health.is_available.return_value = True
            mock_health.record_success = MagicMock()
            mock_health.record_failure = MagicMock()

            result = await aggregator._safe_api_call("slowpoke", slow_method)
            assert "error" in result

    @pytest.mark.asyncio
    async def test_paraswap_swap(self, aggregator):
        """Test Paraswap swap flow."""
        mock_price = MagicMock()
        mock_price.json.return_value = {
            "priceRoute": {"destAmount": "500000000", "bestRoute": []}
        }
        mock_price.raise_for_status = MagicMock()

        mock_tx = MagicMock()
        mock_tx.json.return_value = {"from": "0x...", "to": "0x...", "value": "0", "data": "0x..."}
        mock_tx.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_price)):
            with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_tx)):
                result = await aggregator.paraswap_swap(
                    Chain.ETHEREUM,
                    "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                    "1000000000000000000",
                    "0x1234567890123456789012345678901234567890",
                )
                assert "from" in result

    @pytest.mark.asyncio
    async def test_paraswap_swap_no_price_route(self, aggregator):
        """Test Paraswap swap with no price route."""
        mock_price = MagicMock()
        mock_price.json.return_value = {}  # no priceRoute
        mock_price.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_price)):
            result = await aggregator.paraswap_swap(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "1000000000000000000",
                "0x1234567890123456789012345678901234567890",
            )
            assert "error" in result

    @pytest.mark.asyncio
    async def test_aggregator_error(self):
        with pytest.raises(AggregatorError):
            raise AggregatorError("Test error")

    @pytest.mark.asyncio
    async def test_get_best_quote_returns_provider_status(self, aggregator, mock_1inch_response, mock_paraswap_response, mock_0x_response):
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = [mock_1inch_response, mock_paraswap_response, mock_0x_response]
            result = await aggregator.get_best_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                1000000000000000000,
            )
            assert "provider_status" in result
            assert isinstance(result["provider_status"], dict)

    @pytest.mark.asyncio
    async def test_get_best_quote_solana_error(self, aggregator):
        """Test Solana quote when Jupiter API fails."""
        with patch("httpx.AsyncClient.get", AsyncMock(side_effect=Exception("Jupiter API error"))):
            result = await aggregator.get_best_quote(
                Chain.SOLANA,
                "So11111111111111111111111111111111111111112",
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                1000000000,
            )
            assert result["best_provider"] is None
            assert "error" in result

    @pytest.mark.asyncio
    async def test_get_best_quote_evm_fallback_chain(self, aggregator):
        """Test that when all providers fail, fallback chain is attempted."""
        # First batch: all fail
        all_fail = MagicMock()
        all_fail.json.side_effect = Exception("API error")

        # Fallback attempt: 1inch succeeds
        mock_1inch = MagicMock()
        mock_1inch.json.return_value = {"toAmount": "300000000"}
        mock_1inch.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = [all_fail, all_fail, all_fail, mock_1inch]

            result = await aggregator.get_best_quote(
                Chain.ETHEREUM,
                "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE",
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                1000000000000000000,
            )
            # The fallback chain should have succeeded with 1inch
            assert result["best_provider"] == "1inch"
            assert result["amount_out"] == "300000000"
            assert result["fallback_used"] is True