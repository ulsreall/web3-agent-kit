"""``Wallet.send`` / ``transfer_token`` / ``get_balance_summary``."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from web3_agent_kit.chains import Chain
from web3_agent_kit.wallet.wallet import TRANSFER_SELECTOR, Wallet

KEY = "0x" + "11" * 32
TOKEN = "0x" + "33" * 20
RECIPIENT = "0x" + "22" * 20


def _wallet(chain: Chain = Chain.BASE) -> tuple[Wallet, MagicMock]:
    wallet = Wallet.from_key(KEY)
    w3 = MagicMock()
    w3.to_checksum_address = lambda a: a
    w3.to_wei = lambda amount, unit: int(amount * 10**18)
    wallet.chain_manager = MagicMock()
    wallet.chain_manager.chains = [chain]
    wallet.chain_manager.get_web3.return_value = w3
    return wallet, w3


def test_send_builds_a_native_transfer_and_goes_through_the_gate():
    wallet, _ = _wallet()
    with patch.object(wallet, "send_transaction", return_value="0xhash") as send:
        assert wallet.send(RECIPIENT, 0.5) == {"hash": "0xhash"}

    tx, chain = send.call_args.args[0], send.call_args.args[1]
    assert tx == {"to": RECIPIENT, "value": 5 * 10**17}
    assert chain is Chain.BASE
    assert send.call_args.kwargs["action"].value == "transfer_native"


def test_transfer_token_encodes_transfer_calldata():
    wallet, w3 = _wallet()
    contract = MagicMock()
    contract.functions.decimals.return_value.call.return_value = 6
    w3.eth.contract.return_value = contract

    with patch.object(wallet, "send_transaction", return_value="0xhash") as send:
        assert wallet.transfer_token(TOKEN, RECIPIENT, 12.5) == {"hash": "0xhash"}

    tx = send.call_args.args[0]
    assert tx["to"] == TOKEN
    assert tx["data"].startswith("0x" + TRANSFER_SELECTOR)
    # 12.5 USDC at 6 decimals, right-padded to 32 bytes
    assert tx["data"].endswith(f"{12_500_000:064x}")
    assert send.call_args.kwargs["action"].value == "transfer_token"


def test_balance_summary_reads_native_and_tokens():
    wallet, w3 = _wallet()
    contract = MagicMock()
    contract.functions.decimals.return_value.call.return_value = 6
    contract.functions.balanceOf.return_value.call.return_value = 2_500_000
    w3.eth.contract.return_value = contract

    with patch.object(wallet, "get_balance", return_value=1.25):
        summary = wallet.get_balance_summary(tokens=[TOKEN])

    assert summary == {"native": 1.25, "tokens": {TOKEN: 2.5}}


def test_chain_is_required_when_the_manager_has_several():
    wallet, _ = _wallet()
    wallet.chain_manager.chains = [Chain.BASE, Chain.ETHEREUM]
    with pytest.raises(ValueError, match="chain is required"):
        wallet.send(RECIPIENT, 1)
