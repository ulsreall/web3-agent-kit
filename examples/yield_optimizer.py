"""Example: Yield Optimizer — Scan, compare, and auto-compound yield across DeFi."""

from web3_agent_kit import Wallet, Chain
from web3_agent_kit.yield_optimizer import YieldOptimizer, YieldConfig, RiskLevel, Protocol

# Initialize
wallet = Wallet(private_key="0xYOUR_KEY", chain=Chain.ETHEREUM)
config = YieldConfig(
    min_apy=2.0,               # Only consider >2% APY
    max_risk=RiskLevel.MEDIUM, # No high-risk strategies
    min_tvl=5_000_000,         # Min $5M TVL
    auto_compound_threshold=25, # Compound when rewards > $25
    compound_interval=43200,    # Every 12 hours
)
optimizer = YieldOptimizer(wallet, Chain.ETHEREUM, config)

# 1. Scan opportunities
print("=== Scanning USDC yields ===")
opportunities = optimizer.scan_opportunities("USDC")
for opp in opportunities[:5]:
    print(f"  {opp.protocol.value}: {opp.apy_display} (TVL: {opp.tvl_display}) [{opp.risk.value}]")

# 2. Find best opportunity
best = optimizer.find_best("USDC", amount=10000)
if best:
    print(f"\nBest: {best.protocol.value} — {best.apy_display}")

# 3. Deposit
    result = optimizer.deposit(best, amount=10000)
    print(f"Deposited: {result['status']}")

# 4. Compare across protocols
print("\n=== Protocol Comparison ===")
comparison = optimizer.compare_protocols("USDC")
for c in comparison:
    print(f"  {c['protocol']}: {c['apy']:.2f}% (TVL: ${c['tvl']:,.0f}) [{c['risk']}]")

# 5. Portfolio summary
summary = optimizer.get_portfolio_summary()
print(f"\nPositions: {summary['total_positions']}")
print(f"Total deposited: ${summary['total_deposited_usd']:,.2f}")
print(f"Average APY: {summary['average_apy']:.2f}%")

# 6. Auto-compound
results = optimizer.auto_compound_all()
for r in results:
    print(f"Compounded: ${r['compounded_amount']:.2f}")
