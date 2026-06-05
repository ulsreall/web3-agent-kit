"""Tests for airdrop automation module."""

import json
import os
import time

import pytest

from src.airdrop.base import (
    AirdropCampaign,
    AirdropTask,
    PlatformConfig,
    TaskStatus,
    TaskType,
)
from src.airdrop.gleam import GleamCampaign
from src.airdrop.zealy import ZealyPlatform, ZealyLeaderboardEntry
from src.airdrop.galxe import GalxePlatform, GalxeCredential
from src.airdrop.social import (
    SocialTaskManager,
    SocialAccount,
    SocialPlatform,
    TwitterHelper,
    DiscordHelper,
    TelegramHelper,
    YouTubeHelper,
    GitHubHelper,
)
from src.airdrop.tracker import AirdropTracker, AirdropReward
from src.airdrop.multi_wallet import (
    AirdropFarmer,
    SybilAvoidanceConfig,
    WalletFarmProgress,
)


# === Base Module Tests ===


class TestTaskType:
    def test_task_types_exist(self):
        assert TaskType.SOCIAL_TWITTER_FOLLOW.value == "twitter_follow"
        assert TaskType.SOCIAL_DISCORD_JOIN.value == "discord_join"
        assert TaskType.ON_CHAIN_TX.value == "on_chain_tx"
        assert TaskType.QUIZ.value == "quiz"

    def test_social_flag(self):
        task = AirdropTask(
            task_id="1", platform="test",
            task_type=TaskType.SOCIAL_TWITTER_FOLLOW, title="Follow"
        )
        assert task.is_social is True
        assert task.is_on_chain is False

    def test_on_chain_flag(self):
        task = AirdropTask(
            task_id="1", platform="test",
            task_type=TaskType.ON_CHAIN_SWAP, title="Swap"
        )
        assert task.is_on_chain is True
        assert task.is_social is False


class TestAirdropTask:
    def test_default_status(self):
        task = AirdropTask(task_id="1", platform="test", task_type=TaskType.VISIT_URL, title="Visit")
        assert task.status == TaskStatus.PENDING
        assert task.completed_at is None

    def test_metadata(self):
        task = AirdropTask(
            task_id="1", platform="test", task_type=TaskType.CUSTOM,
            title="Custom", metadata={"key": "value"}
        )
        assert task.metadata["key"] == "value"


class TestAirdropCampaign:
    def test_progress_empty(self):
        campaign = AirdropCampaign(campaign_id="1", platform="test", name="Test")
        assert campaign.progress == 0.0

    def test_progress_partial(self):
        campaign = AirdropCampaign(
            campaign_id="1", platform="test", name="Test",
            total_points=100, earned_points=50,
        )
        assert campaign.progress == 0.5

    def test_is_expired_no_deadline(self):
        campaign = AirdropCampaign(campaign_id="1", platform="test", name="Test")
        assert campaign.is_expired is False

    def test_is_expired_past(self):
        campaign = AirdropCampaign(
            campaign_id="1", platform="test", name="Test",
            deadline=time.time() - 3600,
        )
        assert campaign.is_expired is True

    def test_is_expired_future(self):
        campaign = AirdropCampaign(
            campaign_id="1", platform="test", name="Test",
            deadline=time.time() + 3600,
        )
        assert campaign.is_expired is False


class TestPlatformConfig:
    def test_defaults(self):
        config = PlatformConfig()
        assert config.rate_limit_delay == 2.0
        assert config.max_retries == 3
        assert config.timeout == 30
        assert "Chrome" in config.user_agent

    def test_custom(self):
        config = PlatformConfig(rate_limit_delay=5.0, max_retries=5, proxy="http://proxy:8080")
        assert config.rate_limit_delay == 5.0
        assert config.max_retries == 5
        assert config.proxy == "http://proxy:8080"


# === Gleam Tests ===


class TestGleamCampaign:
    def test_init(self):
        campaign = GleamCampaign()
        assert campaign.platform_name == "gleam"

    def test_login_success(self):
        campaign = GleamCampaign()
        result = campaign.login({"session_cookie": "test_cookie"})
        assert result is True

    def test_login_no_creds(self):
        campaign = GleamCampaign()
        result = campaign.login({})
        assert result is False

    def test_extract_contest_id(self):
        campaign = GleamCampaign()
        cid = campaign._extract_contest_id("https://gleam.io/abc123/contest")
        assert cid == "abc123"

    def test_map_method(self):
        campaign = GleamCampaign()
        assert campaign._map_method_to_task_type("twitter_follow") == TaskType.SOCIAL_TWITTER_FOLLOW
        assert campaign._map_method_to_task_type("discord_join") == TaskType.SOCIAL_DISCORD_JOIN
        assert campaign._map_method_to_task_type("unknown_method") == TaskType.CUSTOM


