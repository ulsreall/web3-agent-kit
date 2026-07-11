"""wak examples — list available example scripts."""

import os

import click


@click.command()
def examples():
    """List available example scripts in the project.

    Shows Python example files you can run to learn the library.
    """
    click.echo()
    click.echo(click.style("  📚 Available Examples", fg="cyan", bold=True))
    click.echo()

    examples_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "examples"))
    if not os.path.isdir(examples_dir):
        click.echo(click.style("  ❌ Examples directory not found.", fg="red"))
        return

    files = sorted(f for f in os.listdir(examples_dir) if f.endswith(".py"))
    if not files:
        click.echo(click.style("  No example files found.", fg="yellow"))
        return

    # Descriptions for known examples
    descriptions = {
        "swap_agent.py": "LLM-powered swap agent",
        "llm_swap_agent.py": "Advanced LLM swap agent",
        "direct_swap.py": "Direct token swap (no LLM)",
        "token_sniper.py": "Snipe new token pairs",
        "sniper_bot.py": "Automated sniper bot",
        "dca_bot.py": "Dollar-cost averaging bot",
        "portfolio_tracker.py": "Track portfolio across chains",
        "portfolio_dashboard.py": "Portfolio dashboard",
        "gas_optimizer.py": "Gas price optimization",
        "bridge_agent.py": "Cross-chain bridge agent",
        "yield_optimizer.py": "DeFi yield optimization",
        "multi_wallet.py": "Multi-wallet management",
        "wallet_watcher.py": "Monitor wallet activity",
        "approval_manager.py": "Token approval manager",
        "security_analysis.py": "Token security scanner",
        "airdrop_suite.py": "Airdrop farming suite",
        "airdrop_farmer.py": "Automated airdrop farmer",
        "plugin_system.py": "Plugin system demo",
        "api_server.py": "REST API server example",
    }

    for i, f in enumerate(files, 1):
        desc = descriptions.get(f, "")
        name = click.style(f"  {i:2d}. {f}", fg="green")
        if desc:
            name += click.style(f"  — {desc}", dim=True)
        click.echo(name)

    click.echo()
    click.echo(click.style("  💡 Run an example:", fg="blue"))
    click.echo(click.style("    cd examples && python swap_agent.py", fg="green"))
    click.echo()
