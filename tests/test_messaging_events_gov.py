"""Tests for messaging, events, governance, and account_abstraction modules.

All network/RPC calls are mocked — tests are fully offline.
"""

from unittest.mock import MagicMock, patch

import pytest

from web3_agent_kit.account_abstraction import (
    BUNDLER_RPCS,
    ENTRY_POINTS,
    KNOWN_FACTORIES,
    AAPaymaster,
    AAWallet,
    UserOperation,
    UserOpResult,
)
from web3_agent_kit.events import (
    ERC20_TRANSFER_ABI,
    EventConfig,
    EventListener,
    Subscription,
)
from web3_agent_kit.governance import (
    KNOWN_DAOS,
    DelegateInfo,
    GovConfig,
    GovernanceTracker,
    Proposal,
    ProposalStatus,
    VoteChoice,
    VotingPower,
)
from web3_agent_kit.messaging import (
    CCIP_CHAIN_SELECTORS,
    LZ_CHAIN_IDS,
    BridgeProtocol,
    CrossChainMessenger,
    MessageResult,
    MessageStatus,
)


# ----------------------------------------------------------------------------
# Messaging
# ----------------------------------------------------------------------------
class TestMessaging:
    def test_message_result_to_dict(self):
        res = MessageResult(tx_hash="0xabc", dst_chain="optimism", src_chain="arbitrum", nonce=3)
        d = res.to_dict()
        assert d["tx_hash"] == "0xabc"
        assert d["dst_chain"] == "optimism"
        assert d["status"] == "pending"
        assert d["nonce"] == 3

    def test_init_no_rpc(self):
        m = CrossChainMessenger(bridge="wormhole", rpc_url="")
        assert m.w3 is None
        assert m.bridge == BridgeProtocol.WORMHOLE

    def test_init_with_rpc(self):
        with patch("web3.Web3") as MockWeb3:
            MockWeb3.HTTPProvider.return_value = "provider"
            m = CrossChainMessenger(bridge="layerzero", rpc_url="https://x")
            assert m.w3 is not None

    def test_send_message_wormhole(self):
        m = CrossChainMessenger(bridge="wormhole", rpc_url="")
        res = m.send_message(dst_chain="optimism", dst_address="0xdead", payload="0x")
        assert res.src_chain == "arbitrum"
        assert res.estimated_delivery == 300

    def test_send_message_wormhole_unknown_chain(self):
        m = CrossChainMessenger(bridge="wormhole", rpc_url="")
        with pytest.raises(ValueError, match="Unknown Wormhole"):
            m.send_message(dst_chain="nope", dst_address="0xdead")

    def test_send_message_ccip(self):
        m = CrossChainMessenger(bridge="chainlink_ccip", rpc_url="")
        res = m.send_message(dst_chain="base", dst_address="0xdead")
        assert res.estimated_delivery == 600

    def test_send_message_ccip_unknown_chain(self):
        m = CrossChainMessenger(bridge="chainlink_ccip", rpc_url="")
        with pytest.raises(ValueError, match="Unknown CCIP"):
            m.send_message(dst_chain="nope", dst_address="0xdead")

    def test_send_layerzero_unknown_dst(self):
        m = CrossChainMessenger(bridge="layerzero", rpc_url="")
        m.w3 = MagicMock()
        with pytest.raises(ValueError, match="Unknown chain"):
            m.send_message(dst_chain="nope", dst_address="0xdead")

    def test_send_layerzero_no_endpoint(self):
        m = CrossChainMessenger(bridge="layerzero", rpc_url="", src_chain="fantom")
        m.w3 = MagicMock()
        with pytest.raises(ValueError, match="No LayerZero endpoint"):
            m.send_message(dst_chain="optimism", dst_address="0xdead")

    def test_send_layerzero_read_only(self):
        m = CrossChainMessenger(bridge="layerzero", rpc_url="", src_chain="arbitrum")
        w3 = MagicMock()
        w3.eth.default_account = "0x0000000000000000000000000000000000000001"
        contract = MagicMock()
        contract.functions.minDstGasLookup.return_value.call.return_value = 0
        contract.functions.send.return_value.build_transaction.return_value = {}
        w3.eth.contract.return_value = contract
        m.w3 = w3
        res = m.send_message(
            dst_chain="optimism",
            dst_address="0x00000000000000000000000000000000000000ab",
        )
        assert res.tx_hash == "0x" + "0" * 64
        assert res.dst_chain == "optimism"

    def test_send_message_unsupported_bridge(self):
        m = CrossChainMessenger(bridge="layerzero", rpc_url="")
        m.bridge = BridgeProtocol.HYPERLANE
        with pytest.raises(ValueError, match="Unsupported bridge"):
            m.send_message(dst_chain="optimism", dst_address="0xdead")

    def test_track_status_lz_delivered(self):
        m = CrossChainMessenger(bridge="layerzero", rpc_url="")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"messages": {"status": "DELIVERED"}}
        with patch("requests.get", return_value=resp):
            assert m.track_status("0xhash") == MessageStatus.DELIVERED

    def test_track_status_lz_executed(self):
        m = CrossChainMessenger(bridge="layerzero", rpc_url="")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"messages": {"status": "EXECUTED"}}
        with patch("requests.get", return_value=resp):
            assert m.track_status("0xhash") == MessageStatus.EXECUTED

    def test_track_status_lz_failed(self):
        m = CrossChainMessenger(bridge="layerzero", rpc_url="")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"messages": {"status": "FAILED"}}
        with patch("requests.get", return_value=resp):
            assert m.track_status("0xhash") == MessageStatus.FAILED

    def test_track_status_lz_pending(self):
        m = CrossChainMessenger(bridge="layerzero", rpc_url="")
        resp = MagicMock()
        resp.status_code = 404
        with patch("requests.get", return_value=resp):
            assert m.track_status("0xhash") == MessageStatus.PENDING

    def test_track_status_lz_exception(self):
        m = CrossChainMessenger(bridge="layerzero", rpc_url="")
        with patch("requests.get", side_effect=RuntimeError("boom")):
            assert m.track_status("0xhash") == MessageStatus.UNKNOWN

    def test_track_status_wormhole_completed(self):
        m = CrossChainMessenger(bridge="wormhole", rpc_url="")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"operations": [{"status": "completed"}]}
        with patch("requests.get", return_value=resp):
            assert m.track_status("0xhash") == MessageStatus.EXECUTED

    def test_track_status_wormhole_pending(self):
        m = CrossChainMessenger(bridge="wormhole", rpc_url="")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"operations": []}
        with patch("requests.get", return_value=resp):
            assert m.track_status("0xhash") == MessageStatus.PENDING

    def test_track_status_wormhole_exception(self):
        m = CrossChainMessenger(bridge="wormhole", rpc_url="")
        with patch("requests.get", side_effect=RuntimeError("boom")):
            assert m.track_status("0xhash") == MessageStatus.UNKNOWN

    def test_track_status_ccip_unknown(self):
        m = CrossChainMessenger(bridge="chainlink_ccip", rpc_url="")
        assert m.track_status("0xhash") == MessageStatus.UNKNOWN

    def test_estimate_fee_layerzero(self):
        m = CrossChainMessenger(bridge="layerzero", rpc_url="")
        fee = m.estimate_fee("optimism")
        assert fee["protocol"] == "layerzero"
        assert fee["currency"] == "ETH"

    def test_estimate_fee_wormhole(self):
        m = CrossChainMessenger(bridge="wormhole", rpc_url="")
        fee = m.estimate_fee("solana")
        assert fee["protocol"] == "wormhole"

    def test_estimate_fee_other(self):
        m = CrossChainMessenger(bridge="chainlink_ccip", rpc_url="")
        fee = m.estimate_fee("base")
        assert fee["protocol"] == "chainlink_ccip"

    def test_constants(self):
        assert LZ_CHAIN_IDS["ethereum"] == 101
        assert CCIP_CHAIN_SELECTORS["base"] > 0


