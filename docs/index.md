<div class="docs-hero" markdown>
<div class="docs-hero-copy" markdown>

<p class="docs-eyebrow">OPEN-SOURCE PYTHON INFRASTRUCTURE <span>·</span> v1.16.1</p>

# Build agents that can actually execute.

Web3 Agent Kit gives autonomous agents a controlled path from intent to on-chain execution: wallets, chains, protocol tools, transaction simulation, and operator-defined policy in one Python framework.

<div class="docs-actions" markdown>
[Get started](getting-started.md){ .md-button .md-button--primary }
[View source](https://github.com/ulsreall/web3-agent-kit){ .md-button }
</div>

<div class="docs-install" markdown>
<span>INSTALL</span>
`pip install web3-agent-kit`
</div>

</div>

<div class="docs-terminal" markdown>
<div class="terminal-bar"><span></span><span></span><span></span><b>agent.py</b><i>READY</i></div>

```python
from web3_agent_kit import Agent, Wallet, Chain
from web3_agent_kit.defi import Uniswap

agent = Agent(
    wallet=Wallet.from_env("PRIVATE_KEY"),
    chains=[Chain.BASE],
    tools=[Uniswap()],
)

result = agent.run("check my balances")
print(result)
```

<div class="terminal-foot">intent → policy → simulation → execution</div>
</div>
</div>

<div class="docs-metrics" markdown>
<div><strong>25</strong><span>modules</span></div>
<div><strong>1,791</strong><span>tests passing</span></div>
<div><strong>8</strong><span>supported chains</span></div>
<div><strong>74%</strong><span>coverage</span></div>
<div><strong>MIT</strong><span>license</span></div>
</div>

<div class="docs-rule"></div>

<div class="docs-section-intro" markdown>
<p class="docs-section-number">01 / THE FRAMEWORK</p>

## Everything around the transaction.

The hard part of an on-chain agent is not calling a contract. It is making the full path observable, composable, and safe to operate. The kit keeps those concerns in one surface.
</div>

<div class="docs-capabilities" markdown>
<div class="docs-capability" markdown>
<span class="capability-number">01</span>
### Agent runtime

Goal-driven execution with pluggable LLM providers, tool routing, structured results, and a Python API that stays readable.

[Read the agent API →](api/agent.md)
</div>

<div class="docs-capability docs-capability-dark" markdown>
<span class="capability-number">02</span>
### Execution policy

Spend limits, operator confirmation, kill switches, and transaction simulation sit between an agent decision and a broadcast.

[Review the security model →](security-model.md)
</div>

<div class="docs-capability" markdown>
<span class="capability-number">03</span>
### Protocol primitives

DeFi, bridges, wallets, gas, portfolio, NFT, trading, oracle, and account-abstraction modules share the same chain-aware foundation.

[Explore features →](features.md)
</div>

<div class="docs-capability docs-capability-wide" markdown>
<span class="capability-number">04</span>
### Multi-chain by default

Use one interface across Ethereum, Base, Arbitrum, Polygon, Optimism, BSC, Solana, and Avalanche. Add a new chain without rebuilding every tool around it.

<div class="chain-list"><span>Ethereum</span><span>Base</span><span>Arbitrum</span><span>Polygon</span><span>Optimism</span><span>BSC</span><span>Solana</span><span>Avalanche</span></div>
</div>
</div>

<div class="docs-rule"></div>

<div class="docs-section-intro" markdown>
<p class="docs-section-number">02 / EXECUTION MODEL</p>

## One controlled path from goal to chain.

Every write operation should be explainable before it becomes irreversible. The framework makes the execution boundary explicit.
</div>

<div class="execution-path" markdown>
<div><span>01</span><strong>Intent</strong><small>Natural language or Python call</small></div>
<div><span>02</span><strong>Plan</strong><small>Tool routing and parameters</small></div>
<div><span>03</span><strong>Policy</strong><small>Limits, approval, simulation</small></div>
<div><span>04</span><strong>Execute</strong><small>Signed transaction on-chain</small></div>
</div>

<div class="docs-callout" markdown>
<span>i</span>
<p><strong>Designed for controlled automation.</strong> The framework is beta software. Review the [maturity policy](project-maturity.md) and [risk disclosure](../RISKS.md) before using real funds.</p>
</div>

<div class="docs-rule"></div>

<div class="docs-section-intro docs-section-intro-small" markdown>
<p class="docs-section-number">03 / START HERE</p>

## Small surface. Serious foundations.
</div>

<div class="docs-start-grid" markdown>
<div markdown>
<span class="start-label">FIRST RUN</span>
### Build your first agent
Install the package, configure a wallet, and run a read-only balance check.

[Open Getting Started →](getting-started.md)
</div>
<div markdown>
<span class="start-label">TERMINAL</span>
### Use the `wak` CLI
Inspect chains, check dependencies, run examples, and operate without writing Python.

[Open CLI reference →](cli.md)
</div>
<div markdown>
<span class="start-label">REFERENCE</span>
### Browse the API
Go deeper into wallets, chains, LLMs, DeFi, bridges, security, and execution modules.

[Open API reference →](api/agent.md)
</div>
</div>

<div class="docs-footer-cta" markdown>
<div><span class="docs-section-number">OPEN SOURCE · MIT LICENSE</span><strong>Build on the source, not a black box.</strong></div>
[GitHub repository →](https://github.com/ulsreall/web3-agent-kit){ .md-button .md-button--primary }
</div>
