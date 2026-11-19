"""Multi-wallet farming: rotation, freezing, the daily cap and the result shapes.

The farmer is a planner — it marks what is already done and reports what is left.
These tests pin the accounting that the log line and the per-day cap depend on.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from web3_agent_kit.airdrop.base import AirdropCampaign, AirdropTask, TaskStatus, TaskType
from web3_agent_kit.airdrop.multi_wallet import AirdropFarmer, SybilAvoidanceConfig


class _Manager:
    def __init__(self, wallets):
        self._wallets = wallets
        self.group_seen = []

    def list_wallets(self, group=""):
        self.group_seen.append(group)
        return [SimpleNamespace(label=label, address=addr) for label, addr in self._wallets]


def _farmer(wallets=(("a", "0xa"), ("b", "0xb")), **cfg) -> AirdropFarmer:
    config = SybilAvoidanceConfig(shuffle_wallet_order=False, **cfg)
    return AirdropFarmer(wallet_manager=_Manager(list(wallets)), config=config)


def _campaign(statuses=()):
    tasks = [
        AirdropTask(f"t{i}", "p", TaskType.CUSTOM, f"task {i}", points=10)
        for i in range(len(statuses))
    ]
    for task, status in zip(tasks, statuses):
        task.status = status
    return AirdropCampaign("c1", "p", "campaign", tasks=tasks)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def _nop(*a, **k):
        return None

    monkeypatch.setattr("web3_agent_kit.airdrop.multi_wallet.asyncio.sleep", _nop)


class TestWallets:
    def test_wallets_come_from_the_group(self):
        farmer = _farmer()
        farmer.get_wallets()
        assert farmer.wallet_manager.group_seen == ["airdrop"]

    def test_without_a_manager_there_are_none(self):
        assert AirdropFarmer().get_wallets() == []

    def test_a_frozen_wallet_is_excluded(self):
        farmer = _farmer()
        farmer.freeze_wallet("a")
        assert farmer.get_wallets() == ["b"]

    def test_unfreezing_restores_it(self):
        farmer = _farmer()
        farmer.freeze_wallet("a")
        farmer.unfreeze_wallet("a")
        assert farmer.get_wallets() == ["a", "b"]

    def test_unfreezing_an_unknown_wallet_is_harmless(self):
        assert _farmer().unfreeze_wallet("zzz") is None

    def test_shuffling_keeps_everyone(self):
        farmer = _farmer()
        farmer.config.shuffle_wallet_order = True
        assert sorted(farmer.get_wallets()) == ["a", "b"]


class TestFarm:
    def test_every_wallet_gets_a_result(self):
        results = asyncio.run(_farmer().farm_campaign(_campaign([TaskStatus.PENDING])))
        assert [r.wallet_label for r in results] == ["a", "b"]

    def test_completed_tasks_are_counted_and_scored(self):
        results = asyncio.run(
            _farmer().farm_campaign(_campaign([TaskStatus.COMPLETED, TaskStatus.COMPLETED]))
        )
        assert results[0].tasks_completed == 2
        assert results[0].points_earned == 20

    def test_a_finished_campaign_is_success_in_plan_mode(self):
        results = asyncio.run(_farmer().farm_campaign(_campaign([TaskStatus.COMPLETED])))
        assert results[0].success is True and results[0].errors == []

    def test_a_pending_campaign_is_not_success_in_plan_mode(self):
        results = asyncio.run(_farmer().farm_campaign(_campaign([TaskStatus.PENDING])))
        assert results[0].success is False

    def test_execute_reports_each_pending_task(self):
        campaign = _campaign([TaskStatus.PENDING, TaskStatus.PENDING])
        results = asyncio.run(_farmer().farm_campaign(campaign, execute=True))
        assert len(results[0].errors) == 2
        assert all("not implemented" in e for e in results[0].errors)

    def test_a_completed_campaign_is_recorded_once(self):
        farmer = _farmer(wallets=(("a", "0xa"),))
        campaign = _campaign([TaskStatus.COMPLETED])
        asyncio.run(farmer.farm_campaign(campaign))
        asyncio.run(farmer.farm_campaign(campaign))
        assert farmer._progress["a"].campaigns_completed == ["c1"]

    def test_the_daily_cap_stops_a_wallet(self):
        farmer = _farmer(max_tasks_per_wallet_per_day=1)
        campaign = _campaign([TaskStatus.PENDING])
        assert len(asyncio.run(farmer.farm_campaign(campaign, execute=True))) == 2
        assert asyncio.run(farmer.farm_campaign(campaign, execute=True)) == []

    def test_the_daily_counter_only_moves_on_execute(self):
        farmer = _farmer()
        asyncio.run(farmer.farm_campaign(_campaign([TaskStatus.PENDING])))
        assert farmer._daily_task_counts == {}
        asyncio.run(farmer.farm_campaign(_campaign([TaskStatus.PENDING]), execute=True))
        assert farmer._daily_task_counts == {"a": 1, "b": 1}

    def test_the_daily_count_resets_after_a_day(self, monkeypatch):
        farmer = _farmer()
        farmer._daily_task_counts = {"a": 9}
        farmer._last_count_reset = 0.0
        farmer._reset_daily_counts_if_needed()
        assert farmer._daily_task_counts == {}

    def test_both_entry_points_agree(self):
        campaign = _campaign([TaskStatus.COMPLETED])
        one = asyncio.run(_farmer().farm_campaign(campaign))
        two = asyncio.run(_farmer().async_farm_campaign(campaign))
        assert [r.tasks_completed for r in one] == [r.tasks_completed for r in two]


class TestProgress:
    def test_a_single_wallet_lookup(self):
        farmer = _farmer()
        asyncio.run(farmer.farm_campaign(_campaign([TaskStatus.COMPLETED])))
        assert farmer.get_progress("a")["tasks_completed"] == 1

    def test_an_unknown_wallet_is_empty(self):
        assert _farmer().get_progress("zzz") == {}

    def test_the_whole_map_carries_no_timestamp(self):
        farmer = _farmer()
        asyncio.run(farmer.farm_campaign(_campaign([TaskStatus.COMPLETED])))
        assert "last_active" not in farmer.get_progress()["a"]

    def test_total_points_sums_wallets(self):
        farmer = _farmer()
        asyncio.run(farmer.farm_campaign(_campaign([TaskStatus.COMPLETED])))
        assert farmer.get_total_points() == 20
