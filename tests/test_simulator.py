"""Tests for Transaction Simulator module."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass

from web3_agent_kit.simulator import TxSimulator, SimResult, SimConfig, SimMode


class TestSimResult:
    """Test SimResult dataclass."""

    def test_create_success(self):
        """Test creating a success result."""
        result = SimResult(success=True, gas_used=21000, gas_limit=30000, return_value="0x")
        assert result.success is True
        assert result.gas_used == 21000
        assert result.gas_limit == 30000
        assert result.error == ""
        assert result.revert_reason == ""

    def test_create_failure(self):
        """Test creating a failure result."""
        result = SimResult(success=False, error="execution reverted", revert_reason="execution reverted: out of gas")
        assert result.success is False
        assert result.error == "execution reverted"
        assert result.revert_reason == "execution reverted: out of gas"

    def test_to_dict(self):
        """Test to_dict conversion."""
        result = SimResult(
            success=True,
            gas_used=50000,
            gas_limit=60000,
            return_value="0x1234",
            events=[{"name": "Transfer"}],
            state_changes=[{"address": "0xabc"}],
            warnings=["Recipient has zero balance"],
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["gas_used"] == 50000
        assert d["num_events"] == 1
        assert d["num_state_changes"] == 1
        assert d["warnings"] == ["Recipient has zero balance"]

    def test_default_values(self):
        """Test default values."""
        result = SimResult(success=True)
        assert result.gas_used == 0
        assert result.gas_limit == 0
        assert result.return_value == "0x"
        assert result.events == []
        assert result.state_changes == []
        assert result.balance_changes == []
        assert result.logs == []
        assert result.warnings == []


class TestSimConfig:
    """Test SimConfig dataclass."""

    def test_default_config(self):
        """Test default configuration."""
        config = SimConfig()
        assert config.mode == SimMode.ETH_CALL
        assert config.block_number is None
        assert config.gas_multiplier == 1.2
        assert config.include_state_diff is True
        assert config.include_events is True

    def test_tenderly_config(self):
        """Test Tenderly configuration."""
        config = SimConfig(
            mode=SimMode.TENDERLY,
            tenderly_api_key="test_key",
            tenderly_user="test_user",
            tenderly_project="test_project",
        )
        assert config.mode == SimMode.TENDERLY
        assert config.tenderly_api_key == "test_key"
        assert config.tenderly_user == "test_user"
        assert config.tenderly_project == "test_project"

    def test_fork_config(self):
        """Test local fork configuration."""
        config = SimConfig(mode=SimMode.LOCAL_FORK, fork_url="http://localhost:8545")
        assert config.mode == SimMode.LOCAL_FORK
        assert config.fork_url == "http://localhost:8545"

    def test_block_number(self):
        """Test block number configuration."""
        config = SimConfig(block_number=12345678)
        assert config.block_number == 12345678


class TestSimMode:
    """Test SimMode enum."""

    def test_values(self):
        """Test enum values."""
        assert SimMode.ETH_CALL.value == "eth_call"
        assert SimMode.TENDERLY.value == "tenderly"
        assert SimMode.LOCAL_FORK.value == "local_fork"


class TestTxSimulator:
    """Test TxSimulator class."""

    @pytest.fixture
    def mock_w3(self):
        """Create a mock Web3 instance."""
        w3 = MagicMock()
        w3.to_checksum_address.side_effect = lambda addr: addr
        w3.eth = MagicMock()
        w3.eth.chain_id = 1
        return w3

    @pytest.fixture
    def simulator(self, mock_w3):
        """Create a TxSimulator with mocked Web3."""
        with patch("web3.Web3") as mock_web3_class:
            mock_web3_class.HTTPProvider = MagicMock()
            mock_web3_class.return_value = mock_w3
            sim = TxSimulator(rpc_url="https://eth.llamarpc.com")
            yield sim

    def test_init(self, simulator):
        """Test initialization."""
        assert simulator.rpc_url == "https://eth.llamarpc.com"
        assert isinstance(simulator.config, SimConfig)
        assert simulator.config.mode == SimMode.ETH_CALL

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = SimConfig(mode=SimMode.TENDERLY)
        with patch("web3.Web3") as mock_web3_class:
            mock_web3_class.HTTPProvider = MagicMock()
            mock_web3_class.return_value = MagicMock()
            sim = TxSimulator(rpc_url="https://eth.llamarpc.com", config=config)
            assert sim.config.mode == SimMode.TENDERLY

    def test_simulate_eth_call_success(self, simulator, mock_w3):
        """Test successful eth_call simulation."""
        mock_w3.eth.call.return_value = b"\x00" * 32
        mock_w3.eth.estimate_gas.return_value = 50000
        mock_w3.eth.get_balance.return_value = 1000000000000000000  # 1 ETH

        result = simulator.simulate(
            from_address="0x1234567890123456789012345678901234567890",
            to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            data="0xabcdef",
            value=1000000000000000000,  # 1 ETH
            gas_limit=100000,
        )

        assert result.success is True
        assert result.gas_used == 50000
        assert result.gas_limit == int(50000 * 1.2)  # With multiplier
        assert len(result.warnings) == 0
        assert len(result.balance_changes) == 2  # sender and recipient

    def test_simulate_eth_call_no_value(self, simulator, mock_w3):
        """Test eth_call simulation with no value."""
        mock_w3.eth.call.return_value = b"\x00" * 32
        mock_w3.eth.estimate_gas.return_value = 25000

        result = simulator.simulate(
            from_address="0x1234567890123456789012345678901234567890",
            to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            data="0xabcdef",
            value=0,
        )

        assert result.success is True
        assert len(result.balance_changes) == 0

    def test_simulate_eth_call_revert(self, simulator, mock_w3):
        """Test eth_call simulation that reverts."""
        mock_w3.eth.call.side_effect = Exception("execution reverted: insufficient funds")

        result = simulator.simulate(
            from_address="0x1234567890123456789012345678901234567890",
            to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            data="0xabcdef",
        )

        assert result.success is False
        assert "execution reverted" in result.revert_reason.lower()
        assert result.error is not None

    def test_simulate_eth_call_gas_estimate_failure(self, simulator, mock_w3):
        """Test eth_call when gas estimation fails."""
        mock_w3.eth.call.return_value = b"\x00" * 32
        mock_w3.eth.estimate_gas.side_effect = Exception("gas estimation failed")
        mock_w3.eth.get_balance.return_value = 0

        result = simulator.simulate(
            from_address="0x1234567890123456789012345678901234567890",
            to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            data="0xabcdef",
            value=0,
        )

        assert result.success is True
        assert result.gas_used == 0
        assert result.gas_limit == 0
        assert "Gas estimation failed" in result.warnings[0]

    def test_simulate_eth_call_recipient_zero_balance(self, simulator, mock_w3):
        """Test warning when recipient has zero balance."""
        mock_w3.eth.call.return_value = b"\x00" * 32
        mock_w3.eth.estimate_gas.return_value = 50000
        mock_w3.eth.get_balance.side_effect = [1000000000000000000, 0]  # sender has ETH, recipient none

        result = simulator.simulate(
            from_address="0x1234567890123456789012345678901234567890",
            to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            data="0xabcdef",
            value=1000000000000000000,
        )

        assert result.success is True
        assert "Recipient has zero balance" in result.warnings

    def test_simulate_tenderly_missing_config(self, simulator):
        """Test tenderly simulation with missing config."""
        simulator.config.mode = SimMode.TENDERLY
        with pytest.raises(ValueError, match="Tenderly API key"):
            simulator.simulate(
                from_address="0x1234567890123456789012345678901234567890",
                to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            )

    @patch("requests.post")
    def test_simulate_tenderly_success(self, mock_post, simulator):
        """Test successful tenderly simulation."""
        simulator.config.mode = SimMode.TENDERLY
        simulator.config.tenderly_api_key = "test_key"
        simulator.config.tenderly_user = "test_user"
        simulator.config.tenderly_project = "test_project"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "simulation": {
                "transaction": {
                    "status": True,
                    "gas_used": 50000,
                    "logs": [{"address": "0xabc"}],
                    "error_info": None,
                },
                "state_overrides": {"0xabc": {"balance": "100"}},
            }
        }
        mock_post.return_value = mock_response

        result = simulator.simulate(
            from_address="0x1234567890123456789012345678901234567890",
            to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            data="0xabcdef",
            value=0,
        )

        assert result.success is True
        assert result.gas_used == 50000
        assert len(result.events) == 1
        assert len(result.state_changes) == 1

    @patch("requests.post")
    def test_simulate_tenderly_api_error(self, mock_post, simulator):
        """Test tenderly simulation with API error."""
        simulator.config.mode = SimMode.TENDERLY
        simulator.config.tenderly_api_key = "test_key"
        simulator.config.tenderly_user = "test_user"
        simulator.config.tenderly_project = "test_project"

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        result = simulator.simulate(
            from_address="0x1234567890123456789012345678901234567890",
            to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        )

        assert result.success is False
        assert "Tenderly API error: 401" in result.error

    @patch("requests.post")
    def test_simulate_tenderly_with_block_number(self, mock_post, simulator):
        """Test tenderly simulation with specific block number."""
        simulator.config.mode = SimMode.TENDERLY
        simulator.config.tenderly_api_key = "test_key"
        simulator.config.tenderly_user = "test_user"
        simulator.config.tenderly_project = "test_project"
        simulator.config.block_number = 19000000

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "simulation": {
                "transaction": {"status": True, "gas_used": 21000},
                "state_overrides": {},
            }
        }
        mock_post.return_value = mock_response

        result = simulator.simulate(
            from_address="0x1234567890123456789012345678901234567890",
            to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
        )

        assert result.success is True
        # Verify block_number was in payload
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["json"]["block_number"] == 19000000

    def test_simulate_fork_missing_url(self, simulator):
        """Test fork simulation with missing fork_url."""
        simulator.config.mode = SimMode.LOCAL_FORK
        with pytest.raises(ValueError, match="fork_url required"):
            simulator.simulate(
                from_address="0x1234567890123456789012345678901234567890",
                to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            )

    @patch("requests.post")
    def test_simulate_fork_success(self, mock_post, simulator):
        """Test successful local fork simulation."""
        simulator.config.mode = SimMode.LOCAL_FORK
        simulator.config.fork_url = "http://localhost:8545"

        with patch("web3.Web3") as mock_w3_class:
            mock_fork_w3 = MagicMock()
            mock_w3_class.HTTPProvider = MagicMock()
            mock_w3_class.return_value = mock_fork_w3
            mock_fork_w3.to_checksum_address.side_effect = lambda addr: addr
            mock_fork_w3.eth.call.return_value = b"\x00" * 32
            mock_fork_w3.eth.estimate_gas.return_value = 75000

            result = simulator.simulate(
                from_address="0x1234567890123456789012345678901234567890",
                to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
                data="0xabcdef",
            )

            assert result.success is True
            assert result.gas_used == 75000
            assert result.gas_limit == int(75000 * 1.2)

    @patch("requests.post")
    def test_simulate_fork_impersonation_fails_still_works(self, mock_post, simulator):
        """Test fork simulation even when impersonation fails."""
        simulator.config.mode = SimMode.LOCAL_FORK
        simulator.config.fork_url = "http://localhost:8545"
        mock_post.side_effect = Exception("impersonation error")

        with patch("web3.Web3") as mock_w3_class:
            mock_fork_w3 = MagicMock()
            mock_w3_class.HTTPProvider = MagicMock()
            mock_w3_class.return_value = mock_fork_w3
            mock_fork_w3.to_checksum_address.side_effect = lambda addr: addr
            mock_fork_w3.eth.call.return_value = b"\x00" * 32
            mock_fork_w3.eth.estimate_gas.return_value = 50000

            result = simulator.simulate(
                from_address="0x1234567890123456789012345678901234567890",
                to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            )

            assert result.success is True
            assert result.gas_used == 50000

    @patch("requests.post")
    def test_simulate_fork_failure(self, mock_post, simulator):
        """Test fork simulation that fails."""
        simulator.config.mode = SimMode.LOCAL_FORK
        simulator.config.fork_url = "http://localhost:8545"

        with patch("web3.Web3") as mock_w3_class:
            mock_fork_w3 = MagicMock()
            mock_w3_class.HTTPProvider = MagicMock()
            mock_w3_class.return_value = mock_fork_w3
            mock_fork_w3.to_checksum_address.side_effect = lambda addr: addr
            mock_fork_w3.eth.call.side_effect = Exception("execution reverted")

            result = simulator.simulate(
                from_address="0x1234567890123456789012345678901234567890",
                to="0xabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            )

            assert result.success is False
            assert "execution reverted" in result.error

    def test_simulate_batch_all_success(self, simulator, mock_w3):
        """Test batch simulation where all succeed."""
        mock_w3.eth.call.return_value = b"\x00" * 32
        mock_w3.eth.estimate_gas.return_value = 50000
        mock_w3.eth.get_balance.return_value = 0

        transactions = [
            {"to": "0xabc1", "data": "0xdef1"},
            {"to": "0xabc2", "data": "0xdef2", "value": 1000},
        ]

        results = simulator.simulate_batch(
            transactions=transactions,
            from_address="0x1234567890123456789012345678901234567890",
        )

        assert len(results) == 2
        assert all(r.success for r in results)

    def test_simulate_batch_stops_on_failure(self, simulator, mock_w3):
        """Test batch simulation stops on first failure."""
        mock_w3.eth.call.side_effect = [
            b"\x00" * 32,
            Exception("execution reverted"),
            b"\x00" * 32,
        ]
        mock_w3.eth.estimate_gas.return_value = 50000
        mock_w3.eth.get_balance.return_value = 0

        transactions = [
            {"to": "0xabc1", "data": "0xdef1"},
            {"to": "0xabc2", "data": "0xdef2"},
            {"to": "0xabc3", "data": "0xdef3"},
        ]

        results = simulator.simulate_batch(
            transactions=transactions,
            from_address="0x1234567890123456789012345678901234567890",
        )

        assert len(results) == 2  # Stops after failure
        assert results[0].success is True
        assert results[1].success is False

    def test_check_approval(self, simulator, mock_w3):
        """Test checking token approval."""
        mock_contract = MagicMock()
        mock_w3.eth.contract.return_value = mock_contract
        mock_allowance_fn = MagicMock()
        mock_contract.functions.allowance.return_value = mock_allowance_fn
        mock_allowance_fn.call.return_value = 1000000000000000000

        result = simulator.check_approval(
            token="0xabc123",
            owner="0xowner123",
            spender="0xspender123",
        )

        assert result["token"] == "0xabc123"
        assert result["owner"] == "0xowner123"
        assert result["spender"] == "0xspender123"
        assert result["allowance"] == 1000000000000000000

    def test_to_dict_empty_warnings(self):
        """Test to_dict with empty warnings."""
        result = SimResult(success=True)
        d = result.to_dict()
        assert d["warnings"] == []

    def test_to_dict_no_events_or_state_changes(self):
        """Test to_dict with no events or state_changes."""
        result = SimResult(success=True, gas_used=21000)
        d = result.to_dict()
        assert d["num_events"] == 0
        assert d["num_state_changes"] == 0