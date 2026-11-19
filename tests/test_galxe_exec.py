"""Galxe executor: URL ids, task-type mapping and task parsing.

Parsing is wrapped in a bare ``except`` that returns ``None``, so a field that
fails to coerce silently drops the task from the campaign instead of erroring.
The tests pin the fields that used to do that.
"""

from __future__ import annotations

import json

import pytest

from web3_agent_kit.airdrop.executor.galxe_exec import GalxeExecutor


def _executor() -> GalxeExecutor:
    executor = GalxeExecutor()
    executor._campaign_id = "camp1"
    return executor


class TestCampaignId:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://app.galxe.com/quest/abc123", "abc123"),
            ("https://app.galxe.com/campaign/xyz", "xyz"),
            ("https://app.galxe.com/quest/abc/extra", "abc"),
            ("https://app.galxe.com/other/seg", "seg"),
            ("https://app.galxe.com", "unknown"),
        ],
    )
    def test_id_is_extracted(self, url, expected):
        assert _executor()._extract_galxe_id(url) == expected


class TestTaskTypeMapping:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("twitter_follow", "twitter_follow"),
            ("twitter_tweet", "twitter_comment"),
            ("discord_join", "discord_join"),
            ("on_chain", "on_chain_tx"),
            ("on-chain-swap", "on_chain_swap"),
            ("ON_CHAIN_BRIDGE", "on_chain_bridge"),
            ("nft_hold", "custom"),
            ("something_new", "custom"),
        ],
    )
    def test_mapping(self, raw, expected):
        assert _executor()._map_task_type(raw) == expected


class TestParseTask:
    def test_a_full_task_is_parsed(self):
        data = {
            "id": "t9",
            "name": "Swap on Base",
            "type": "on_chain_swap",
            "description": "d",
            "status": "COMPLETED",
            "credential": {"id": 12},
            "attribute": {"points": "15", "chainId": 8453, "contractAddress": "0xabc"},
        }
        task = _executor()._parse_task(data, 0)
        assert task.task_id == "galxe_camp1_t9"
        assert task.points == 15
        assert task.is_completed is True
        assert task.credential_id == "12"
        assert task.chain_id == 8453

    def test_on_chain_tasks_are_medium_and_bridges_are_hard(self):
        assert _executor()._parse_task({"type": "on_chain_swap"}, 0).difficulty.value == "medium"
        assert _executor()._parse_task({"type": "on_chain_bridge"}, 0).difficulty.value == "hard"
        assert _executor()._parse_task({"type": "quiz"}, 0).difficulty.value == "easy"

    @pytest.mark.parametrize("points", ["", None, "not-a-number", {}, 0])
    def test_unusable_points_do_not_drop_the_task(self, points):
        # int(None) and int("") raise, and the bare except used to swallow the
        # whole task instead of just the points.
        task = _executor()._parse_task({"id": "t", "attribute": {"points": points}}, 0)
        assert task is not None
        assert task.points == 0

    def test_a_null_id_falls_back_to_the_index(self):
        task = _executor()._parse_task({"id": None}, 4)
        assert task.task_id == "galxe_camp1_4"
        assert task.task_id_galxe == "4"

    def test_attribute_as_a_json_string_is_decoded(self):
        task = _executor()._parse_task({"attribute": json.dumps({"points": 7})}, 0)
        assert task.points == 7

    def test_a_broken_attribute_string_becomes_empty(self):
        task = _executor()._parse_task({"attribute": "{not json"}, 0)
        assert task.points == 0

    def test_unverified_status_is_not_completed(self):
        assert _executor()._parse_task({"status": "active"}, 0).is_completed is False

    def test_metadata_carries_the_campaign(self):
        task = _executor()._parse_task({"attribute": {"points": 1}}, 0)
        assert task.metadata["campaign_id"] == "camp1"


class TestGraphql:
    def test_auth_token_becomes_a_bearer_header(self, monkeypatch):
        executor = _executor()
        executor._auth_token = "tok"
        captured = {}

        def post(url, **kwargs):
            captured.update(kwargs)
            return type("R", (), {"json": lambda s: {"data": {}}})()

        monkeypatch.setattr(executor, "_post", post, raising=False)
        executor._graphql_query("query {}", {"a": 1})
        assert captured["headers"]["Authorization"] == "Bearer tok"
        assert captured["json"]["variables"] == {"a": 1}

    def test_without_a_token_there_is_no_auth_header(self, monkeypatch):
        executor = _executor()
        executor._auth_token = ""
        captured = {}

        def post(url, **kwargs):
            captured.update(kwargs)
            return type("R", (), {"json": lambda s: {}})()

        monkeypatch.setattr(executor, "_post", post, raising=False)
        executor._graphql_query("query {}", {})
        assert "Authorization" not in captured["headers"]
