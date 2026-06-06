# MEV Module

Maximal Extractable Value (MEV) bots — arbitrage, sandwich attacks, and liquidation.

---

## Arbitrage Bot

Find and execute cross-DEX arbitrage opportunities.

```python
from web3_agent_kit.mev import ArbitrageBot

bot = ArbitrageBot(
    chain_manager=chain_manager,
    wallet=wallet,
    min_profit_usd=5.0,
    max_gas_usd=2.0,
)

# Scan for opportunities
opportunities = bot.scan()
for opp in opportunities:
    print(f"{opp.pair}: ${opp.estimated_profit:.2f} profit")

# Auto-execute profitable ones
bot.run()
```

### Configuration

```python
from web3_agent_kit.mev import ArbitrageConfig

config = ArbitrageConfig(
    dexes=["uniswap", "sushiswap", "aerodrome"],
    pairs=["WETH/USDC", "WETH/USDT", "WBTC/WETH"],
    min_profit_usd=5.0,
    max_gas_usd=2.0,
    use_flashbots=True,  # Submit via Flashbots to avoid frontrunning
)

bot = ArbitrageBot(config=config)
```

---

## Liquidation Bot

Monitor and liquidate undercollateralized positions.

```python
from web3_agent_kit.mev import LiquidationBot

bot = LiquidationBot(
    chain_manager=chain_manager,
    wallet=wallet,
    protocols=["aave", "compound"],
)

# Monitor for liquidatable positions
bot.start(callback=lambda pos: print(f"💧 Liquidatable: {pos.user}"))
```

---

## Flashbot Support

Submit bundles directly to block builders to avoid public mempool.

```python
from web3_agent_kit.mev import FlashbotSubmitter

submitter = FlashbotSubmitter(wallet=wallet)
bundle = submitter.create_bundle([tx1, tx2, tx3])
result = submitter.send_bundle(bundle, target_block=18500000)
```
