"""Example: Approval Manager — Scan and revoke risky approvals."""

from web3_agent_kit import Wallet, Chain, ChainManager
from web3_agent_kit.approval_manager import ApprovalManager, ApprovalRisk

wallet = Wallet.from_env("PRIVATE_KEY", chain_manager=ChainManager(chains=[Chain.ETHEREUM]))
manager = ApprovalManager(wallet, ChainManager(chains=[Chain.ETHEREUM]))

# 1. Scan for approvals
approvals = manager.scan(Chain.ETHEREUM)
print(f"Found {len(approvals)} approvals")

# 2. Show all
for a in approvals:
    risk_emoji = {
        ApprovalRisk.SAFE: "🟢",
        ApprovalRisk.MODERATE: "🟡",
        ApprovalRisk.HIGH: "🟠",
        ApprovalRisk.CRITICAL: "🔴",
    }
    emoji = risk_emoji.get(a.risk, "⚪")
    amount_str = "unlimited" if a.amount == float("inf") else f"{a.amount:.2f}"
    print(f"  {emoji} {a.token_symbol} → {a.spender_label}: {amount_str}")

# 3. Get risky ones
risky = manager.get_risky(ApprovalRisk.HIGH)
print(f"\n⚠️ {len(risky)} high-risk approvals")

# 4. Get unlimited
unlimited = manager.get_unlimited()
print(f"🔓 {len(unlimited)} unlimited approvals")

# 5. Summary
summary = manager.get_summary()
print(f"\nSummary:")
print(f"  Total: {summary['total_approvals']}")
print(f"  Unlimited: {summary['unlimited']}")
print(f"  High risk: {summary['high_risk']}")
print(f"  Unknown contracts: {summary['unknown_contracts']}")

# 6. Revoke all unlimited (CAREFUL!)
# results = manager.revoke_all_unlimited(Chain.ETHEREUM)
# for r in results:
#     print(f"Revoked {r.token_address}: {'✅' if r.success else '❌ ' + r.error}")
