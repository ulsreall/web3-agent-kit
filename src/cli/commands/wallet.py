"""wak wallet — wallet-related commands."""

import click


@click.group()
def wallet():
    """Wallet operations (balance, send, etc.)."""
    pass


@wallet.command()
@click.option("--address", "-a", required=True, help="Wallet address (0x...)")
@click.option("--chain", "-c", default="ethereum", help="Blockchain network (ethereum, base, arbitrum, etc.)")
def balance(address, chain):
    """Check native token balance for a wallet address.

    \b
    Example:
      wak wallet balance --address 0x1234...abcd --chain ethereum
      wak wallet balance -a 0x1234...abcd -c base
    """
    click.echo()
    click.echo(click.style("  💰 Wallet Balance Check", fg="cyan", bold=True))
    click.echo()
    click.echo(f"  Address: {address}")
    click.echo(f"  Chain:   {chain}")
    click.echo()
    click.echo(click.style("  ⚠️  This command requires an RPC connection.", fg="yellow"))
    click.echo()
    click.echo("  To use this feature, set your RPC URL:")
    click.echo(click.style("    export RPC_URL=https://eth.llamarpc.com", fg="green"))
    click.echo()
    click.echo("  Or add to your .env file:")
    click.echo(click.style("    RPC_URL=https://eth.llamarpc.com", fg="green"))
    click.echo()
    click.echo("  Supported chains: ethereum, base, arbitrum, optimism, polygon, avalanche, bsc")
    click.echo()
    click.echo(click.style("  💡 Tip:", fg="blue") + " You can also use the Python API directly:")
    click.echo('    from web3_agent_kit import Wallet, WalletConfig')
    click.echo(f'    w = Wallet(WalletConfig(rpc_url="https://eth.llamarpc.com"))')
    click.echo(f'    print(w.get_balance("{address}"))')
    click.echo()