# ----------------------------------------------------------------------------
# Events
# ----------------------------------------------------------------------------
class TestEvents:
    def _abi(self):
        return ERC20_TRANSFER_ABI

    def test_subscribe_with_callback(self):
        listener = EventListener(rpc_url="https://x")
        sub_id = listener.subscribe(
            address="0xabc", abi=self._abi(), event="Transfer", callback=lambda e: None
        )
        assert sub_id in listener._subscriptions

    def test_subscribe_no_callback_no_webhook_raises(self):
        listener = EventListener(rpc_url="https://x")
        with pytest.raises(ValueError, match="Either callback or webhook"):
            listener.subscribe(address="0xabc", abi=self._abi(), event="Transfer")

    def test_subscribe_max_reached(self):
        listener = EventListener(rpc_url="https://x", max_subscriptions=1)
        listener.subscribe(address="0xa", abi=self._abi(), event="Transfer", callback=lambda e: None)
        with pytest.raises(ValueError, match="Max subscriptions"):
            listener.subscribe(address="0xb", abi=self._abi(), event="Transfer", callback=lambda e: None)

    def test_unsubscribe(self):
        listener = EventListener(rpc_url="https://x")
        sub_id = listener.subscribe(
            address="0xabc", abi=self._abi(), event="Transfer", callback=lambda e: None
        )
        assert listener.unsubscribe(sub_id) is True
        assert listener.unsubscribe(sub_id) is False

    def test_unsubscribe_nonexistent(self):
        listener = EventListener(rpc_url="https://x")
        assert listener.unsubscribe("nope") is False

    def test_start_idempotent(self):
        listener = EventListener(rpc_url="https://x")
        listener._running = True
        listener.start()  # returns early because already running
        assert listener._running is True

    def test_stop(self):
        listener = EventListener(rpc_url="https://x")
        listener._running = True
        listener.stop()
        assert listener._running is False

    def test_get_status(self):
        listener = EventListener(rpc_url="https://x")
        listener.subscribe(
            address="0xabcdef0123456789", abi=self._abi(), event="Transfer", callback=lambda e: None
        )
        status = listener.get_status()
        assert status["running"] is False
        assert len(status["subscriptions"]) == 1
        assert status["subscriptions"][0]["event"] == "Transfer"

    def test_poll_subscription_no_new_blocks(self):
        listener = EventListener(rpc_url="https://x")
        sub_id = listener.subscribe(
            address="0x00000000000000000000000000000000000000ab",
            abi=self._abi(),
            event="Transfer",
            callback=lambda e: None,
        )
        sub = listener._subscriptions[sub_id]
        sub.last_block = 100
        w3 = MagicMock()
        w3.to_checksum_address.side_effect = lambda a: a
        # current_block equal to last_block -> from_block >= to_block -> return
        listener._poll_subscription(w3, sub, 100)
        assert sub.events_processed == 0

    def test_poll_subscription_processes_events(self):
        received = []
        listener = EventListener(rpc_url="https://x")
        sub_id = listener.subscribe(
            address="0x00000000000000000000000000000000000000ab",
            abi=self._abi(),
            event="Transfer",
            callback=received.append,
        )
        sub = listener._subscriptions[sub_id]
        sub.last_block = 0
        sub.config.from_block = 0

        event = MagicMock()
        event.blockNumber = 5
        event.transactionHash.hex.return_value = "0xdeadbeef"
        event.args = {"from": "0xa", "to": "0xb", "value": 100}
        event.logIndex = 2

        contract = MagicMock()
        contract.events.Transfer.get_logs.return_value = [event]
        w3 = MagicMock()
        w3.to_checksum_address.side_effect = lambda a: a
        w3.eth.contract.return_value = contract

        listener._poll_subscription(w3, sub, 10)
        assert sub.events_processed == 1
        assert received[0]["args"]["value"] == 100

    def test_poll_subscription_callback_error(self):
        listener = EventListener(rpc_url="https://x")

        def bad_cb(e):
            raise RuntimeError("callback broke")

        sub_id = listener.subscribe(
            address="0x00000000000000000000000000000000000000ab",
            abi=self._abi(),
            event="Transfer",
            callback=bad_cb,
        )
        sub = listener._subscriptions[sub_id]
        sub.last_block = 0
        sub.config.from_block = 0

        event = MagicMock()
        event.blockNumber = 5
        event.transactionHash.hex.return_value = "0xdeadbeef"
        event.args = {"value": 1}
        event.logIndex = 0
        contract = MagicMock()
        contract.events.Transfer.get_logs.return_value = [event]
        w3 = MagicMock()
        w3.to_checksum_address.side_effect = lambda a: a
        w3.eth.contract.return_value = contract

        # Callback error should be swallowed; event still counted
        listener._poll_subscription(w3, sub, 10)
        assert sub.events_processed == 1

    def test_poll_subscription_triggers_webhook(self):
        listener = EventListener(rpc_url="https://x")
        sub_id = listener.subscribe(
            address="0x00000000000000000000000000000000000000ab",
            abi=self._abi(),
            event="Transfer",
            webhook_url="https://hook",
        )
        sub = listener._subscriptions[sub_id]
        sub.last_block = 0
        sub.config.from_block = 0

        event = MagicMock()
        event.blockNumber = 5
        event.transactionHash.hex.return_value = "0xdeadbeef"
        event.args = {"value": 1}
        event.logIndex = 0
        contract = MagicMock()
        contract.events.Transfer.get_logs.return_value = [event]
        w3 = MagicMock()
        w3.to_checksum_address.side_effect = lambda a: a
        w3.eth.contract.return_value = contract

        with patch("requests.post") as mock_post:
            listener._poll_subscription(w3, sub, 10)
            mock_post.assert_called_once()

    def test_send_webhook_error_swallowed(self):
        listener = EventListener(rpc_url="https://x")
        config = EventConfig(
            address="0xa", abi=self._abi(), event_name="Transfer",
            callback=lambda e: None, webhook_url="https://hook",
        )
        with patch("requests.post", side_effect=RuntimeError("net down")):
            listener._send_webhook({"x": 1}, config)  # must not raise

    def test_subscription_dataclass(self):
        cfg = EventConfig(
            address="0xa", abi=self._abi(), event_name="Transfer", callback=lambda e: None
        )
        sub = Subscription(id="s1", config=cfg)
        assert sub.active is True
        assert sub.events_processed == 0


