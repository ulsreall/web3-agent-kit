#!/usr/bin/env python3
"""Security Module — token analysis example.

Demonstrates how to use the Security Module to analyze tokens
before interacting with them.

Usage:
    python examples/security_analysis.py
"""

from web3_agent_kit.security import (
    TokenAnalyzer,
    SecurityConfig,
    RiskLevel,
)


def example_quick_check():
    """Quick security check using GoPlus API."""
    print("\n" + "=" * 60)
    print("🔍 QUICK SECURITY CHECK")
    print("=" * 60)

    analyzer = TokenAnalyzer(SecurityConfig(chain="ethereum"))

    # Example tokens (replace with real addresses)
    tokens = [
        ("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "USDC"),
        ("0xdAC17F958D2ee523a2206206994597C13D831ec7", "USDT"),
        ("0x6B175474E89094C44Da98b954EedeAC495271d0F", "DAI"),
    ]

    for address, name in tokens:
        print(f"\nChecking {name} ({address[:10]}...)")
        result = analyzer.quick_check(address)
        status = "⚠️ HONEYPOT" if result["is_honeypot"] is True else ("❓ Unknown" if result["is_honeypot"] is None else "✓ Safe")
        print(f"  Status: {status}")
        print(f"  Buy Tax: {result['buy_tax']}%")
        print(f"  Sell Tax: {result['sell_tax']}%")


def example_full_analysis():
    """Full token analysis with detailed report."""
    print("\n" + "=" * 60)
    print("🔒 FULL SECURITY ANALYSIS")
    print("=" * 60)

    analyzer = TokenAnalyzer(SecurityConfig(
        chain="ethereum",
        max_buy_tax=5.0,
        max_sell_tax=5.0,
        min_liquidity_usd=10000,
    ))

    # Analyze a token (replace with real address)
    address = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"  # USDC
    print(f"\nAnalyzing: {address}")

    report = analyzer.analyze_token(address)

    # Print full report
    report.print_report()

    # Programmatic access
    print(f"\nProgrammatic Access:")
    print(f"  Safety Score: {report.safety_score}/100")
    print(f"  Risk Level: {report.risk_level.value}")
    print(f"  Is Safe: {report.is_safe}")
    print(f"  Is Honeypot: {report.is_honeypot}")
    print(f"  Is Rug Risk: {report.is_rug_risk}")


def example_honeypot_check():
    """Check if token is a honeypot."""
    print("\n" + "=" * 60)
    print("🍯 HONEYPOT CHECK")
    print("=" * 60)

    analyzer = TokenAnalyzer(SecurityConfig(chain="ethereum"))

    # Example: Check a suspicious token
    address = "0x..."  # Replace with real address
    print(f"\nChecking: {address}")

    tax = analyzer.check_honeypot(address)

    if tax.is_honeypot is True:
        print("  ⚠️ Is Honeypot: YES")
        print(f"  Buy Tax: {tax.buy_tax}%")
        print(f"  Sell Tax: {tax.sell_tax}%")
        print("  ⚠️ DO NOT BUY — you won't be able to sell!")
    elif tax.is_honeypot is None:
        print("❓ Honeypot status unknown (API failure)")
        print(f"  Buy Tax: {tax.buy_tax}%")
        print(f"  Sell Tax: {tax.sell_tax}%")
    else:
        print("✓ Not a honeypot")
        print(f"  Buy Tax: {tax.buy_tax}%")
        print(f"  Sell Tax: {tax.sell_tax}%")
        print(f"  Can Sell: {tax.can_sell}")


def example_rug_check():
    """Check rug pull risk."""
    print("\n" + "=" * 60)
    print("🧶 RUG PULL CHECK")
    print("=" * 60)

    analyzer = TokenAnalyzer(SecurityConfig(chain="ethereum"))

    address = "0x..."  # Replace with real address
    print(f"\nChecking: {address}")

    result = analyzer.check_rug_risk(address)

    print(f"  Risk Score: {result['risk_score']}/100")
    print(f"  Is Rug Risk: {result['is_rug_risk']}")

    if result["risk_factors"]:
        print("  Risk Factors:")
        for factor in result["risk_factors"]:
            print(f"    • {factor}")


def example_pre_trade_check():
    """Example: Pre-trade security check workflow."""
    print("\n" + "=" * 60)
    print("📊 PRE-TRADE SECURITY CHECK")
    print("=" * 60)

    analyzer = TokenAnalyzer(SecurityConfig(
        chain="base",
        max_buy_tax=5.0,
        min_liquidity_usd=50000,
    ))

    # Simulate a trading decision
    token_address = "0x..."  # Replace with real address

    print(f"\nPre-trade analysis for: {token_address}")

    # Step 1: Quick check
    quick = analyzer.quick_check(token_address)
    if quick["is_honeypot"]:
        print("❌ BLOCKED: Honeypot detected!")
        return

    # Step 2: Full analysis
    report = analyzer.analyze_token(token_address)

    # Step 3: Decision logic
    if report.safety_score < 30:
        print(f"❌ BLOCKED: Safety score too low ({report.safety_score}/100)")
    elif report.safety_score < 50:
        print(f"⚠️ WARNING: Medium risk ({report.safety_score}/100)")
        print("  Consider reducing position size")
    elif report.safety_score < 70:
        print(f"⚠️ CAUTION: Low risk ({report.safety_score}/100)")
        print("  Proceed with standard position")
    else:
        print(f"✓ SAFE: Good score ({report.safety_score}/100)")
        print("  Proceed with normal trading")

    # Print warnings
    if report.warnings:
        print("\n  Warnings:")
        for w in report.warnings:
            print(f"    {w}")


def main():
    """Run all examples."""
    print("🔒 Web3 Agent Kit — Security Module Examples")
    print("=" * 60)

    example_quick_check()
    example_full_analysis()
    example_honeypot_check()
    example_rug_check()
    example_pre_trade_check()

    print("\n" + "=" * 60)
    print("✅ All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
