# 🤖 Web3 Agent Kit — Telegram Bot

A ready-to-deploy Telegram bot showcasing web3-agent-kit features.

## Features

- `/balance` — Check wallet balance across chains
- `/portfolio` — Full portfolio view with USD values
- `/dca` — Create & manage DCA (Dollar-Cost Averaging) orders
- `/gas` — Check gas prices with recommendations
- `/help` — Command list

Inline keyboard buttons for quick navigation.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables
cp .env.example .env
# Edit .env with your values

# 3. Run
python bot.py
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | Get from @BotFather |
| `PRIVATE_KEY` | ✅ | Wallet private key |
| `TELEGRAM_OWNER_ID` | ❌ | Your Telegram user ID |
| `ETH_RPC` | ❌ | Custom Ethereum RPC |

## Screenshots

The bot features:
- Inline keyboard buttons for easy navigation
- Markdown-formatted messages
- Real-time balance & portfolio data
- DCA order management with history
- Gas price monitoring with recommendations

## Deploy

### Systemd (recommended)
```bash
sudo cp web3-bot.service /etc/systemd/system/
sudo systemctl enable web3-bot
sudo systemctl start web3-bot
```

### PM2
```bash
pm2 start bot.py --interpreter python3 --name web3-bot
```

### Screen
```bash
screen -S web3-bot
python bot.py
# Ctrl+A, D to detach
```