# === Zealy Tests ===


class TestZealyPlatform:
    def test_init(self):
        zealy = ZealyPlatform()
        assert zealy.platform_name == "zealy"

    def test_login_success(self):
        zealy = ZealyPlatform()
        result = zealy.login({"api_key": "test_key"})
        assert result is True

    def test_login_no_creds(self):
        zealy = ZealyPlatform()
        result = zealy.login({})
        assert result is False

    def test_total_xp(self):
        zealy = ZealyPlatform()
        assert zealy.get_total_xp() == 0

    def test_map_quest_type(self):
        zealy = ZealyPlatform()
        assert zealy._map_quest_type("twitter_follow") == TaskType.SOCIAL_TWITTER_FOLLOW
        assert zealy._map_quest_type("on_chain") == TaskType.ON_CHAIN_TX
        assert zealy._map_quest_type("quiz") == TaskType.QUIZ


# === Galxe Tests ===


class TestGalxePlatform:
    def test_init(self):
        galxe = GalxePlatform()
        assert galxe.platform_name == "galxe"

    def test_login_success(self):
        galxe = GalxePlatform()
        result = galxe.login({"api_key": "test_key"})
        assert result is True

    def test_get_points_empty(self):
        galxe = GalxePlatform()
        assert galxe.get_points() == {}

    def test_map_task_type(self):
        galxe = GalxePlatform()
        assert galxe._map_task_type("twitter_follow") == TaskType.SOCIAL_TWITTER_FOLLOW
        assert galxe._map_task_type("on_chain") == TaskType.ON_CHAIN_TX
        assert galxe._map_task_type("swap") == TaskType.ON_CHAIN_SWAP


# === Social Helper Tests ===


class TestTwitterHelper:
    def test_follow(self):
        helper = TwitterHelper()
        result = helper.follow("test_user")
        assert result.success is True
        assert result.target == "test_user"
        assert len(helper.get_completed()) == 1

    def test_retweet(self):
        helper = TwitterHelper()
        result = helper.retweet("https://twitter.com/user/status/123")
        assert result.success is True

    def test_like(self):
        helper = TwitterHelper()
        result = helper.like("https://twitter.com/user/status/123")
        assert result.success is True

    def test_comment(self):
        helper = TwitterHelper()
        result = helper.comment("https://twitter.com/user/status/123", "Great!")
        assert result.success is True


class TestDiscordHelper:
    def test_join(self):
        helper = DiscordHelper()
        result = helper.join_server("https://discord.gg/test")
        assert result.success is True
        assert len(helper.get_completed()) == 1

    def test_verify(self):
        helper = DiscordHelper()
        result = helper.verify("123456789")
        assert result.success is True


class TestTelegramHelper:
    def test_join(self):
        helper = TelegramHelper()
        result = helper.join_channel("https://t.me/test")
        assert result.success is True


class TestGitHubHelper:
    def test_star(self):
        helper = GitHubHelper()
        result = helper.star("user/repo")
        assert result.success is True
        assert result.target == "user/repo"

    def test_fork(self):
        helper = GitHubHelper()
        result = helper.fork("user/repo")
        assert result.success is True


class TestSocialTaskManager:
    def test_complete_task(self):
        manager = SocialTaskManager()
        result = manager.complete_social_task(
            TaskType.SOCIAL_TWITTER_FOLLOW, "test_user"
        )
        assert result.success is True
        assert len(manager.get_all_results()) == 1

    def test_unsupported_task(self):
        manager = SocialTaskManager()
        result = manager.complete_social_task(TaskType.ON_CHAIN_TX, "0x123")
        assert result.success is False

    def test_add_account(self):
        manager = SocialTaskManager()
        account = SocialAccount(SocialPlatform.TWITTER, "testuser")
        manager.add_account(account)
        assert len(manager.accounts) == 1

    def test_completed_count(self):
        manager = SocialTaskManager()
        manager.complete_social_task(TaskType.SOCIAL_TWITTER_FOLLOW, "user1")
        manager.complete_social_task(TaskType.SOCIAL_DISCORD_JOIN, "server1")
        counts = manager.get_completed_count()
        assert counts.get("twitter", 0) == 1
        assert counts.get("discord", 0) == 1


# === Tracker Tests ===


