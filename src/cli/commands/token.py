"""wak token — token analysis commands."""

import click


@click.group()
def token():
    """Token analysis (safety check, info, etc.)."""
    pass


@token.command()
@click.option("--address", "-a", required=True, help="Token contract address (0x...)")
@click.option("--chain", "-c", default="ethereum", help="Blockchain network")
def check(address, chain):
    """Check token safety: honeypot, rug pull risk, contract audit.

    \b
    Example:
      wak token check --address 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48
      wak token check -a 0xA0b8...eB48 -c base
    """
    click.echo()
    click.echo(click.style("  🔒 Token Safety Check", fg="cyan", bold=True))
    click.echo()
    click.echo(f"  Address: {address}")
    click.echo(f"  Chain:   {chain}")
    click.echo()
    click.echo(click.style("  ⚠️  This command requires an RPC endpoint and/or API key.", fg="yellow"))
    click.echo()
    click.echo("  To use this feature, configure:")
    click.echo(click.style("    export RPC_URL=https://eth.llamarpc.com", fg="green"))
    click.echo(click.style("    export ETHERSCAN_API_KEY=your_key", fg="green"))
    click.echo()
    click.echo("  Or use the Python API directly:")
    click.echo(click.style('    from web3_agent_kit import TokenAnalyzer, SecurityConfig', fg="green"))
    click.echo(click.style('    analyzer = TokenAnalyzer(SecurityConfig(rpc_url="..."))', fg="green"))
    click.echo(click.style(f'    report = analyzer.analyze_token("{address}")', fg="green"))
    click.echo(click.style('    print(f"Safety: {report.safety_score}/100")', fg="green"))
    click.echo()
