#!/usr/bin/env python3
"""Airdrop Automation Suite — full workflow example.

Demonstrates the complete airdrop automation pipeline:
1. Campaign Discovery — find new campaigns
2. On-chain Farming — DeFi interactions for airdrops
3. Daily Scheduler — automate recurring tasks
4. Points Dashboard — track points across platforms
5. Referral Manager — generate and track referrals
6. Faucet Claimer — claim testnet tokens

Usage:
    python examples/airdrop_suite.py
"""

from web3_agent_kit.airdrop import (
    # Discovery
    CampaignDiscovery,
    DiscoveryConfig,
    # On-chain
    OnChainAirdropFarmer,
    OnChainConfig,
    Chain,
    # Scheduler
    AirdropScheduler,
    # Dashboard
    PointsDashboard,
    DashboardConfig,
    # Referral
    ReferralManager,
    # Faucet
    FaucetClaimer,
)


def example_discovery():
    """Example: Discover new airdrop campaigns."""
    print("\n" + "=" * 60)
    print("🔍 CAMPAIGN DISCOVERY")
    print("=" * 60)

    # Configure discovery
    config = DiscoveryConfig(
        platforms=["galxe", "zealy", "layer3"],
        min_points=10,
        active_only=True,
        max_per_platform=10,
    )

    discovery = CampaignDiscovery(config)

    # Discover campaigns (dry run — APIs may not be available)
    print("Scanning platforms for new campaigns...")
    campaigns = discovery.discover_all()

    if campaigns:
        print(f"\nFound {len(campaigns)} campaigns:")
        for c in campaigns[:5]:
            print(f"  [{c.platform}] {c.title} — {c.points} pts")

        # Export URLs for executor
        urls = discovery.export_urls(campaigns)
        print(f"\nExported {len(urls)} URLs for executor")
    else:
        print("No campaigns found (APIs may be unavailable)")

    return campaigns


def example_onchain():
    """Example: On-chain airdrop farming (dry run)."""
    print("\n" + "=" * 60)
    print("⛓️ ON-CHAIN AIRDROP FARMING")
    print("=" * 60)

    # Configure for Base chain (dry run)
    config = OnChainConfig(
        chain="base",
        dry_run=True,  # IMPORTANT: Always dry run first!
        swap_amount_eth=0.001,
    )

    farmer = OnChainAirdropFarmer(config)

    # View available plans
    plans = farmer.get_all_plans()
    print(f"\nAvailable farming plans: {len(plans)}")
    for name, plan in plans.items():
        print(f"  {name}: {plan.description}")
        print(f"    Chain: {plan.chain.value} | Priority: {plan.priority}")

    # Execute Base activity plan (dry run)
    print("\nExecuting 'base_activity' plan (dry run)...")
    results = farmer.farm_plan("base_activity")

    for r in results:
        status = "✓" if r.success else "✗"
        print(f"  {status} {r.action} on {r.protocol}: {r.amount}")

    # Get summary
    summary = farmer.get_summary()
    print(f"\nSummary: {summary}")


def example_scheduler():
    """Example: Schedule recurring airdrop tasks."""
    print("\n" + "=" * 60)
    print("⏰ DAILY TASK SCHEDULER")
    print("=" * 60)

    scheduler = AirdropScheduler()

    # Add daily tasks
    scheduler.add_daily(
        "galxe_checkin",
        "09:00",
        lambda: print("Galxe daily check-in"),
        platform="galxe",
        description="Check for new Galxe campaigns",
    )

    scheduler.add_daily(
        "base_swap",
        "14:00",
        lambda: print("Base daily swap"),
        platform="base",
        description="Daily swap on Aerodrome",
    )

    scheduler.add_hourly(
        "points_sync",
        lambda: print("Syncing points..."),
        platform="all",
        description="Sync points from all platforms",
    )

    # View scheduled tasks
    tasks = scheduler.get_all_tasks()
    print(f"\nScheduled tasks: {len(tasks)}")
    for task in tasks:
        print(f"  [{task.frequency.value}] {task.name} at {task.target_time}")
        print(f"    Platform: {task.platform} | Next: {task.next_run}")

    # Run a task immediately
    print("\nRunning 'galxe_checkin' now...")
    log = scheduler.run_task_now("galxe_checkin")
    print(f"  Status: {log.status.value}")

    # Get summary
    summary = scheduler.get_summary()
    print(f"\nSummary: {summary}")


