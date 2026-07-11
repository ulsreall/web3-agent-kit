"""CLI interface for airdrop farming and browser management.

Provides terminal commands for farming Gleam/Zealy campaigns,
managing browser sessions, and tracking airdrop progress.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import click

from ..tracker import AirdropTracker

# Lazy imports for heavy dependencies
_browser_manager = None
_gleam_executor = None
_zealy_executor = None
_twitter_executor = None
_discord_executor = None
_telegram_executor = None


def _get_browser(config=None):
    """Lazy-import and create BrowserManager."""
    from .browser import BrowserConfig, BrowserManager

    return BrowserManager(config or BrowserConfig())


def _ensure_playwright():
    """Check if playwright is available."""
    try:
        from .browser import HAS_PLAYWRIGHT
        if not HAS_PLAYWRIGHT:
            click.echo(
                click.style(
                    "Error: playwright not installed. Run:\n"
                    "  pip install playwright && playwright install chromium",
                    fg="red",
                )
            )
            sys.exit(1)
    except ImportError:
        click.echo(click.style("Error: executor module not available", fg="red"))
        sys.exit(1)


# ─────────────────────── Main CLI Group ───────────────────────


@click.group()
@click.version_option(version="0.8.0", prog_name="wak")
def main():
    """Web3 Agent Kit — Airdrop farming and browser automation."""
    pass


# ─────────────────────── Farm Commands ───────────────────────


@main.group()
def farm():
    """Airdrop farming commands."""
    pass


@farm.command("gleam")
@click.argument("url")
@click.option("--headless/--headed", default=True, help="Run browser in headless mode")
@click.option("--proxy", default=None, help="Proxy URL (http://... or socks5://...)")
@click.option("--delay-min", default=2.0, help="Minimum delay between tasks (seconds)")
@click.option("--delay-max", default=5.0, help="Maximum delay between tasks (seconds)")
@click.option("--screenshot-dir", default=None, help="Directory for debug screenshots")
def farm_gleam(url: str, headless: bool, proxy: str, delay_min: float, delay_max: float, screenshot_dir: str):
    """Farm a Gleam.io campaign.

    URL is the full Gleam.io contest URL.
    """
    _ensure_playwright()

    from .browser import BrowserConfig, BrowserManager
    from .gleam_exec import GleamExecutor

    click.echo(click.style("🎯 Gleam.io Farming", fg="cyan", bold=True))
    click.echo(f"   URL: {url}")
    click.echo(f"   Mode: {'headless' if headless else 'headed'}")
    if proxy:
        click.echo(f"   Proxy: {proxy}")
    click.echo()

    config = BrowserConfig(
        headless=headless,
        proxy=proxy,
        screenshot_dir=Path(screenshot_dir) if screenshot_dir else None,
    )
    tracker = AirdropTracker()

    try:
        with BrowserManager(config) as browser:
            executor = GleamExecutor(browser)
            executor.TASK_DELAY_MIN = delay_min
            executor.TASK_DELAY_MAX = delay_max

            with click.progressbar(
                length=100, label="Completing tasks", show_pos=True
            ) as bar:
                result = executor.complete_all(url, tracker=tracker)
                bar.update(100)

            # Display results
            _display_gleam_result(result)

    except ImportError as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        sys.exit(1)


@farm.command("zealy")
@click.argument("url")
@click.option("--headless/--headed", default=True, help="Run browser in headless mode")
@click.option("--proxy", default=None, help="Proxy URL")
@click.option("--delay-min", default=3.0, help="Minimum delay between quests")
@click.option("--delay-max", default=7.0, help="Maximum delay between quests")
def farm_zealy(url: str, headless: bool, proxy: str, delay_min: float, delay_max: float):
    """Farm a Zealy quest board.

    URL is the Zealy community URL (e.g., https://zealy.io/c/community).
    """
    _ensure_playwright()

    from .browser import BrowserConfig, BrowserManager
    from .zealy_exec import ZealyExecutor

    click.echo(click.style("🎯 Zealy Quest Farming", fg="cyan", bold=True))
    click.echo(f"   URL: {url}")
    click.echo(f"   Mode: {'headless' if headless else 'headed'}")
    click.echo()

    config = BrowserConfig(headless=headless, proxy=proxy)
    tracker = AirdropTracker()

    try:
        with BrowserManager(config) as browser:
            executor = ZealyExecutor(browser)
            executor.QUEST_DELAY_MIN = delay_min
            executor.QUEST_DELAY_MAX = delay_max

            with click.progressbar(
                length=100, label="Completing quests", show_pos=True
            ) as bar:
                result = executor.complete_all(url, tracker=tracker)
                bar.update(100)

            _display_zealy_result(result)

    except ImportError as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        sys.exit(1)


@farm.command("status")
@click.option("--platform", default=None, help="Filter by platform (gleam, zealy)")
@click.option("--all", "show_all", is_flag=True, help="Show inactive campaigns too")
def farm_status(platform: str, show_all: bool):
    """Show all tracked airdrop campaigns and progress."""
    tracker = AirdropTracker()
    campaigns = tracker.list_campaigns(
        platform=platform,
        active_only=not show_all,
    )

    summary = tracker.get_summary()

    click.echo(click.style("📊 Airdrop Status", fg="cyan", bold=True))
    click.echo(f"   Total campaigns: {summary.total_campaigns}")
    click.echo(f"   Active campaigns: {summary.active_campaigns}")
    click.echo(f"   Completed tasks: {summary.completed_tasks}")
    click.echo(f"   Total points: {summary.total_points:.0f}")
    click.echo()

    if not campaigns:
        click.echo(click.style("   No tracked campaigns.", fg="yellow"))
        return

    for campaign in campaigns:
        progress_bar = _make_progress_bar(campaign.progress)

        click.echo(f"   {click.style(campaign.name, fg='white', bold=True)} [{campaign.platform}]")
        click.echo(f"     {progress_bar} {campaign.progress:.0%}")
        click.echo(f"     Points: {campaign.earned_points:.0f}/{campaign.total_points:.0f}")

        if campaign.url:
            click.echo(f"     URL: {click.style(campaign.url, fg='blue')}")
        click.echo()

    # Show rewards if any
    if summary.total_rewards:
        click.echo(click.style("   💰 Rewards:", fg="green"))
        for reward in summary.total_rewards:
            claimed = "✓" if reward.claimed else "○"
            click.echo(
                f"     {claimed} {reward.campaign_name}: "
                f"{reward.points} pts, {reward.tokens} {reward.token_symbol}"
            )


@farm.command("export")
@click.option("--format", "fmt", type=click.Choice(["csv", "json"]), default="csv")
@click.option("--output", "-o", default=None, help="Output file path")
def farm_export(fmt: str, output: str):
    """Export airdrop progress to CSV or JSON."""
    tracker = AirdropTracker()

    if not output:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output = f"airdrop_export_{timestamp}.{fmt}"

    if fmt == "json":
        tracker.export_json(output)
    else:
        tracker.export_csv(output)

    click.echo(click.style(f"✓ Exported to {output}", fg="green"))


# ─────────────────────── Browser Commands ───────────────────────


@main.group()
def browser():
    """Browser session management."""
    pass


@browser.command("login")
@click.argument("platform", type=click.Choice(["twitter", "discord", "telegram"]))
def browser_login(platform: str):
    """Interactive login to a social platform.

    Opens a headed browser for manual authentication.
    Cookies are saved for future automated use.
    """
    _ensure_playwright()

    click.echo(click.style(f"🔑 Logging in to {platform.title()}", fg="cyan", bold=True))
    click.echo("   A browser window will open. Log in manually, then press Enter here.")
    click.echo()

    if platform == "twitter":
        from .social_exec import TwitterExecutor

        browser = _get_browser()
        executor = TwitterExecutor(browser)
        try:
            success = executor.interactive_login()
            if success:
                click.echo(click.style("✓ Twitter login saved!", fg="green"))
            else:
                click.echo(click.style("✗ Twitter login failed", fg="red"))
        finally:
            browser.close()

    elif platform == "discord":
        from .social_exec import DiscordExecutor

        browser = _get_browser()
        executor = DiscordExecutor(browser)
        try:
            success = executor.interactive_login()
            if success:
                click.echo(click.style("✓ Discord login saved!", fg="green"))
            else:
                click.echo(click.style("✗ Discord login failed", fg="red"))
        finally:
            browser.close()

    elif platform == "telegram":
        from .social_exec import TelegramExecutor

        browser = _get_browser()
        executor = TelegramExecutor(browser)
        try:
            success = executor.interactive_login()
            if success:
                click.echo(click.style("✓ Telegram login saved!", fg="green"))
            else:
                click.echo(click.style("✗ Telegram login failed", fg="red"))
        finally:
            browser.close()


@browser.command("sessions")
def browser_sessions():
    """List saved browser sessions."""
    from .browser import SESSIONS_DIR

    if not SESSIONS_DIR.exists():
        click.echo(click.style("No saved sessions.", fg="yellow"))
        return

    click.echo(click.style("📦 Saved Sessions", fg="cyan", bold=True))
    click.echo()

    for session_dir in sorted(SESSIONS_DIR.iterdir()):
        if session_dir.is_dir():
            name = session_dir.name
            cookie_file = session_dir / "cookies.json"
            has_cookies = cookie_file.exists()
            size = cookie_file.stat().st_size if has_cookies else 0
            modified = time.ctime(cookie_file.stat().st_mtime) if has_cookies else "never"

            status = click.style("✓ cookies", fg="green") if has_cookies else click.style("○ no cookies", fg="yellow")
            click.echo(f"   {click.style(name, bold=True)} — {status}")
            if has_cookies:
                click.echo(f"     Size: {size:,} bytes, Modified: {modified}")

            # List platform subdirs
            for subdir in sorted(session_dir.iterdir()):
                if subdir.is_dir():
                    sub_cookie = subdir / "cookies.json"
                    sub_status = click.style("✓", fg="green") if sub_cookie.exists() else click.style("○", fg="yellow")
                    click.echo(f"     └─ {subdir.name} {sub_status}")

    click.echo()
    click.echo(f"   Session directory: {SESSIONS_DIR}")


# ─────────────────────── Display Helpers ───────────────────────


def _display_gleam_result(result) -> None:
    """Display Gleam farming results."""
    click.echo()

    if result.is_fully_completed:
        click.echo(click.style("✅ All tasks completed!", fg="green", bold=True))
    else:
        click.echo(click.style("⚠️  Farming completed with issues", fg="yellow", bold=True))

    click.echo(f"   Total tasks:   {result.total_tasks}")
    click.echo(click.style(f"   Completed:     {result.completed_tasks}", fg="green"))
    if result.failed_tasks:
        click.echo(click.style(f"   Failed:        {result.failed_tasks}", fg="red"))
    if result.skipped_tasks:
        click.echo(f"   Skipped:       {result.skipped_tasks}")
    click.echo(f"   Success rate:  {result.success_rate:.0%}")
    click.echo(f"   Time:          {result.elapsed_seconds:.1f}s")

    if result.errors:
        click.echo()
        click.echo(click.style("   Errors:", fg="red"))
        for error in result.errors[:10]:
            click.echo(f"     • {error}")


def _display_zealy_result(result) -> None:
    """Display Zealy farming results."""
    click.echo()

    if result.completed_quests == result.total_quests and result.total_quests > 0:
        click.echo(click.style("✅ All quests completed!", fg="green", bold=True))
    else:
        click.echo(click.style("⚠️  Questing completed with issues", fg="yellow", bold=True))

    click.echo(f"   Total quests:  {result.total_quests}")
    click.echo(click.style(f"   Completed:     {result.completed_quests}", fg="green"))
    click.echo(click.style(f"   XP earned:     {result.xp_earned}", fg="cyan"))
    if result.failed_quests:
        click.echo(click.style(f"   Failed:        {result.failed_quests}", fg="red"))
    click.echo(f"   Success rate:  {result.success_rate:.0%}")
    click.echo(f"   Time:          {result.elapsed_seconds:.1f}s")

    if result.errors:
        click.echo()
        click.echo(click.style("   Errors:", fg="red"))
        for error in result.errors[:10]:
            click.echo(f"     • {error}")


def _make_progress_bar(progress: float, width: int = 20) -> str:
    """Create a text progress bar."""
    filled = int(width * min(progress, 1.0))
    empty = width - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}]"


if __name__ == "__main__":
    main()