# ----------------------------------------------------------------------------
# Governance
# ----------------------------------------------------------------------------
class TestGovernance:
    def _tracker(self):
        with patch("web3.Web3"):
            t = GovernanceTracker(rpc_url="https://x")
        t.w3 = MagicMock()
        t.w3.to_checksum_address.side_effect = lambda a: a
        return t

    def test_proposal_to_dict(self):
        p = Proposal(id="1", title="Test", for_votes=10, against_votes=2)
        d = p.to_dict()
        assert d["id"] == "1"
        assert d["for_votes"] == 10
        assert d["status"] == "pending"

    def test_gov_config_defaults(self):
        cfg = GovConfig(rpc_url="https://x")
        assert "snapshot" in cfg.snapshot_graphql_url
        assert cfg.cache_ttl == 300

    def test_vote_choice_enum(self):
        assert VoteChoice.FOR.value == "for"
        assert VoteChoice.AGAINST.value == "against"

    def test_voting_power_dataclass(self):
        vp = VotingPower(address="0xa", token="0xt", power=5.0)
        assert vp.can_vote is True

    def test_delegate_info(self):
        di = DelegateInfo(address="0xa", name="Alice", voting_power=99.0)
        assert di.name == "Alice"

    def test_get_active_proposals_no_dao_no_governor(self):
        t = self._tracker()
        with pytest.raises(ValueError, match="Either dao name or governor_address"):
            t.get_active_proposals()

    def test_get_active_proposals_known_dao(self):
        t = self._tracker()
        governor = MagicMock()
        governor.functions.proposalCount.return_value.call.return_value = 2
        governor.functions.state.return_value.call.return_value = 1  # ACTIVE
        governor.functions.proposalDeadline.return_value.call.return_value = 12345
        governor.functions.proposalProposer.return_value.call.return_value = "0xauthor"
        t.w3.eth.contract.return_value = governor
        with patch.object(t, "_fetch_snapshot_proposals", return_value=[]):
            props = t.get_active_proposals(dao="uniswap", limit=2)
        assert len(props) == 2
        assert props[0].status == ProposalStatus.ACTIVE

    def test_get_active_proposals_governor_address(self):
        t = self._tracker()
        governor = MagicMock()
        governor.functions.proposalCount.return_value.call.return_value = 1
        governor.functions.state.return_value.call.return_value = 3  # DEFEATED (skipped)
        t.w3.eth.contract.return_value = governor
        props = t.get_active_proposals(governor_address="0xgov", limit=1)
        assert props == []

    def test_get_active_proposals_contract_error(self):
        t = self._tracker()
        governor = MagicMock()
        governor.functions.proposalCount.return_value.call.side_effect = RuntimeError("rpc down")
        t.w3.eth.contract.return_value = governor
        props = t.get_active_proposals(governor_address="0xgov")
        assert props == []

    def test_fetch_snapshot_proposals(self):
        t = self._tracker()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "data": {
                "proposals": [
                    {
                        "id": "p1",
                        "title": "T1",
                        "body": "body",
                        "start": 1,
                        "end": 2,
                        "state": "active",
                        "author": "0xa",
                        "choices": ["yes", "no"],
                        "scores_total": [3.0],
                        "quorum": 0,
                        "link": "http://x",
                    }
                ]
            }
        }
        with patch("requests.post", return_value=resp):
            props = t._fetch_snapshot_proposals("uniswap")
        assert len(props) == 1
        assert props[0].title == "T1"

    def test_fetch_snapshot_proposals_non_200(self):
        t = self._tracker()
        resp = MagicMock()
        resp.status_code = 500
        with patch("requests.post", return_value=resp):
            assert t._fetch_snapshot_proposals("uniswap") == []

    def test_fetch_snapshot_proposals_exception(self):
        t = self._tracker()
        with patch("requests.post", side_effect=RuntimeError("boom")):
            assert t._fetch_snapshot_proposals("uniswap") == []

    def test_get_voting_power_no_token_no_dao(self):
        t = self._tracker()
        with pytest.raises(ValueError, match="Either token or dao"):
            t.get_voting_power(address="0xa")

    def test_get_voting_power_with_dao(self):
        t = self._tracker()
        token = MagicMock()
        token.functions.balanceOf.return_value.call.return_value = 10 ** 18
        token.functions.delegates.return_value.call.return_value = (
            "0x000000000000000000000000000000000000000b"
        )
        token.functions.getCurrentVotes.return_value.call.return_value = 5 * 10 ** 18
        t.w3.eth.contract.return_value = token
        with patch("web3.Web3.from_wei", side_effect=lambda v, u: v / 10 ** 18):
            vp = t.get_voting_power(address="0x000000000000000000000000000000000000000a", dao="uniswap")
        assert vp.power == 5.0
        assert vp.delegated_to is not None
        assert vp.can_vote is True

    def test_get_voting_power_fallback_to_balance(self):
        t = self._tracker()
        token = MagicMock()
        token.functions.balanceOf.return_value.call.return_value = 2 * 10 ** 18
        token.functions.delegates.return_value.call.side_effect = RuntimeError("no delegates")
        token.functions.getCurrentVotes.return_value.call.side_effect = RuntimeError("no votes")
        t.w3.eth.contract.return_value = token
        with patch("web3.Web3.from_wei", side_effect=lambda v, u: v / 10 ** 18):
            vp = t.get_voting_power(address="0xa", token="0xt")
        assert vp.power == 2.0
        assert vp.delegated_to is None

    def test_delegate(self):
        t = self._tracker()
        account = MagicMock()
        account.address = "0xacct"
        t.w3.eth.account.from_key.return_value = account
        token = MagicMock()
        token.functions.delegate.return_value.build_transaction.return_value = {}
        t.w3.eth.contract.return_value = token
        signed = MagicMock()
        signed.raw_transaction = b"raw"
        t.w3.eth.account.sign_transaction.return_value = signed
        tx_hash = MagicMock()
        tx_hash.hex.return_value = "0xdelegatehash"
        t.w3.eth.send_raw_transaction.return_value = tx_hash
        result = t.delegate(delegatee="0xdel", token="0xt", private_key="0xkey")
        assert result == "0xdelegatehash"

    def test_get_delegates_success(self):
        t = self._tracker()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "delegates": [
                {"address": "0xa", "name": "A", "votingPower": 100, "delegators": 3}
            ]
        }
        with patch("requests.get", return_value=resp):
            dels = t.get_delegates("uniswap")
        assert len(dels) == 1
        assert dels[0].voting_power == 100.0

    def test_get_delegates_exception(self):
        t = self._tracker()
        with patch("requests.get", side_effect=RuntimeError("down")):
            assert t.get_delegates("uniswap") == []

    def test_get_all_daos(self):
        t = self._tracker()
        daos = t.get_all_daos()
        assert len(daos) == len(KNOWN_DAOS)
        assert all("governor" in d for d in daos)