def example_dashboard():
    """Example: Track points across platforms."""
    print("\n" + "=" * 60)
    print("📊 POINTS DASHBOARD")
    print("=" * 60)

    config = DashboardConfig(
        wallet_address="0x721e885BE237Ef193807d7a912C201c6a53dA522",
        platforms=["galxe", "zealy", "layer3"],
    )

    dashboard = PointsDashboard(config)

    # Manually add some data for demo
    from datetime import datetime, timezone
    from web3_agent_kit.airdrop.dashboard import PlatformPoints, PointsSnapshot

    dashboard._current = PointsSnapshot(
        timestamp=datetime.now(timezone.utc),
        platforms={
            "galxe": PlatformPoints(
                platform="galxe",
                points=1500,
                rank=1250,
                campaigns_completed=25,
                streak_days=7,
            ),
            "zealy": PlatformPoints(
                platform="zealy",
                points=800,
                rank=500,
                campaigns_completed=15,
            ),
            "layer3": PlatformPoints(
                platform="layer3",
                points=450,
                campaigns_completed=8,
            ),
        },
    )

    # Print summary
    dashboard.print_summary()

    # Export JSON
    json_str = dashboard.export_json()
    print(f"\nExported {len(json_str)} bytes of JSON data")


def example_referral():
    """Example: Generate and track referral links."""
    print("\n" + "=" * 60)
    print("🔗 REFERRAL MANAGER")
    print("=" * 60)

    manager = ReferralManager(
        wallets=["0x721e885BE237Ef193807d7a912C201c6a53dA522"]
    )

    # Add platforms
    manager.add_known_platform("galxe")
    manager.add_known_platform("zealy")
    manager.add_known_platform("layer3")

    # Generate links
    print("\nGenerating referral links...")
    links = manager.generate_links(count=3)

    for link in links:
        print(f"  [{link.platform}] {link.url}")

    # Record some activity
    if links:
        manager.record_click(links[0].code)
        manager.record_conversion(links[0].code, points=10)
        print(f"\nRecorded click + conversion for {links[0].code}")

    # Generate a chain
    chain = manager.generate_chain(
        ["galxe", "zealy", "layer3"],
        wallet="0x721e885BE237Ef193807d7a912C201c6a53dA522",
    )
    print(f"\nReferral chain: {' → '.join(l.platform for l in chain)}")

    # Print stats
    manager.print_stats()


def example_faucet():
    """Example: Claim testnet tokens."""
    print("\n" + "=" * 60)
    print("🚰 FAUCET CLAIMER")
    print("=" * 60)

    claimer = FaucetClaimer()

    # View available faucets
    faucets = claimer.get_all_faucets()
    print(f"\nAvailable faucets: {len(faucets)}")
    for key, faucet in list(faucets.items())[:5]:
        print(f"  {key}: {faucet.name} ({faucet.token})")

    # Check available (not in cooldown)
    available = claimer.get_available("0x123")
    print(f"\nAvailable (not in cooldown): {len(available)}")

    # Note: Actual claiming requires CAPTCHA solving and real APIs
    print("\nNote: Run claimer.claim_all(wallet) to actually claim tokens")
    print("      Requires CAPTCHA API key for some faucets")


def main():
    """Run all examples."""
    print("🚀 Web3 Agent Kit — Airdrop Automation Suite")
    print("=" * 60)

    # Run examples
    example_discovery()
    example_onchain()
    example_scheduler()
    example_dashboard()
    example_referral()
    example_faucet()

    print("\n" + "=" * 60)
    print("✅ All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
