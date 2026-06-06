# Trading Module

Automated trading bots — DCA, limit orders, and more.

---

## DCA Bot (Dollar-Cost Averaging)

Automatically buy tokens at regular intervals.

```python
from web3_agent_kit.trading import DCABot

bot = DCABot(
    wallet=wallet,
    chain_manager=chain_manager,
    token_in="ETH",
    token_out="USDC",
    amount_per_buy=0.01,  # 0.01 ETH per buy
    interval_hours=24,     # Every 24 hours
)

# Start DCA
bot.start()

# Check status
status = bot.get_status()
print(f"Buys executed: {status['total_buys']}")
print(f"Total spent: {status['total_spent']} ETH")
print(f"Avg price: ${status['avg_price']:.2f}")

# Stop
bot.stop()
```

### Advanced Configuration

```python
from web3_agent_kit.trading import DCAConfig

config = DCAConfig(
    token_in="ETH",
    token_out="USDC",
    amount_per_buy=0.01,
    interval_hours=24,
    # Price-based triggers
    buy_more_if_drops=5.0,     # Buy 2x if price drops 5%
    stop_if_drops=20.0,        # Stop if price drops 20%
    take_profit_at=50.0,       # Sell 50% if price rises 50%
    max_total_spend=1.0,       # Max 1 ETH total
)

bot = DCABot(wallet=wallet, chain_manager=chain_manager, config=config)
```

---

## Sniper Bot

See [Token Sniper](../features.md#-token-sniper) in Features.

---

## Yield Optimizer

Find and auto-compound the best yield opportunities.

```python
from web3_agent_kit.trading import YieldOptimizer

optimizer = YieldOptimizer(chain_manager=chain_manager, wallet=wallet)

# Find best yields
opportunities = optimizer.scan(min_apy=5.0)
for opp in opportunities:
    print(f"{opp.protocol}: {opp.apy:.1f}% APY")

# Auto-compound
optimizer.auto_compound(min_claim_usd=10)
```
