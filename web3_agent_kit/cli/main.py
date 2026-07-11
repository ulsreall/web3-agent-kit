"""WAK CLI — Web3 Agent Kit command-line interface."""

import click

from web3_agent_kit.cli.commands.agent import agent
from web3_agent_kit.cli.commands.doctor import doctor
from web3_agent_kit.cli.commands.examples import examples
from web3_agent_kit.cli.commands.gas import gas
from web3_agent_kit.cli.commands.info import info
from web3_agent_kit.cli.commands.token import token
from web3_agent_kit.cli.commands.wallet import wallet

BANNER = r"""
 ██╗    ██╗ █████╗ ██╗
 ██║    ██║██╔══██╗██║
 ██║ █╗ ██║███████║██║
 ██║███╗██║██╔══██║██║
 ╚███╔███╔╝██║  ██║██║
  ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝
  Web3 Agent Kit CLI
"""


@click.group(invoke_without_command=True)
@click.version_option(version="1.12.0", prog_name="wak")
@click.pass_context
def main(ctx):
    """WAK — Web3 Agent Kit CLI.

    Build and run autonomous Web3 AI agents from your terminal.

    Run 'wak <command> --help' for more info on a command.
    """
    if ctx.invoked_subcommand is None:
        click.echo(click.style(BANNER, fg="cyan", bold=True))
        click.echo(ctx.get_help())


# Register subcommands
main.add_command(info)
main.add_command(doctor)
main.add_command(wallet)
main.add_command(token)
main.add_command(gas)
main.add_command(agent)
main.add_command(examples)


if __name__ == "__main__":
    main()
