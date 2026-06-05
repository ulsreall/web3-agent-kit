"""Tests for new airdrop modules: discovery, onchain, scheduler, dashboard, referral, faucet."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.airdrop.discovery import (
    CampaignDiscovery,
    DiscoveryConfig,
    DiscoveredCampaign,
    CampaignStatus,
    CampaignCategory,
)
from src.airdrop.onchain import (
    OnChainAirdropFarmer,
    OnChainConfig,
    TransactionResult,
    Chain,
    DeFiProtocol,
    FARMING_PLANS,
)
from src.airdrop.scheduler import (
    AirdropScheduler,
    SchedulerConfig,
    ScheduledTask,
    ScheduleFrequency,
    TaskExecutionStatus,
)
from src.airdrop.dashboard import (
    PointsDashboard,
    DashboardConfig,
    PlatformPoints,
    PointsSnapshot,
)
from src.airdrop.referral import (
    ReferralManager,
    ReferralLink,
    ReferralPlatform,
    ReferralStats,
)
from src.airdrop.faucet import (
    FaucetClaimer,
    FaucetConfig,
    ClaimResult,
    FAUCETS,
)


# ─── Discovery Tests ─────────────────────────────────────────────


class TestCampaignDiscovery:
    """Test campaign discovery module."""

    def test_init(self):
        discovery = CampaignDiscovery()
        assert discovery.config is not None
        assert discovery.session is not None

    def test_init_with_config(self):
        config = DiscoveryConfig(
            platforms=["galxe", "zealy"],
            min_points=10,
            active_only=True,
        )
        discovery = CampaignDiscovery(config)
        assert discovery.config.platforms == ["galxe", "zealy"]
        assert discovery.config.min_points == 10

    def test_discovered_campaign_creation(self):
        campaign = DiscoveredCampaign(
            platform="galxe",
            campaign_id="123",
            title="Test Campaign",
            url="https://app.galxe.com/quest/123",
            points=100,
        )
        assert campaign.platform == "galxe"
        assert campaign.points == 100
        assert campaign.is_high_value is True

    def test_discovered_campaign_low_value(self):
        campaign = DiscoveredCampaign(
            platform="galxe",
            campaign_id="123",
            title="Low Value",
            url="https://app.galxe.com/quest/123",
            points=10,
        )
        assert campaign.is_high_value is False

    def test_discovered_campaign_ending_soon(self):
        from datetime import timedelta
        campaign = DiscoveredCampaign(
            platform="galxe",
            campaign_id="123",
            title="Ending Soon",
            url="https://app.galxe.com/quest/123",
            end_time=datetime.now(timezone.utc) + timedelta(hours=12),
        )
        assert campaign.is_ending_soon is True

    def test_discovered_campaign_to_dict(self):
        campaign = DiscoveredCampaign(
            platform="galxe",
            campaign_id="123",
            title="Test",
            url="https://app.galxe.com/quest/123",
            points=50,
        )
        d = campaign.to_dict()
        assert d["platform"] == "galxe"
        assert d["points"] == 50

    def test_export_urls(self):
        discovery = CampaignDiscovery()
        campaigns = [
            DiscoveredCampaign(
                platform="galxe",
                campaign_id="1",
                title="A",
                url="https://a.com",
            ),
            DiscoveredCampaign(
                platform="zealy",
                campaign_id="2",
                title="B",
                url="https://b.com",
            ),
        ]
        urls = discovery.export_urls(campaigns)
        assert urls == ["https://a.com", "https://b.com"]

    def test_export_json(self):
        discovery = CampaignDiscovery()
        campaigns = [
            DiscoveredCampaign(
                platform="galxe",
                campaign_id="1",
                title="Test",
                url="https://test.com",
                points=100,
            ),
        ]
        json_str = discovery.export_json(campaigns)
        data = json.loads(json_str)
        assert data["total"] == 1
        assert data["campaigns"][0]["platform"] == "galxe"


# ─── On-chain Tests ──────────────────────────────────────────────


class TestOnChainAirdropFarmer:
    """Test on-chain airdrop module."""

    def test_init(self):
        config = OnChainConfig(chain="base", dry_run=True)
        farmer = OnChainAirdropFarmer(config)
        assert farmer.config.chain == "base"
        assert farmer.config.dry_run is True

    def test_get_plans_for_chain(self):
        config = OnChainConfig(chain="base", dry_run=True)
        farmer = OnChainAirdropFarmer(config)
        plans = farmer.get_plans_for_chain("base")
        assert len(plans) > 0
        assert plans[0].chain == Chain.BASE

    def test_get_all_plans(self):
        config = OnChainConfig(dry_run=True)
        farmer = OnChainAirdropFarmer(config)
        plans = farmer.get_all_plans()
        assert "base_activity" in plans
        assert "eigenlayer_restake" in plans

    def test_dry_run_swap(self):
        config = OnChainConfig(chain="base", dry_run=True)
        farmer = OnChainAirdropFarmer(config)
        result = farmer.execute_swap(
            chain="base",
            protocol="aerodrome",
            token_in="ETH",
            token_out="USDC",
            amount_in=0.001,
        )
        assert result.success is True
        assert result.tx_hash == "0xDRY_RUN"

    def test_dry_run_bridge(self):
        config = OnChainConfig(dry_run=True)
        farmer = OnChainAirdropFarmer(config)
        result = farmer.execute_bridge(
            from_chain="base",
            to_chain="ethereum",
            amount_eth=0.001,
        )
        assert result.success is True

    def test_dry_run_lend(self):
        config = OnChainConfig(dry_run=True)
        farmer = OnChainAirdropFarmer(config)
        result = farmer.execute_lend(
            chain="ethereum",
            protocol="aave_v3",
            asset="USDC",
            amount=100,
            action="supply",
        )
        assert result.success is True

    def test_dry_run_stake(self):
        config = OnChainConfig(dry_run=True)
        farmer = OnChainAirdropFarmer(config)
        result = farmer.execute_stake(
            chain="ethereum",
            protocol="eigenlayer",
            amount_eth=0.01,
        )
        assert result.success is True

    def test_get_summary(self):
        config = OnChainConfig(dry_run=True)
        farmer = OnChainAirdropFarmer(config)
        farmer.execute_swap("base", "aerodrome", "ETH", "USDC", 0.001)
        summary = farmer.get_summary()
        assert summary["total_transactions"] == 1
        assert summary["successful"] == 1

    def test_transaction_result_to_dict(self):
        result = TransactionResult(
            protocol="aerodrome",
            action="swap",
            chain="base",
            success=True,
            tx_hash="0x123",
        )
        d = result.to_dict()
        assert d["protocol"] == "aerodrome"
        assert d["success"] is True

    def test_farming_plans_exist(self):
        assert "base_activity" in FARMING_PLANS
        assert "eigenlayer_restake" in FARMING_PLANS
        assert "arbitrum_defi" in FARMING_PLANS
        assert "optimism_rpgf" in FARMING_PLANS


# ─── Scheduler Tests ─────────────────────────────────────────────


class TestAirdropScheduler:
    """Test scheduler module."""

    def test_init(self):
        scheduler = AirdropScheduler()
        assert scheduler.config is not None

    def test_add_daily(self):
        scheduler = AirdropScheduler()
        task = scheduler.add_daily(
            "test_daily",
            "09:00",
            lambda: None,
            name="Test Daily",
        )
        assert task.task_id == "test_daily"
        assert task.frequency == ScheduleFrequency.DAILY
        assert task.target_time == "09:00"

    def test_add_hourly(self):
        scheduler = AirdropScheduler()
        task = scheduler.add_hourly(
            "test_hourly",
            lambda: None,
        )
        assert task.frequency == ScheduleFrequency.HOURLY

    def test_add_weekly(self):
        scheduler = AirdropScheduler()
        task = scheduler.add_weekly(
            "test_weekly",
            0,  # Monday
            "10:00",
            lambda: None,
        )
        assert task.frequency == ScheduleFrequency.WEEKLY

    def test_add_custom(self):
        scheduler = AirdropScheduler()
        task = scheduler.add_custom(
            "test_custom",
            3600,
            lambda: None,
        )
        assert task.frequency == ScheduleFrequency.CUSTOM

    def test_remove_task(self):
        scheduler = AirdropScheduler()
        scheduler.add_daily("test", "09:00", lambda: None)
        assert scheduler.remove_task("test") is True
        assert scheduler.get_task("test") is None

    def test_enable_disable(self):
        scheduler = AirdropScheduler()
        scheduler.add_daily("test", "09:00", lambda: None)
        scheduler.disable_task("test")
        assert scheduler.get_task("test").enabled is False
        scheduler.enable_task("test")
        assert scheduler.get_task("test").enabled is True

    def test_run_task_now(self):
        scheduler = AirdropScheduler()
        result = []

        def test_fn():
            result.append("executed")

        scheduler.add_daily("test", "09:00", test_fn)
        log = scheduler.run_task_now("test")
        assert log is not None
        assert log.status == TaskExecutionStatus.SUCCESS
        assert len(result) == 1

    def test_run_task_with_error(self):
        scheduler = AirdropScheduler()

        def failing_fn():
            raise ValueError("Test error")

        scheduler.add_daily("test", "09:00", failing_fn, max_retries=1)
        log = scheduler.run_task_now("test")
        assert log.status == TaskExecutionStatus.FAILED

    def test_get_summary(self):
        scheduler = AirdropScheduler()
        scheduler.add_daily("test1", "09:00", lambda: None)
        scheduler.add_daily("test2", "10:00", lambda: None)
        summary = scheduler.get_summary()
        assert summary["total_tasks"] == 2

    def test_scheduled_task_to_dict(self):
        task = ScheduledTask(
            task_id="test",
            name="Test",
            frequency=ScheduleFrequency.DAILY,
        )
        d = task.to_dict()
        assert d["task_id"] == "test"
        assert d["frequency"] == "daily"


# ─── Dashboard Tests ─────────────────────────────────────────────


class TestPointsDashboard:
    """Test points dashboard module."""

    def test_init(self):
        dashboard = PointsDashboard()
        assert dashboard.config is not None

    def test_platform_points(self):
        points = PlatformPoints(
            platform="galxe",
            points=1000,
            rank=50,
            campaigns_completed=10,
        )
        assert points.points == 1000
        assert points.total_with_referrals == 1000

    def test_points_snapshot(self):
        snapshot = PointsSnapshot(
            timestamp=datetime.now(timezone.utc),
            platforms={
                "galxe": PlatformPoints(platform="galxe", points=100),
                "zealy": PlatformPoints(platform="zealy", points=50),
            },
        )
        assert snapshot.total_points == 150

    def test_snapshot_to_dict(self):
        snapshot = PointsSnapshot(
            timestamp=datetime.now(timezone.utc),
            platforms={"galxe": PlatformPoints(platform="galxe", points=100)},
        )
        d = snapshot.to_dict()
        assert d["total_points"] == 100

    def test_export_json(self):
        dashboard = PointsDashboard(
            DashboardConfig(wallet_address="0x123")
        )
        # Set current manually
        dashboard._current = PointsSnapshot(
            timestamp=datetime.now(timezone.utc),
            platforms={"galxe": PlatformPoints(platform="galxe", points=100)},
        )
        json_str = dashboard.export_json()
        data = json.loads(json_str)
        assert data["wallet"] == "0x123"

    def test_print_summary_no_data(self):
        dashboard = PointsDashboard()
        result = dashboard.print_summary()
        assert "Not synced" in result

    def test_get_growth_no_history(self):
        dashboard = PointsDashboard()
        growth = dashboard.get_growth()
        assert growth["total_delta"] == 0


# ─── Referral Tests ──────────────────────────────────────────────


class TestReferralManager:
    """Test referral manager module."""

    def test_init(self):
        manager = ReferralManager()
        assert manager._links == []

    def test_add_platform(self):
        manager = ReferralManager()
        platform = manager.add_platform(
            "galxe",
            "https://app.galxe.com/quest",
            "ref",
            reward_per_referral=10,
        )
        assert platform.name == "galxe"
        assert platform.reward_per_referral == 10

    def test_add_known_platform(self):
        manager = ReferralManager()
        platform = manager.add_known_platform("galxe")
        assert platform is not None
        assert platform.name == "Galxe"

    def test_generate_links(self):
        manager = ReferralManager()
        manager.add_platform("galxe", "https://app.galxe.com/quest", "ref")
        links = manager.generate_links(platform="galxe", count=3)
        assert len(links) == 3
        assert all(l.platform == "galxe" for l in links)

    def test_generate_chain(self):
        manager = ReferralManager()
        manager.add_platform("galxe", "https://galxe.com", "ref")
        manager.add_platform("zealy", "https://zealy.io", "ref")
        chain = manager.generate_chain(
            ["galxe", "zealy"],
            wallet="0x123",
        )
        assert len(chain) == 2

    def test_record_click(self):
        manager = ReferralManager()
        manager.add_platform("galxe", "https://galxe.com", "ref")
        links = manager.generate_links(platform="galxe", count=1)
        code = links[0].code
        assert manager.record_click(code) is True
        assert links[0].clicks == 1

    def test_record_conversion(self):
        manager = ReferralManager()
        manager.add_platform("galxe", "https://galxe.com", "ref")
        links = manager.generate_links(platform="galxe", count=1)
        code = links[0].code
        assert manager.record_conversion(code, points=10) is True
        assert links[0].conversions == 1
        assert links[0].points_earned == 10

    def test_deactivate_link(self):
        manager = ReferralManager()
        manager.add_platform("galxe", "https://galxe.com", "ref")
        links = manager.generate_links(platform="galxe", count=1)
        code = links[0].code
        manager.deactivate_link(code)
        assert links[0].is_active is False

    def test_get_stats(self):
        manager = ReferralManager()
        manager.add_platform("galxe", "https://galxe.com", "ref")
        manager.generate_links(platform="galxe", count=5)
        stats = manager.get_stats()
        assert stats.total_links == 5

    def test_referral_link_to_dict(self):
        link = ReferralLink(
            platform="galxe",
            url="https://galxe.com?ref=abc",
            code="abc",
        )
        d = link.to_dict()
        assert d["platform"] == "galxe"

    def test_export_json(self):
        manager = ReferralManager()
        manager.add_platform("galxe", "https://galxe.com", "ref")
        manager.generate_links(platform="galxe", count=1)
        json_str = manager.export_json()
        data = json.loads(json_str)
        assert "stats" in data


# ─── Faucet Tests ────────────────────────────────────────────────


class TestFaucetClaimer:
    """Test faucet claimer module."""

    def test_init(self):
        claimer = FaucetClaimer()
        assert len(claimer._faucets) > 0

    def test_add_faucet(self):
        claimer = FaucetClaimer()
        config = FaucetConfig(
            name="Test Faucet",
            chain="test_chain",
            url="https://test.com",
        )
        claimer.add_faucet("test_chain", config)
        assert "test_chain" in claimer._faucets

    def test_get_all_faucets(self):
        claimer = FaucetClaimer()
        faucets = claimer.get_all_faucets()
        assert "base_sepolia" in faucets
        assert "ethereum_sepolia" in faucets

    def test_get_available(self):
        claimer = FaucetClaimer()
        available = claimer.get_available("0x123")
        assert len(available) > 0

    def test_claim_result_to_dict(self):
        result = ClaimResult(
            faucet="Test",
            chain="test",
            token="ETH",
            success=True,
            amount="0.1",
        )
        d = result.to_dict()
        assert d["success"] is True

    def test_faucet_config_to_dict(self):
        config = FaucetConfig(
            name="Test",
            chain="test",
            url="https://test.com",
        )
        d = config.to_dict()
        assert d["name"] == "Test"

    def test_print_results_empty(self):
        claimer = FaucetClaimer()
        result = claimer.print_results()
        assert "No results" in result

    def test_export_json(self):
        claimer = FaucetClaimer()
        claimer._results = [
            ClaimResult(
                faucet="Test",
                chain="test",
                token="ETH",
                success=True,
            ),
        ]
        json_str = claimer.export_json()
        data = json.loads(json_str)
        assert len(data["results"]) == 1

    def test_cooldown_check(self):
        claimer = FaucetClaimer()
        claimer._cooldowns.clear()  # Clear any loaded cooldowns
        assert claimer._in_cooldown("base_sepolia") is False
        claimer._set_cooldown("base_sepolia", 24)
        assert claimer._in_cooldown("base_sepolia") is True

    @patch("src.airdrop.faucet.requests.Session.post")
    def test_claim_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "txHash": "0x123"}
        mock_response.headers = {"content-type": "application/json"}
        mock_post.return_value = mock_response

        claimer = FaucetClaimer()
        results = claimer.claim_chain("base_sepolia", "0x123", skip_cooldown=True)
        assert len(results) == 1


# ─── Integration Test ────────────────────────────────────────────


class TestIntegration:
    """Test module integration."""

    def test_import_all_new_modules(self):
        from src.airdrop import (
            CampaignDiscovery,
            OnChainAirdropFarmer,
            AirdropScheduler,
            PointsDashboard,
            ReferralManager,
            FaucetClaimer,
        )
        assert CampaignDiscovery is not None
        assert OnChainAirdropFarmer is not None
        assert AirdropScheduler is not None
        assert PointsDashboard is not None
        assert ReferralManager is not None
        assert FaucetClaimer is not None

    def test_full_workflow_dry_run(self):
        # 1. Discover campaigns
        discovery = CampaignDiscovery()
        # (would normally scan, but just test init)

        # 2. On-chain farming
        config = OnChainConfig(chain="base", dry_run=True)
        farmer = OnChainAirdropFarmer(config)
        result = farmer.execute_swap("base", "aerodrome", "ETH", "USDC", 0.001)
        assert result.success

        # 3. Scheduler
        scheduler = AirdropScheduler()
        scheduler.add_daily("test", "09:00", lambda: "ok")
        assert len(scheduler.get_all_tasks()) == 1

        # 4. Referrals
        manager = ReferralManager()
        manager.add_platform("galxe", "https://galxe.com", "ref")
        links = manager.generate_links(count=1)
        assert len(links) == 1

        # 5. Faucet
        claimer = FaucetClaimer()
        available = claimer.get_available("0x123")
        assert len(available) > 0
