"""wak info — show library version, stats, and links."""

import os

import click

BANNER = r"""
 ██╗    ██╗ █████╗ ██╗
 ██║    ██║██╔══██╗██║
 ██║ █╗ ██║███████║██║
 ██║███╗██║██╔══██║██║
 ╚███╔███╔╝██║  ██║██║
  ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝
"""


def _count_modules(src_dir: str) -> int:
    """Count distinct Python sub-packages under src/."""
    modules = set()
    for entry in os.scandir(src_dir):
        if entry.is_dir() and not entry.name.startswith(("_", ".")):
            init = os.path.join(entry.path, "__init__.py")
            if os.path.isfile(init):
                modules.add(entry.name)
    return len(modules)


def _count_chains(src_dir: str) -> int:
    """Parse Chain enum member count from chains/chain.py."""
    chain_file = os.path.join(src_dir, "chains", "chain.py")
    if not os.path.isfile(chain_file):
        return 0
    count = 0
    with open(chain_file) as f:
        for line in f:
            line.strip().upper()
            # Enum members look like: ETHEREUM = "ethereum"
            if "=" in line and '"' in line and not line.strip().startswith("#"):
                parts = line.strip().split("=")
                name = parts[0].strip()
                if name.isupper() and name.isalpha() and len(name) > 1:
                    count += 1
    return count


def _read_version() -> str:
    """Read version from pyproject.toml."""
    pyproject = os.path.join(os.path.dirname(__file__), "..", "..", "..", "pyproject.toml")
    pyproject = os.path.normpath(pyproject)
    if os.path.isfile(pyproject):
        with open(pyproject) as f:
            for line in f:
                if line.strip().startswith("version"):
                    return line.split("=")[1].strip().strip('"')
    return "unknown"


@click.command()
def info():
    """Show library version, stats, and useful links."""
    # Banner
    click.echo(click.style(BANNER, fg="cyan", bold=True))

    version = _read_version()
    src_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    module_count = _count_modules(src_dir)
    chain_count = _count_chains(src_dir)

    # Stats
    click.echo(click.style("  📦 web3-agent-kit", fg="white", bold=True) + click.style(f"  v{version}", fg="green"))
    click.echo()
    click.echo(click.style("  Modules:  ", fg="yellow") + f"{module_count} packages")
    click.echo(click.style("  Chains:   ", fg="yellow") + f"{chain_count} networks (EVM + Solana)")
    click.echo(click.style("  Python:   ", fg="yellow") + ">=3.10")
    click.echo(click.style("  License:  ", fg="yellow") + "MIT")
    click.echo()

    # Capabilities
    click.echo(click.style("  🚀 Capabilities:", fg="magenta", bold=True))
    caps = [
        "AI-powered swap agent (LLM-driven)",
        "Token sniping & DCA bot",
        "Portfolio tracking & yield optimization",
        "Bridge routing across chains",
        "Security analysis (honeypot, rug detection)",
        "Multi-wallet management & batch txns",
        "Gas optimization & MEV protection",
        "Airdrop farming automation",
        "Plugin system for extensibility",
    ]
    for cap in caps:
        click.echo(f"    • {cap}")

    click.echo()

    # Links
    click.echo(click.style("  🔗 Links:", fg="blue", bold=True))
    click.echo("    GitHub  → https://github.com/ulsreall/web3-agent-kit")
    click.echo("    Issues  → https://github.com/ulsreall/web3-agent-kit/issues")
    click.echo("    Docs    → https://github.com/ulsreall/web3-agent-kit#readme")
    click.echo()
