"""``Wallet.send_transaction`` fills the fields a caller may omit."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from web3_agent_kit.chains import Chain
from web3_agent_kit.wallet.wallet import Wallet

KEY = "0x" + "11" * 32


def _wallet() -> tuple[Wallet, MagicMock]:
    wallet = Wallet.from_key(KEY)
    w3 = MagicMock()
    w3.eth.get_transaction_count.return_value = 7
    w3.eth.estimate_gas.return_value = 21_000
    w3.eth.get_block.return_value = {"baseFeePerGas": 10**9}
    w3.eth.max_priority_fee = 10**6
    w3.eth.gas_price = 2 * 10**9
    w3.eth.send_raw_transaction.return_value = MagicMock(hex=lambda: "0xhash")
    wallet.chain_manager = MagicMock()
    wallet.chain_manager.get_web3.return_value = w3
    return wallet, w3


def test_missing_fields_are_filled_before_signing():
    wallet, w3 = _wallet()
    with patch.object(wallet, "sign_transaction", return_value=b"signed") as sign:
        assert wallet.send_transaction({"to": "0x" + "22" * 20, "value": 1}, Chain.BASE) == "0xhash"

    tx = sign.call_args.args[0]
    assert tx["from"] == wallet.address
    assert tx["chainId"] == 8453
    assert tx["nonce"] == 7
    assert tx["gas"] == 21_000
    assert tx["maxFeePerGas"] == 2 * 10**9 + 10**6
    assert tx["maxPriorityFeePerGas"] == 10**6
    w3.eth.send_raw_transaction.assert_called_once_with(b"signed")


def test_caller_values_are_preserved():
    wallet, _ = _wallet()
    tx = {"to": "0x" + "22" * 20, "nonce": 3, "gas": 50_000, "gasPrice": 5}
    with patch.object(wallet, "sign_transaction", return_value=b"signed") as sign:
        wallet.send_transaction(tx, Chain.BASE)

    sent = sign.call_args.args[0]
    assert sent["nonce"] == 3
    assert sent["gas"] == 50_000
    assert sent["gasPrice"] == 5
    assert "maxFeePerGas" not in sent


def test_legacy_chain_without_base_fee_uses_gas_price():
    wallet, w3 = _wallet()
    w3.eth.get_block.return_value = {}
    with patch.object(wallet, "sign_transaction", return_value=b"signed") as sign:
        wallet.send_transaction({"to": "0x" + "22" * 20}, Chain.BSC)

    sent = sign.call_args.args[0]
    assert sent["gasPrice"] == 2 * 10**9
    assert "maxFeePerGas" not in sent
