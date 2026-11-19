# Airdrop Suite

Automated airdrop farming toolkit — discover, track, and claim airdrops across multiple platforms.

---

## Modules

### Discovery

Find new airdrop opportunities automatically.

```python
from web3_agent_kit.airdrop import AirdropDiscovery

discovery = AirdropDiscovery()

# Find new airdrops
airdrops = discovery.scan()
for a in airdrops:
    print(f"{a.name} — {a.chain} — Est. ${a.estimated_value}")
```

### Scheduler

Automate recurring airdrop tasks.

```python
from web3_agent_kit.airdrop import AirdropScheduler

scheduler = AirdropScheduler(wallet=wallet)
scheduler.add_task("daily_bridge", chain=Chain.BASE, amount=0.01)
scheduler.add_task("weekly_swap", chain=Chain.ETHEREUM, token="USDC")
scheduler.start()
```

### Multi-Wallet

Manage multiple wallets for airdrop farming.

```python
from web3_agent_kit.airdrop import MultiWalletManager

manager = MultiWalletManager.from_csv("wallets.csv")
manager.execute_on_all("swap", token_in="ETH", token_out="USDC", amount=0.01)
```

### Platform Integrations

- **Galxe** — Quest completion, credential claiming
- **Zealy** — Quest automation
- **Layer3** — Task completion
- **QuestN** — Quest participation
- **Intract** — Campaign automation
- **Gleam** — Giveaway entry

### On-Chain Actions

```python
from web3_agent_kit.airdrop import OnchainActions

actions = OnchainActions(wallet=wallet, chain_manager=chain_manager)

# Bridge small amounts to stay active
actions.bridge_daily(amount=0.001)

# Swap tokens to generate volume
actions.swap_volume(token_pair=("ETH", "USDC"), amount=0.01)

# Interact with protocols
actions.interact_with_protocol("aave", action="deposit", amount=10)
```

### Form Filler

Automated form submission for whitelist applications.

```python
from web3_agent_kit.airdrop import FormFiller

filler = FormFiller(wallet=wallet)
filler.submit(
    url="https://example.com/whitelist",
    fields={
        "twitter": "@itseywacc",
        "wallet": wallet.address,
        "email": "user@example.com",
    },
)
```

### Whitelist Grinder

Automated NFT whitelist grinding on X/Twitter.

```python
from web3_agent_kit.airdrop import WLGrinder

grinder = WLGrinder(x_account="@itseywacc", wallet=wallet)
grinder.grind(
    project_url="https://twitter.com/project/status/123",
    actions=["follow", "retweet", "comment"],
)
```

### Referral Tracking

Track referral codes and rewards.

```python
from web3_agent_kit.airdrop import ReferralTracker

tracker = ReferralTracker(wallet=wallet)
tracker.add_referral("project_x", "REF123")
rewards = tracker.get_rewards()
```

### Dashboard

Unified dashboard for all airdrop activities.

```python
from web3_agent_kit.airdrop import AirdropDashboard

dashboard = AirdropDashboard(wallets=manager.wallets)
summary = dashboard.get_summary()
print(f"Total claimed: ${summary['total_claimed']}")
print(f"Pending: {summary['pending_count']} airdrops")
```

## Reading the reports honestly

Several airdrop results are deliberately optimistic, and a summary that is taken
at face value will overstate what happened.

### Quest completion is optimistic

`ZealyExecutor.complete_quest` and `GleamExecutor.complete_task` mark a quest
done as soon as the action was submitted. If verification then fails — or there
is nothing to click, since `_verify_quest` returns `True` when no verify or claim
button exists — the quest is still marked completed and the XP is credited.
`xp_earned` / `completed_tasks` therefore mean *submitted*, not *confirmed*.

### A Telegram join counts a visit

`TelegramExecutor.join_channel` returns `True` when the page was merely opened
and no join button was visible. Joined and visited are not distinguished.

### Faucet claims

A claim is only successful on an explicit `success: true` (or the configured
`success_indicator` in a text body). `HTTP 200` with `{"success": false}` is a
failure, and a failed result carries no amount. Only a success sets the cooldown.

### Cooldowns are per faucet, not per wallet

`FaucetClaimer` stores cooldowns by faucet key in
`~/.hermes/cache/faucet_cooldowns.json`. Switching wallets does not reset them;
pass `skip_cooldown=True` when you know the faucet is ready.

### Discovery deduplication needs a path

`CampaignDiscovery.get_new_campaigns` only deduplicates across runs when a
`save_path` (or `seen_path`) is configured. Without one, every run reports the
same campaigns.

### Parsed numbers default to zero

Platform payloads send points/XP as `""`, `null` or a string. Those are coerced
to `0` rather than dropping the task, so a campaign that reports zero points may
be a campaign whose points the API did not send.