# ----------------------------------------------------------------------------
# Account Abstraction
# ----------------------------------------------------------------------------
class TestAccountAbstraction:
    def _wallet(self):
        with patch("web3.Web3"):
            w = AAWallet(rpc_url="https://x", chain="base")
        w.w3 = MagicMock()
        return w

    def test_constants(self):
        assert ENTRY_POINTS["ethereum"].startswith("0x")
        assert "pimlico" in BUNDLER_RPCS["base"]
        assert "simple_account_v7" in KNOWN_FACTORIES

    def test_user_operation_defaults(self):
        op = UserOperation(sender="0xa", nonce=0)
        assert op.call_data == "0x"
        assert op.signature == "0x"

    def test_user_op_result(self):
        r = UserOpResult(user_op_hash="0xh")
        assert r.status == "pending"

    def test_wallet_init_defaults(self):
        w = self._wallet()
        assert w.factory_address == KNOWN_FACTORIES["simple_account_v7"]
        assert w.entry_point == ENTRY_POINTS["base"]

    def test_wallet_init_unknown_chain_falls_back(self):
        with patch("web3.Web3"):
            w = AAWallet(rpc_url="https://x", chain="unknownchain")
        assert w.entry_point == ENTRY_POINTS["ethereum"]
        assert w.bundler_url == "https://x"

    def test_get_counterfactual_address(self):
        w = self._wallet()
        with patch.object(w, "_encode_init_code", return_value="0x1234"):
            from web3 import Web3
            with patch("web3.Web3.keccak", return_value=b"\x00" * 32), \
                 patch("web3.Web3.to_bytes", side_effect=lambda *a, **k: b"\x00" * 20), \
                 patch("web3.Web3.to_checksum_address", side_effect=lambda a: a):
                addr = w.get_counterfactual_address(owner="0xowner")
        assert isinstance(addr, str)
        assert Web3  # imported

    def test_deploy_account_not_deployed(self):
        w = self._wallet()
        w.w3.eth.get_code.return_value = b"\x00"  # len <= 2
        with patch.object(w, "get_counterfactual_address", return_value="0xcf"):
            info = w.deploy_account(owner="0xowner")
        assert info.deployed is False
        assert info.address == "0xcf"

    def test_deploy_account_already_deployed(self):
        w = self._wallet()
        w.w3.eth.get_code.return_value = b"\x60\x60\x60"  # len > 2
        with patch.object(w, "get_counterfactual_address", return_value="0xcf"):
            info = w.deploy_account(owner="0xowner")
        assert info.deployed is True

    def test_send_user_op_no_sender_no_owner(self):
        w = self._wallet()
        with pytest.raises(ValueError, match="Either sender or owner"):
            w.send_user_op(to="0xdest")

    def test_send_user_op_with_sender(self):
        w = self._wallet()
        w.w3.eth.chain_id = 8453
        w.w3.eth.gas_price = 1_000_000_000
        w.w3.eth.get_code.return_value = b"\x60\x60"  # deployed
        with patch.object(w, "_submit_to_bundler", return_value="0xuohash"):
            res = w.send_user_op(to="0xdest", sender="0xsender", value=0)
        assert res.user_op_hash == "0xuohash"
        assert res.status == "pending"

    def test_send_user_op_with_owner_needs_deploy(self):
        w = self._wallet()
        w.w3.eth.chain_id = 8453
        w.w3.eth.gas_price = 1_000_000_000
        w.w3.eth.get_code.return_value = b"\x00"  # not deployed
        with patch.object(w, "get_counterfactual_address", return_value="0xsender"), \
             patch.object(w, "_encode_init_code", return_value="0xinit"), \
             patch.object(w, "_submit_to_bundler", return_value="0xuohash"):
            res = w.send_user_op(to="0xdest", owner="0xowner")
        assert res.user_op_hash == "0xuohash"

    def test_send_user_op_with_paymaster(self):
        pm = MagicMock()
        pm.get_paymaster_data.return_value = {
            "paymasterAndData": "0xpm", "verificationGasLimit": 600000
        }
        w = self._wallet()
        w.paymaster = pm
        w.w3.eth.chain_id = 8453
        w.w3.eth.gas_price = 1_000_000_000
        w.w3.eth.get_code.return_value = b"\x60\x60"
        with patch.object(w, "_submit_to_bundler", return_value="0xuohash"):
            res = w.send_user_op(to="0xdest", sender="0xsender")
        assert res.user_op_hash == "0xuohash"
        pm.get_paymaster_data.assert_called_once()

    def test_submit_to_bundler_success(self):
        w = self._wallet()
        op = UserOperation(sender="0xa", nonce=0)
        resp = MagicMock()
        resp.json.return_value = {"result": "0xuoh"}
        with patch("requests.post", return_value=resp):
            assert w._submit_to_bundler(op) == "0xuoh"

    def test_submit_to_bundler_with_api_key(self):
        with patch("web3.Web3"):
            w = AAWallet(rpc_url="https://x", chain="base", api_key="secret")
        w.w3 = MagicMock()
        op = UserOperation(sender="0xa", nonce=0)
        resp = MagicMock()
        resp.json.return_value = {"result": "0xuoh"}
        with patch("requests.post", return_value=resp) as mock_post:
            assert w._submit_to_bundler(op) == "0xuoh"
            headers = mock_post.call_args.kwargs["headers"]
            assert "Authorization" in headers

    def test_submit_to_bundler_error(self):
        w = self._wallet()
        op = UserOperation(sender="0xa", nonce=0)
        resp = MagicMock()
        resp.json.return_value = {"error": {"message": "bad op"}}
        with patch("requests.post", return_value=resp):
            with pytest.raises(ValueError, match="Bundler error"):
                w._submit_to_bundler(op)

    def test_get_account_info(self):
        w = self._wallet()
        w.w3.eth.get_code.return_value = b"\x60\x60\x60"
        w.w3.eth.get_balance.return_value = 10 ** 18
        w.w3.from_wei.return_value = 1.0
        info = w.get_account_info("0xacct")
        assert info.deployed is True
        assert info.balance == 1.0


