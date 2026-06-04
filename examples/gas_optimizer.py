"""Example: Gas Optimizer — Smart gas estimation and timing."""

from web3_agent_kit import Wallet, Chain, ChainManager
from web3_agent_kit.gas_optimizer import GasOptimizer, GasPriority

wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=ChainManager(chains=[Chain.ETHEREUM]))
optimizer = GasOptimizer(wallet, ChainManager(chains=[Chain.ETHEREUM, Chain.BASE]))

# 1. Current gas price
gas = optimizer.get_gas_price(Chain.ETHEREUM)
print(f"⛽ Gas: {gas['gwei']:.1f} gwei ({gas['level']})")

# 2. Estimate for a swap
estimate = optimizer.estimate(
    to="0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",
    value=0.1,
    chain=Chain.ETHEREUM,
    priority=GasPriority.MEDIUM,
    operation="swap",
)
print(f"Swap cost: {estimate.total_cost_eth:.6f} ETH (${estimate.total_cost_usd:.2f})")

# 3. Timing recommendation
rec = optimizer.recommend_timing(Chain.ETHEREUM)
print(f"Recommendation: {rec.recommended_action}")
print(f"  Current: {rec.current_gwei:.1f} gwei")
print(f"  Optimal: {rec.optimal_gwei:.1f} gwei")
print(f"  Savings: {rec.estimated_savings_pct:.0f}%")
print(f"  Reason: {rec.reason}")

# 4. Batch estimate
txs = [
    {"to": "0xA", "value": 0.01, "operation": "transfer"},
    {"to": "0xB", "value": 0.02, "operation": "transfer"},
    {"to": "0xC", "value": 0.03, "operation": "erc20_transfer"},
]
batch = optimizer.batch_estimate(txs, Chain.BASE)
print(f"\nBatch: {batch['count']} txs = {batch['total_cost_usd']:.2f} USD")
