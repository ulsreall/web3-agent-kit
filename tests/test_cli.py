"""Tests for the WAK CLI (web3_agent_kit.cli)."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from web3_agent_kit.cli.commands.agent import agent
from web3_agent_kit.cli.commands.doctor import doctor
from web3_agent_kit.cli.commands.examples import examples
from web3_agent_kit.cli.commands.gas import gas
from web3_agent_kit.cli.commands.info import (
    _count_chains,
    _count_modules,
    _read_version,
    info,
)
from web3_agent_kit.cli.commands.token import token
from web3_agent_kit.cli.commands.wallet import wallet
from web3_agent_kit.cli.main import main

runner = CliRunner()


# === main group ===


class TestMainGroup:
    def test_no_subcommand_shows_banner_and_help(self):
        result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "Web3 Agent Kit CLI" in result.output
        assert "Usage" in result.output

    def test_help(self):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "WAK" in result.output

    def test_version(self):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "1.12.0" in result.output

    def test_subcommands_registered(self):
        result = runner.invoke(main, ["--help"])
        for cmd in ("info", "doctor", "wallet", "token", "gas", "agent", "examples"):
            assert cmd in result.output


# === info command ===


class TestInfoCommand:
    def test_info_runs(self):
        result = runner.invoke(info, [])
        assert result.exit_code == 0
        assert "web3-agent-kit" in result.output
        assert "Beta (module maturity varies)" in result.output
        assert "Use testnets and explicit spending limits" in result.output
        assert "Capabilities" in result.output
        assert "Links" in result.output

    def test_count_modules(self, tmp_path):
        pkg = tmp_path / "mymod"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        # dir without __init__ should not count
        (tmp_path / "nopkg").mkdir()
        # hidden / underscore dirs skipped
        hidden = tmp_path / "_private"
        hidden.mkdir()
        (hidden / "__init__.py").write_text("")
        assert _count_modules(str(tmp_path)) == 1

    def test_count_chains(self, tmp_path):
        chains_dir = tmp_path / "chains"
        chains_dir.mkdir()
        (chains_dir / "chain.py").write_text(
            'class Chain:\n'
            '    ETHEREUM = "ethereum"\n'
            '    BASE = "base"\n'
            '    # COMMENT = "skip"\n'
        )
        assert _count_chains(str(tmp_path)) == 2

    def test_count_chains_missing_file(self, tmp_path):
        assert _count_chains(str(tmp_path)) == 0

    def test_read_version_returns_string(self):
        version = _read_version()
        assert isinstance(version, str)
        assert version != ""

    def test_read_version_missing_pyproject(self):
        with patch("os.path.isfile", return_value=False):
            assert _read_version() == "unknown"

    def test_info_through_main(self):
        result = runner.invoke(main, ["info"])
        assert result.exit_code == 0


# === doctor command ===


class TestDoctorCommand:
    def test_doctor_runs(self):
        result = runner.invoke(doctor, [])
        assert result.exit_code == 0
        assert "WAK Doctor" in result.output
        assert "Python" in result.output

    def test_doctor_with_env_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("PRIVATE_KEY=0xabc123\n")
        monkeypatch.setenv("PRIVATE_KEY", "0x1234567890abcdef1234")
        result = runner.invoke(doctor, [])
        assert result.exit_code == 0
        assert ".env file" in result.output
        # masked private key
        assert "PRIVATE_KEY" in result.output

    def test_doctor_short_env_masked(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("RPC_URL", "short")
        result = runner.invoke(doctor, [])
        assert result.exit_code == 0
        assert "***" in result.output

    def test_doctor_through_main(self):
        result = runner.invoke(main, ["doctor"])
        assert result.exit_code == 0


# === wallet command ===


class TestWalletCommand:
    def test_wallet_group_help(self):
        result = runner.invoke(wallet, ["--help"])
        assert result.exit_code == 0
        assert "balance" in result.output

    def test_wallet_balance(self):
        result = runner.invoke(
            wallet, ["balance", "--address", "0xabc", "--chain", "base"]
        )
        assert result.exit_code == 0
        assert "0xabc" in result.output
        assert "base" in result.output

    def test_wallet_balance_short_opts(self):
        result = runner.invoke(wallet, ["balance", "-a", "0xdef"])
        assert result.exit_code == 0
        assert "0xdef" in result.output

    def test_wallet_balance_requires_address(self):
        result = runner.invoke(wallet, ["balance"])
        assert result.exit_code != 0


# === token command ===


class TestTokenCommand:
    def test_token_group_help(self):
        result = runner.invoke(token, ["--help"])
        assert result.exit_code == 0
        assert "check" in result.output

    def test_token_check(self):
        result = runner.invoke(
            token, ["check", "--address", "0xtoken", "--chain", "ethereum"]
        )
        assert result.exit_code == 0
        assert "0xtoken" in result.output
        assert "Token Safety Check" in result.output

    def test_token_check_requires_address(self):
        result = runner.invoke(token, ["check"])
        assert result.exit_code != 0


# === gas command ===


class TestGasCommand:
    def test_gas_default(self):
        result = runner.invoke(gas, [])
        assert result.exit_code == 0
        assert "Gas Price Estimator" in result.output
        assert "ethereum" in result.output
        assert "medium" in result.output

    def test_gas_with_options(self):
        result = runner.invoke(gas, ["-c", "base", "-p", "high"])
        assert result.exit_code == 0
        assert "base" in result.output
        assert "high" in result.output

    def test_gas_invalid_priority(self):
        result = runner.invoke(gas, ["-p", "invalid"])
        assert result.exit_code != 0


# === agent command ===


class TestAgentCommand:
    def test_agent_runs(self):
        result = runner.invoke(
            agent, ["--goal", "swap ETH", "--wallet", "0x1234", "--chain", "base"]
        )
        assert result.exit_code == 0
        assert "swap ETH" in result.output
        assert "0x1234" in result.output
        assert "WAK Agent" in result.output

    def test_agent_requires_goal_and_wallet(self):
        result = runner.invoke(agent, [])
        assert result.exit_code != 0

    def test_agent_short_opts(self):
        result = runner.invoke(agent, ["-g", "bridge", "-w", "0xabc", "-c", "base"])
        assert result.exit_code == 0
        assert "bridge" in result.output


# === examples command ===


class TestExamplesCommand:
    def test_examples_lists_files(self, tmp_path):
        examples_dir = tmp_path / "examples"
        examples_dir.mkdir()
        (examples_dir / "swap_agent.py").write_text("")
        (examples_dir / "custom.py").write_text("")
        (examples_dir / "notpython.txt").write_text("")
        with patch("os.path.normpath", return_value=str(examples_dir)):
            result = runner.invoke(examples, [])
        assert result.exit_code == 0
        assert "swap_agent.py" in result.output
        assert "custom.py" in result.output
        assert "notpython.txt" not in result.output

    def test_examples_dir_missing(self):
        with patch("os.path.isdir", return_value=False):
            result = runner.invoke(examples, [])
        assert result.exit_code == 0
        assert "Examples directory not found" in result.output

    def test_examples_no_py_files(self, tmp_path):
        examples_dir = tmp_path / "examples"
        examples_dir.mkdir()
        (examples_dir / "readme.txt").write_text("")
        with patch("os.path.normpath", return_value=str(examples_dir)):
            result = runner.invoke(examples, [])
        assert result.exit_code == 0
        assert "No example files found" in result.output

    def test_examples_real_run(self):
        # Runs against the real examples dir (may or may not exist); must not crash.
        result = runner.invoke(examples, [])
        assert result.exit_code == 0
        assert "Available Examples" in result.output
