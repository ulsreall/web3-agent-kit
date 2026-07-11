"""wak agent — run an AI agent."""

import click


@click.command()
@click.option("--goal", "-g", required=True, help="Natural language goal for the agent")
@click.option("--wallet", "-w", required=True, help="Wallet address to use")
@click.option("--chain", "-c", default="base", help="Target blockchain network")
def agent(goal, wallet, chain):
    """Run an autonomous AI agent to execute a Web3 task.

    \b
    Example:
      wak agent --goal "swap 0.1 ETH to USDC" --wallet 0x1234... --chain base
      wak agent -g "bridge 1 ETH from ethereum to base" -w 0x1234... -c base
    """
    click.echo()
    click.echo(click.style("  🤖 WAK Agent", fg="cyan", bold=True))
    click.echo()
    click.echo(f"  Goal:   {goal}")
    click.echo(f"  Wallet: {wallet}")
    click.echo(f"  Chain:  {chain}")
    click.echo()
    click.echo(click.style("  ⚠️  This command requires an LLM API key.", fg="yellow"))
    click.echo()
    click.echo("  To use the agent, configure one of:")
    click.echo(click.style("    export OPENAI_API_KEY=sk-...", fg="green"))
    click.echo(click.style("    export ANTHROPIC_API_KEY=sk-ant-...", fg="green"))
    click.echo()
    click.echo(click.style("  📝 You also need:", fg="yellow"))
    click.echo(click.style("    export PRIVATE_KEY=0x...", fg="green"))
    click.echo(click.style("    export RPC_URL=https://...", fg="green"))
    click.echo()
    click.echo("  Or use the Python API directly:")
    click.echo(click.style('    from web3_agent_kit import Agent, AgentConfig', fg="green"))
    click.echo(click.style('    agent = Agent(AgentConfig(', fg="green"))
    click.echo(click.style('        llm_provider="openai",', fg="green"))
    click.echo(click.style('        private_key="0x...",', fg="green"))
    click.echo(click.style('        rpc_url="...",', fg="green"))
    click.echo(click.style('    ))', fg="green"))
    click.echo(click.style(f'    result = agent.run("{goal}")', fg="green"))
    click.echo()
