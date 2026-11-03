"""wak token — token analysis commands."""

import os

import click

from ._helpers import resolve_chain


@click.group()
def token():
    """Token safety quick checks."""
    pass


@token.command()
@click.option("--address", "-a", required=True, help="Token contract address (0x...)")
@click.option("--chain", "-c", default="ethereum", help="Blockchain network")
def check(address, chain):
    """Run a GoPlus honeypot/tax quick check.

    \b
    Example:
      wak token check --address 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48
      wak token check -a 0xA0b8...eB48 -c base
    """
    from web3_agent_kit.security import SecurityConfig, TokenAnalyzer

    selected_chain = resolve_chain(chain)
    analyzer = TokenAnalyzer(
        SecurityConfig(
            chain=selected_chain.value,
            rpc_url=os.environ.get(f"{selected_chain.name}_RPC_URL")
            or os.environ.get("RPC_URL", ""),
            etherscan_api_key=os.environ.get("ETHERSCAN_API_KEY", ""),
            goplus_api_key=os.environ.get("GOPLUS_API_KEY", ""),
        )
    )
    result = analyzer.quick_check(address)
    if result.get("error"):
        raise click.ClickException(f"Token safety check failed: {result['error']}")

    click.echo(f"Address: {address}")
    click.echo(f"Chain: {selected_chain.value}")
    click.echo("Check: GoPlus quick security lookup")
    honeypot = result["is_honeypot"] if result["is_honeypot"] is not None else "unknown"
    click.echo(f"Honeypot: {honeypot}")
    click.echo(f"Buy tax: {result['buy_tax']}%")
    click.echo(f"Sell tax: {result['sell_tax']}%")
    click.echo(f"Risk: {result['risk_level']}")