class TestAAPaymaster:
    def test_get_paymaster_data_default(self):
        pm = AAPaymaster(paymaster_type="unknown")
        op = UserOperation(sender="0xa", nonce=0, verification_gas_limit=1000)
        data = pm.get_paymaster_data(op, "0xep", 1)
        assert data["paymasterAndData"] == "0x"
        assert data["verificationGasLimit"] == 1000

    def test_token_paymaster(self):
        pm = AAPaymaster(paymaster_type="token")
        op = UserOperation(sender="0xa", nonce=0, verification_gas_limit=2000)
        data = pm.get_paymaster_data(op, "0xep", 1)
        assert data["verificationGasLimit"] == 2000

    def test_verifying_paymaster_missing_config(self):
        pm = AAPaymaster(paymaster_type="verifying")
        op = UserOperation(sender="0xa", nonce=0)
        with pytest.raises(ValueError, match="URL and API key required"):
            pm.get_paymaster_data(op, "0xep", 1)

    def test_verifying_paymaster_success(self):
        pm = AAPaymaster(
            paymaster_type="verifying", url="https://pm", api_key="k", policy_id="p1"
        )
        op = UserOperation(sender="0xa", nonce=0)
        resp = MagicMock()
        resp.json.return_value = {
            "result": {"paymasterAndData": "0xpmdata", "verificationGasLimit": "0x186a0"}
        }
        with patch("requests.post", return_value=resp) as mock_post:
            data = pm.get_paymaster_data(op, "0xep", 1)
            # policy id was injected into params
            sent = mock_post.call_args.kwargs["json"]
            assert sent["params"][0]["sponsorshipPolicyId"] == "p1"
        assert data["paymasterAndData"] == "0xpmdata"
        assert data["verificationGasLimit"] == 100000

    def test_verifying_paymaster_error(self):
        pm = AAPaymaster(paymaster_type="verifying", url="https://pm", api_key="k")
        op = UserOperation(sender="0xa", nonce=0)
        resp = MagicMock()
        resp.json.return_value = {"error": {"message": "no policy"}}
        with patch("requests.post", return_value=resp):
            with pytest.raises(ValueError, match="Paymaster error"):
                pm.get_paymaster_data(op, "0xep", 1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
