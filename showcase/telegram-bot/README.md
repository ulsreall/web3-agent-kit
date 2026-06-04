# 🤖 Web3 Agent Telegram Bot

A powerful Telegram bot for Web3 operations, built with [web3-agent-kit](https://github.com/ulsreall/web3-agent-kit).

![Demo](demo.gif)

## Features

- 💰 **Check Balance** — View ETH + token balances
- 💱 **Swap Tokens** — Uniswap V2 swaps with quote confirmation
- 📊 **Portfolio** — Track holdings and P&L
- 🎯 **Token Sniper** — Analyze new tokens for safety
- 🌉 **Bridge** — Cross-chain transfers via Li.Fi/Socket
- ⛓️ **Multi-Chain** — Ethereum, Base, Arbitrum, Optimism, Polygon

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export TELEGRAM_BOT_TOKEN="your_bot_token"
export WALLET_ADDRESS="0x..."
export PRIVATE_KEY="0x..."

# Run the bot
python bot.py
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/balance` | Check wallet balance |
| `/swap 0.1 ETH USDC` | Swap tokens |
| `/portfolio` | View portfolio |
| `/snipe <address>` | Analyze token |
| `/bridge 100 USDC arbitrum` | Bridge assets |
| `/chain ethereum` | Switch chain |

## Screenshots

### Balance Check
```
💰 Wallet Balance

Native: 1.5 ETH
USD Value: $4,500.00

Top Tokens:
• USDC: 1000.00 ($1,000.00)
• UNI: 50.0 ($350.00)
```

### Swap Quote
```
💱 Swap Quote

From: 0.1 ETH
To: ~300.00 USDC
Price Impact: 0.01%
Gas: ~$5.00

[✅ Confirm] [❌ Cancel]
```

### Token Analysis
```
🔍 Token Info

Name: Example Token (EXT)
Price: $0.00000100
Liquidity: $50,000
Safety: 🟢 Safe

Checks:
• Honeypot: ✅
• Mint Auth: ✅
• LP Locked: ✅
```

## Architecture

```
┌─────────────────┐
│  Telegram Bot   │
├─────────────────┤
│  web3-agent-kit │
├─────────────────┤
│  Uniswap V2     │
│  Li.Fi Bridge   │
│  Portfolio      │
│  Token Sniper   │
├─────────────────┤
│  Ethereum       │
│  Base           │
│  Arbitrum       │
│  Optimism       │
│  Polygon        │
└─────────────────┘
```

## Security

- Governor limits per-transaction and daily spending
- Safety checks before token swaps
- Confirmation required for all transactions
- Private keys never logged or exposed

## License

MIT