class TestAirdropTracker:
    def test_add_campaign(self, tmp_path):
        tracker = AirdropTracker(str(tmp_path / "test.json"))
        campaign = AirdropCampaign(
            campaign_id="test1", platform="galxe",
            name="Test Campaign", total_points=100,
        )
        tracker.add_campaign(campaign)
        assert len(tracker.list_campaigns()) == 1

    def test_mark_task_completed(self, tmp_path):
        tracker = AirdropTracker(str(tmp_path / "test.json"))
        task = AirdropTask(
            task_id="t1", platform="galxe",
            task_type=TaskType.SOCIAL_TWITTER_FOLLOW,
            title="Follow", points=10,
        )
        campaign = AirdropCampaign(
            campaign_id="c1", platform="galxe",
            name="Test", total_points=100, tasks=[task],
        )
        tracker.add_campaign(campaign)
        tracker.mark_task_completed(task)

        c = tracker.get_campaign("c1")
        assert c is not None
        assert c.earned_points == 10

    def test_add_reward(self, tmp_path):
        tracker = AirdropTracker(str(tmp_path / "test.json"))
        reward = AirdropReward(
            platform="galxe", campaign_id="c1",
            campaign_name="Test", points=100,
        )
        tracker.add_reward(reward)
        assert len(tracker.rewards) == 1

    def test_get_summary(self, tmp_path):
        tracker = AirdropTracker(str(tmp_path / "test.json"))
        tracker.add_campaign(AirdropCampaign(
            campaign_id="c1", platform="galxe", name="Test 1",
        ))
        summary = tracker.get_summary()
        assert summary.total_campaigns == 1

    def test_export_json(self, tmp_path):
        tracker = AirdropTracker(str(tmp_path / "test.json"))
        tracker.add_campaign(AirdropCampaign(
            campaign_id="c1", platform="galxe", name="Test",
        ))
        out_path = str(tmp_path / "export.json")
        tracker.export_json(out_path)
        assert os.path.exists(out_path)
        with open(out_path) as f:
            data = json.load(f)
        assert "c1" in data["campaigns"]

    def test_export_csv(self, tmp_path):
        tracker = AirdropTracker(str(tmp_path / "test.json"))
        tracker.add_campaign(AirdropCampaign(
            campaign_id="c1", platform="galxe", name="Test",
        ))
        out_path = str(tmp_path / "export.csv")
        tracker.export_csv(out_path)
        assert os.path.exists(out_path)

    def test_upcoming_deadlines(self, tmp_path):
        tracker = AirdropTracker(str(tmp_path / "test.json"))
        tracker.add_campaign(AirdropCampaign(
            campaign_id="c1", platform="galxe", name="Soon",
            deadline=time.time() + 3600,
        ))
        tracker.add_campaign(AirdropCampaign(
            campaign_id="c2", platform="galxe", name="Later",
            deadline=time.time() + 86400 * 7,
        ))
        upcoming = tracker.get_upcoming_deadlines(within_hours=48)
        assert len(upcoming) == 1
        assert upcoming[0].name == "Soon"

    def test_list_by_platform(self, tmp_path):
        tracker = AirdropTracker(str(tmp_path / "test.json"))
        tracker.add_campaign(AirdropCampaign(campaign_id="c1", platform="galxe", name="G"))
        tracker.add_campaign(AirdropCampaign(campaign_id="c2", platform="zealy", name="Z"))
        galxe_only = tracker.list_campaigns(platform="galxe")
        assert len(galxe_only) == 1


# === Multi-Wallet Farmer Tests ===


class TestAirdropFarmer:
    def test_init(self):
        farmer = AirdropFarmer()
        assert farmer.config.min_delay_between_wallets == 30.0

    def test_custom_config(self):
        config = SybilAvoidanceConfig(
            min_delay_between_wallets=60,
            max_tasks_per_wallet_per_day=5,
        )
        farmer = AirdropFarmer(config=config)
        assert farmer.config.min_delay_between_wallets == 60

    def test_get_wallets_no_manager(self):
        farmer = AirdropFarmer()
        assert farmer.get_wallets() == []

    def test_freeze_unfreeze(self):
        farmer = AirdropFarmer()
        farmer.freeze_wallet("wallet1")
        assert farmer._progress["wallet1"].is_frozen is True
        farmer.unfreeze_wallet("wallet1")
        assert farmer._progress["wallet1"].is_frozen is False

    def test_farm_campaign_no_wallets(self):
        farmer = AirdropFarmer()
        campaign = AirdropCampaign(
            campaign_id="c1", platform="test", name="Test",
            tasks=[AirdropTask(task_id="t1", platform="test", task_type=TaskType.VISIT_URL, title="Visit")],
        )
        results = farmer.farm_campaign(campaign, execute=True)
        assert results == []

    def test_get_progress_empty(self):
        farmer = AirdropFarmer()
        assert farmer.get_progress() == {}

    def test_get_total_points(self):
        farmer = AirdropFarmer()
        assert farmer.get_total_points() == 0

    def test_sybil_config_defaults(self):
        config = SybilAvoidanceConfig()
        assert config.shuffle_wallet_order is True
        assert config.max_tasks_per_wallet_per_day == 10

    def test_wallet_farm_progress(self):
        progress = WalletFarmProgress(wallet_label="w1", wallet_address="0x123")
        assert progress.is_frozen is False
        assert progress.tasks_completed == 0
