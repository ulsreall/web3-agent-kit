# Airdrop & Grinding Landscape 2025-2026

## Comprehensive Research Document

*Last updated: June 2025*

---

## Table of Contents

1. [Quest/Reward Platforms](#1-questreward-platforms)
2. [Giveaway Platforms](#2-giveaway-platforms)
3. [DeFi/On-chain Airdrops](#3-defion-chain-airdrops)
4. [Social Tasks Commonly Required](#4-social-tasks-commonly-required)
5. [Anti-bot Measures](#5-anti-bot-measures)
6. [Farming Tools & Bots](#6-farming-tools--bots)
7. [Platform Comparison Matrix](#7-platform-comparison-matrix)
8. [Automation Strategy](#8-automation-strategy)

---

## 1. Quest/Reward Platforms

### Galxe (galxe.com)

| Attribute | Details |
|-----------|---------|
| **Type** | Quest-based campaigns, credentials, points |
| **Status** | ✅ Active — largest quest platform |
| **Users** | 15M+ unique users |
| **Auth** | OAuth (Twitter, Discord, GitHub), Wallet Connect |
| **API** | Public GraphQL API at `graphigo.prd.galaxy.eco` |
| **Anti-bot** | CAPTCHA, social verification, wallet age, on-chain proof |
| **Automation Difficulty** | Medium |
| **Reward Value** | $50-500+ per campaign |

**Task Types:**
- Twitter follow/retweet/like
- Discord join/verify
- On-chain transactions
- Quiz completion
- NFT minting
- Referral chains
- Credential building (Soulbound tokens)

**API Details:**
```graphql
# GraphQL endpoint
POST https://graphigo.prd.galaxy.eco/query

# Key queries
- campaignList(filter: {status: ACTIVE})
- credential(id: "...")
- userCredentials(address: "...")
```

**Verification Method:** OAuth token validation + on-chain transaction verification

**Anti-bot Measures:**
- GeeTest CAPTCHA on high-value campaigns
- IP rate limiting (100 req/min)
- Social account age >30 days
- Wallet balance requirements
- Unique credential per wallet

---

### Zealy (zealy.io) — formerly Crew3

| Attribute | Details |
|-----------|---------|
| **Type** | Community quests, XP leaderboard |
| **Status** | ✅ Active — merged Crew3 |
| **Users** | 5M+ users |
| **Auth** | OAuth (Twitter, Discord), Wallet Connect |
| **API** | Hidden REST API |
| **Anti-bot** | Rate limiting, social verification |
| **Automation Difficulty** | Easy-Medium |
| **Reward Value** | $20-200 per sprint |

**Task Types:**
- Social media engagement (Twitter, Discord)
- Content creation (memes, threads)
- Bug reporting
- Translation
- Community moderation
- Quiz/hackathon participation
- Daily check-ins

**API Details:**
```
# Hidden API endpoints
GET  https://api.zealy.io/communities/{slug}/quests
POST https://api.zealy.io/quests/{id}/submit

# Auth via session cookie + CSRF token
```

**Verification Method:** Manual review for content, automated for social tasks

---

### Layer3 (layer3.xyz)

| Attribute | Details |
|-----------|---------|
| **Type** | Cross-chain quests, XP system |
| **Status** | ✅ Active |
| **Users** | 3M+ users |
| **Auth** | Wallet Connect, OAuth |
| **API** | Hidden API |
| **Anti-bot** | On-chain verification, wallet activity |
| **Automation Difficulty** | Medium-Hard |
| **Reward Value** | $30-300 per quest |

**Task Types:**
- Cross-chain swaps
- Bridge transactions
- DEX interactions
- NFT minting
- Governance voting
- Testnet activities
- Social tasks

**Unique Feature:** Multi-chain activity tracking, CUBEs (on-chain credentials)

---

### Intract (intract.io)

| Attribute | Details |
|-----------|---------|
| **Type** | Community quests, XP |
| **Status** | ✅ Active |
| **Users** | 2M+ users |
| **Auth** | OAuth, Wallet Connect |
| **API** | Hidden API |
| **Anti-bot** | Social verification, CAPTCHA |
| **Automation Difficulty** | Easy-Medium |
| **Reward Value** | $10-150 per campaign |

**Task Types:**
- Social media tasks
- On-chain transactions
- Content creation
- Quiz completion
- Referral programs

---

### QuestN (questn.com)

| Attribute | Details |
|-----------|---------|
| **Type** | Quest platform |
| **Status** | ✅ Active |
| **Users** | 1M+ users |
| **Auth** | OAuth, Wallet Connect |
| **API** | Hidden API |
| **Anti-bot** | Basic verification |
| **Automation Difficulty** | Easy |
| **Reward Value** | $5-100 per quest |

**Task Types:**
- Social tasks
- On-chain tasks
- Quiz/hackathon
- Content creation

---

### TaskOn (taskon.xyz)

| Attribute | Details |
|-----------|---------|
| **Type** | Task campaigns |
| **Status** | ✅ Active |
| **Users** | 500K+ users |
| **Auth** | OAuth |
| **API** | Hidden API |
| **Anti-bot** | Basic verification |
| **Automation Difficulty** | Easy |
| **Reward Value** | $5-50 per campaign |

**Task Types:**
- Social media tasks
- Quiz completion
- Referral programs
- Content creation

---

### Port3 (port3.io)

| Attribute | Details |
|-----------|---------|
| **Type** | Social aggregator quests |
| **Status** | ✅ Active |
| **Users** | 200K+ users |
| **Auth** | OAuth, Wallet Connect |
| **API** | Public API available |
| **Anti-bot** | Social verification |
| **Automation Difficulty** | Easy-Medium |
| **Reward Value** | $10-100 per quest |

**Task Types:**
- Multi-platform social aggregation
- On-chain data quests
- Community engagement

---

### Dappback (dappback.com)

| Attribute | Details |
|-----------|---------|
| **Type** | Dapp quests |
| **Status** | ⚠️ Limited Activity |
| **Users** | 100K+ users |
| **Auth** | OAuth, Wallet Connect |
| **API** | No public API |
| **Anti-bot** | Basic verification |
| **Automation Difficulty** | Easy |
| **Reward Value** | $5-50 per quest |

---

## 2. Giveaway Platforms

### Gleam.io

| Attribute | Details |
|-----------|---------|
| **Type** | Social contests/giveaways |
| **Status** | ✅ Active |
| **API** | No public API (hidden) |
| **Anti-bot** | CAPTCHA, IP detection, email verification |
| **Automation Difficulty** | Hard |
| **Reward Value** | $10-1000+ per giveaway |

**Task Types:**
- Twitter follow/retweet/like
- Discord join
- YouTube subscribe
- Email signup
- Referral entries
- Blog comments

**Anti-bot Measures:**
- hCaptcha/ReCAPTCHA
- IP geolocation
- Cookie tracking
- Email verification
- Browser fingerprinting

---

### SweepWidget

| Attribute | Details |
|-----------|---------|
| **Type** | Giveaway platform |
| **Status** | ✅ Active |
| **API** | No public API |
| **Anti-bot** | CAPTCHA, email verification |
| **Automation Difficulty** | Medium |
| **Reward Value** | $10-500 per giveaway |

---

### Galxe Compass

| Attribute | Details |
|-----------|---------|
| **Type** | Token launch platform |
| **Status** | ✅ Active |
| **API** | Uses Galxe API |
| **Anti-bot** | Wallet verification, social proof |
| **Automation Difficulty** | Medium |
| **Reward Value** | $100-5000+ (token allocations) |

---

### Cookie3

| Attribute | Details |
|-----------|---------|
| **Type** | Marketing quests |
| **Status** | ✅ Active |
| **API** | Hidden API |
| **Anti-bot** | Social verification |
| **Automation Difficulty** | Easy-Medium |
| **Reward Value** | $5-100 per quest |

---

### Inspect (inspect.xyz)

| Attribute | Details |
|-----------|---------|
| **Type** | Twitter-based rewards |
| **Status** | ✅ Active |
| **API** | Hidden API |
| **Anti-bot** | Twitter OAuth |
| **Automation Difficulty** | Medium |
| **Reward Value** | $10-50 per task |

**Task Types:**
- Twitter engagement tracking
- Content creation
- Community participation

---

## 3. DeFi/On-chain Airdrops

### Testnet Faucets (Active as of 2025)

| Chain | Faucet URL | Status | Token |
|-------|-----------|--------|-------|
| Ethereum Sepolia | sepoliafaucet.com | ✅ Active | ETH |
| Ethereum Holesky | holesky-faucet.pk910.de | ✅ Active | ETH |
| Arbitrum Sepolia | faucet.quicknode.com | ✅ Active | ETH |
| Optimism Sepolia | faucet.quicknode.com | ✅ Active | ETH |
| Base Sepolia | faucet.quicknode.com | ✅ Active | ETH |
| Scroll Sepolia | scroll.io/faucet | ✅ Active | ETH |
| zkSync Sepolia | portal.zksync.io | ✅ Active | ETH |
| Linea Sepolia | faucet.linea.build | ✅ Active | ETH |
| Polygon Amoy | faucet.polygon.technology | ✅ Active | POL |
| Avalanche Fuji | faucet.avax.network | ✅ Active | AVAX |
| BNB Testnet | testnet.bnbchain.org | ✅ Active | tBNB |
| Monad Testnet | monad.xyz/faucet | ✅ Active | MONAD |

---

### DEX Interactions

#### Uniswap

| Attribute | Details |
|-----------|---------|
| **Chains** | Ethereum, Arbitrum, Optimism, Base, Polygon, BNB |
| **Tasks** | Swap, provide liquidity, limit orders |
| **Points** | Uniswap v4 hooks incentives |
| **Anti-bot** | On-chain verification |
| **Automation** | Medium (requires gas management) |

```python
# Example swap interaction
from web3 import Web3

# Swap ETH for USDC on Uniswap
def swap_eth_to_usdc(amount_eth):
    router = web3.eth.contract(address=UNISWAP_ROUTER, abi=ROUTER_ABI)
    # ... execute swap
```

#### Jupiter (Solana)

| Attribute | Details |
|-----------|---------|
| **Chain** | Solana |
| **Tasks** | Swap, DCA, limit orders |
| **Points** | JUP staking rewards |
| **Anti-bot** | On-chain verification |
| **Automation** | Easy-Medium |

#### Aerodrome (Base)

| Attribute | Details |
|-----------|---------|
| **Chain** | Base |
| **Tasks** | Swap, provide liquidity, vote |
| **Points** | veAERO incentives |
| **Anti-bot** | On-chain verification |
| **Automation** | Medium |

---

### Bridge Usage

| Bridge | Chains | Status | Airdrop Potential |
|--------|--------|--------|-------------------|
| Stargate | Multi-chain | ✅ Active | High (STG rewards) |
| Across | Multi-chain | ✅ Active | High (ACX rewards) |
| Hop Protocol | L2s | ✅ Active | Medium |
| Wormhole | Multi-chain | ✅ Active | High |
| LayerZero | Multi-chain | ✅ Active | Very High |
| deBridge | Multi-chain | ✅ Active | High |
| Rhino.fi | Multi-chain | ✅ Active | Medium |

---

### Lending Protocols

| Protocol | Chains | Status | Points Program |
|----------|--------|--------|----------------|
| Aave | Multi-chain | ✅ Active | AAVE staking |
| Compound | Ethereum, Base | ✅ Active | COMP rewards |
| Radiant | Arbitrum, BNB | ✅ Active | RDNT rewards |
| Venus | BNB | ✅ Active | XVS rewards |
| Morpho | Ethereum, Base | ✅ Active | MORPHO rewards |
| Spark | Ethereum | ✅ Active | SPK rewards |

---

### Restaking

| Protocol | Status | Points | Tasks |
|----------|--------|--------|-------|
| EigenLayer | ✅ Active | EIGEN points | Restake ETH/LSTs |
| Ether.fi | ✅ Active | eETH points | Stake ETH |
| Renzo | ✅ Active | ezETH points | Restake ETH |
| Puffer Finance | ✅ Active | PUFFER points | Restake ETH |
| Kelp DAO | ✅ Active | rsETH points | Restake ETH |
| Swell | ✅ Active | swETH points | Stake ETH |
| Mellow Finance | ✅ Active | Points | LRT vaults |

---

### Layer 2 Activity

#### Base

| Task | Points/Incentive | Frequency |
|------|------------------|-----------|
| Swap on Aerodrome | HIGH | Weekly |
| Swap on Uniswap | MEDIUM | Weekly |
| Mint NFTs | LOW | Daily |
| Bridge from ETH | HIGH | Once |
| Use Coinbase Wallet | MEDIUM | Daily |

#### Arbitrum

| Task | Points/Incentive | Frequency |
|------|------------------|-----------|
| GMX trading | HIGH | Weekly |
| Radiant lending | HIGH | Weekly |
| Uniswap swaps | MEDIUM | Weekly |
| Governance voting | LOW | Monthly |
| Bridge usage | HIGH | Once |

#### Optimism

| Task | Points/Incentive | Frequency |
|------|------------------|-----------|
| Velodrome swaps | HIGH | Weekly |
| OP delegation | HIGH | Once |
| RetroPGF participation | HIGH | Varies |
| Synthetix staking | MEDIUM | Weekly |

#### zkSync

| Task | Points/Incentive | Frequency |
|------|------------------|-----------|
| SyncSwap | HIGH | Weekly |
| Mute.io | MEDIUM | Weekly |
| Era lending | MEDIUM | Weekly |
| NFT minting | LOW | Daily |
| Testnet activity | LOW | Daily |

#### Scroll

| Task | Points/Incentive | Frequency |
|------|------------------|-----------|
| Skydrome | HIGH | Weekly |
| Nuri Finance | MEDIUM | Weekly |
| Testnet activity | LOW | Daily |
| Bridge from ETH | HIGH | Once |

#### Linea

| Task | Points/Incentive | Frequency |
|------|------------------|-----------|
| Linea DeFi Voyage | HIGH | Weekly |
| SyncSwap | MEDIUM | Weekly |
| NILE DEX | MEDIUM | Weekly |
| Testnet activity | LOW | Daily |

#### Blast

| Task | Points/Incentive | Frequency |
|------|------------------|-----------|
| DEX swaps | HIGH | Weekly |
| Lending | MEDIUM | Weekly |
| NFT minting | LOW | Daily |
| Yield farming | HIGH | Daily |

---

## 4. Social Tasks Commonly Required

### Twitter/X Tasks

| Task | Frequency | Verification Method |
|------|-----------|---------------------|
| Follow @account | Once | Twitter API check |
| Retweet post | Per campaign | Tweet ID verification |
| Like post | Per campaign | Twitter API check |
| Reply to post | Per campaign | Tweet ID + content check |
| Quote tweet | Per campaign | Tweet ID verification |
| Tweet with hashtag | Per campaign | Search API |
| Join Twitter Space | Per campaign | Attendance tracking |
| Create thread | Per campaign | Manual review |

**Automation Notes:**
- Rate limits: 50 API calls/15min (basic), 300/15min (elevated)
- Shadow ban risk with excessive engagement
- Account age >30 days typically required
- Phone verification often required

---

### Discord Tasks

| Task | Frequency | Verification Method |
|------|-----------|---------------------|
| Join server | Once | Guild member check |
| Verify role | Once | Role assignment |
| React to message | Per campaign | Reaction check |
| Reach level | Progressive | Bot tracking (MEE6, Carl-bot) |
| Send message | Per campaign | Message ID check |
| Complete captcha | Once per server | Bot verification |

**Automation Notes:**
- Discord API: 50 requests/second
- Bot detection: rapid join/leave patterns
- Account age >7 days typically required
- Phone verification for many servers

---

### Telegram Tasks

| Task | Frequency | Verification Method |
|------|-----------|---------------------|
| Join group | Once | Member check |
| Join channel | Once | Subscriber check |
| Verify via bot | Once | Bot interaction |
| React to message | Per campaign | Reaction check |

**Automation Notes:**
- Telegram API: 30 requests/second
- Flood wait handling required
- Account age >7 days typically required

---

### YouTube Tasks

| Task | Frequency | Verification Method |
|------|-----------|---------------------|
| Subscribe | Once | YouTube API |
| Like video | Per campaign | YouTube API |
| Comment | Per campaign | Comment ID check |
| Watch duration | Per campaign | View tracking |

**Automation Notes:**
- YouTube API quota: 10,000 units/day
- Google account required
- Anti-bot: watch time verification

---

### GitHub Tasks

| Task | Frequency | Verification Method |
|------|-----------|---------------------|
| Star repo | Once | GitHub API |
| Fork repo | Once | GitHub API |
| Contribute PR | Per campaign | PR merge check |
| Follow user | Once | GitHub API |

**Automation Notes:**
- GitHub API: 5,000 requests/hour (authenticated)
- Account age >30 days recommended
- Email verification required

---

### Medium Tasks

| Task | Frequency | Verification Method |
|------|-----------|---------------------|
| Follow publication | Once | Manual check |
| Clap article | Per campaign | Manual check |
| Comment | Per campaign | Comment ID check |

---

### Reddit Tasks

| Task | Frequency | Verification Method |
|------|-----------|---------------------|
| Join subreddit | Once | Member check |
| Upvote post | Per campaign | Manual check |
| Comment | Per campaign | Comment ID check |

---

## 5. Anti-bot Measures

### CAPTCHA Types by Platform

| Platform | CAPTCHA Type | Difficulty |
|----------|--------------|------------|
| Galxe | GeeTest v3/v4 | Hard |
| Gleam | hCaptcha, ReCAPTCHA v3 | Hard |
| Zealy | ReCAPTCHA v2 | Medium |
| Layer3 | Custom | Medium |
| Intract | ReCAPTCHA v2 | Medium |
| QuestN | Basic | Easy |
| TaskOn | Basic | Easy |

### IP/VPN Detection

| Platform | VPN Detection | IP Limits |
|----------|---------------|-----------|
| Galxe | Yes | 5 accounts/IP |
| Gleam | Yes | 1 entry/IP |
| Zealy | Partial | 3 accounts/IP |
| Layer3 | Yes | 3 accounts/IP |

### Browser Fingerprinting

| Method | Platforms Using |
|--------|-----------------|
| Canvas fingerprint | Galxe, Gleam |
| WebGL fingerprint | Galxe |
| Navigator properties | Galxe, Layer3 |
| Font enumeration | Gleam |

### Social Account Requirements

| Platform | Min Account Age | Phone Required | Email Required |
|----------|-----------------|----------------|----------------|
| Galxe | 30 days | Sometimes | Yes |
| Zealy | 7 days | No | Yes |
| Gleam | 30 days | Sometimes | Yes |
| Layer3 | 30 days | No | Yes |

### On-chain Activity Requirements

| Requirement | Purpose | Platforms |
|-------------|---------|-----------|
| Minimum balance | Sybil prevention | Galxe, Layer3 |
| Transaction count | Activity proof | Galxe, Layer3, Intract |
| Wallet age | Sybil prevention | Galxe |
| Specific interactions | Targeted farming | Layer3, Galxe |

### Sybil Detection Methods

1. **On-chain clustering** — Multiple wallets from same funding source
2. **Behavioral analysis** — Identical transaction patterns
3. **Timing analysis** — Simultaneous claim attempts
4. **Graph analysis** — Social connections between wallets
5. **IP clustering** — Multiple accounts from same IP
6. **Device fingerprinting** — Same browser/device for multiple wallets
7. **Funding source tracing** — All wallets funded from same CEX/address

---

## 6. Farming Tools & Bots

### Commercial Bots

#### Multibot (multibot.io)

| Attribute | Details |
|-----------|---------|
| **Price** | $50-200/month |
| **Features** | Multi-chain, wallet management, task automation |
| **Chains** | EVM chains, Solana |
| **Anti-bot Bypass** | Built-in CAPTCHA solving |

#### Farming Bot Pro

| Attribute | Details |
|-----------|---------|
| **Price** | $100-500/month |
| **Features** | Quest automation, social tasks, wallet rotation |
| **Platforms** | Galxe, Zealy, Layer3 |
| **Anti-bot Bypass** | Residential proxies, CAPTCHA solving |

#### Airdrop Farmer Bot

| Attribute | Details |
|-----------|---------|
| **Price** | $30-100/month |
| **Features** | Social task automation, multi-account |
| **Platforms** | Gleam, Galxe, Zealy |
| **Anti-bot Bypass** | Basic CAPTCHA solving |

---

### Open Source Tools

#### web3-agent-kit (this project)

| Attribute | Details |
|-----------|---------|
| **URL** | github.com/nousresearch/web3-agent-kit |
| **Features** | AI-powered DeFi automation, multi-chain |
| **Language** | Python |
| **Status** | Active development |

#### AirdropBot (various forks)

| Attribute | Details |
|-----------|---------|
| **URL** | github.com/airdropbot/airdropbot |
| **Features** | Quest automation, social tasks |
| **Language** | Python, JavaScript |
| **Status** | Community maintained |

#### Galxe-Quest-Bot

| Attribute | Details |
|-----------|---------|
| **URL** | github.com/galxe-quest-bot |
| **Features** | Galxe quest automation |
| **Language** | JavaScript |
| **Status** | Semi-active |

#### Multibot-CLI

| Attribute | Details |
|-----------|---------|
| **URL** | github.com/multibot-cli |
| **Features** | Command-line quest automation |
| **Language** | Go |
| **Status** | Active |

---

### Browser Extensions

| Extension | Features | Platforms |
|-----------|----------|-----------|
| Airdrop Tracker | Track eligibility | All |
| DeBank | Wallet portfolio | All |
| Rabby Wallet | Multi-chain wallet | EVM |
| Quest Helper | Quest completion | Galxe, Zealy |

---

### Telegram Bots

| Bot | Features | Price |
|-----|----------|-------|
| @AirdropAlertBot | Airdrop notifications | Free |
| @QuestTrackerBot | Quest tracking | Free |
| @GalxeBot | Galxe notifications | Free |
| @Layer3Bot | Layer3 notifications | Free |

---

## 7. Platform Comparison Matrix

| Platform | Users | API | Anti-bot | Automation | Reward |
|----------|-------|-----|----------|------------|--------|
| Galxe | 15M+ | Public GraphQL | Hard | Medium | $50-500 |
| Zealy | 5M+ | Hidden | Medium | Easy-Med | $20-200 |
| Layer3 | 3M+ | Hidden | Hard | Med-Hard | $30-300 |
| Intract | 2M+ | Hidden | Medium | Easy-Med | $10-150 |
| QuestN | 1M+ | Hidden | Easy | Easy | $5-100 |
| TaskOn | 500K+ | Hidden | Easy | Easy | $5-50 |
| Port3 | 200K+ | Public | Medium | Easy-Med | $10-100 |
| Gleam | 10M+ | Hidden | Hard | Hard | $10-1000 |
| EigenLayer | 500K+ | On-chain | Medium | Medium | $100-5000 |
| LayerZero | 1M+ | On-chain | Hard | Hard | $100-10000 |

---

## 8. Automation Strategy

### Recommended Farming Stack

```yaml
# wallet_management:
#   - HD wallet derivation
#   - Multi-wallet rotation
#   - Gas management across chains

# social_accounts:
#   - Twitter: aged accounts (>30 days)
#   - Discord: verified accounts
#   - Telegram: aged accounts (>7 days)

# tools:
#   - CAPTCHA solving service (2captcha, anticaptcha)
#   - Residential proxies
#   - Browser automation (Puppeteer, Playwright)
#   - Web3 libraries (ethers.js, web3.py)

# chains:
#   - Ethereum mainnet
#   - Base, Arbitrum, Optimism
#   - zkSync, Scroll, Linea
#   - Solana (Jupiter, Raydium)
```

### Daily Routine

```yaml
morning:
  - Check new quests on Galxe, Zealy, Layer3
  - Complete social tasks
  - Bridge small amounts between L2s

afternoon:
  - DEX swaps on target chains
  - Lending protocol interactions
  - NFT minting on active chains

evening:
  - Claim earned rewards
  - Update tracking spreadsheet
  - Monitor for new airdrop announcements
```

### Risk Management

1. **Gas costs** — Keep 0.01-0.05 ETH per chain
2. **Wallet separation** — Never reuse wallets across campaigns
3. **Timing** — Spread activities to avoid pattern detection
4. **Diversification** — Farm multiple protocols simultaneously
5. **Documentation** — Track all transactions for tax purposes

---

## Appendix A: Active Airdrop Programs (June 2025)

| Protocol | Type | Points System | Status |
|----------|------|---------------|--------|
| EigenLayer | Restaking | EIGEN points | ✅ Active |
| Ether.fi | Staking | eETH points | ✅ Active |
| Renzo | Restaking | ezETH points | ✅ Active |
| LayerZero | Bridge | ZRO points | ✅ Active |
| Wormhole | Bridge | W points | ✅ Active |
| Stargate | Bridge | STG rewards | ✅ Active |
| Across | Bridge | ACX rewards | ✅ Active |
| Morpho | Lending | MORPHO points | ✅ Active |
| Spark | Lending | SPK points | ✅ Active |
| Base | L2 | Activity-based | ✅ Active |
| Scroll | L2 | Activity-based | ✅ Active |
| Linea | L2 | DeFi Voyage | ✅ Active |
| Blast | L2 | Points | ✅ Active |
| Monad | L1 | Testnet | ✅ Active |

---

## Appendix B: Useful Resources

- **Airdrop Tracking:** [earni.fi](https://earni.fi), [airdrops.io](https://airdrops.io)
- **DeFi Analytics:** [DeBank](https://debank.com), [Zapper](https://zapper.fi)
- **Points Tracking:** [PointsBoard](https://pointsboard.xyz)
- **Social Verification:** [Galxe Passport](https://galxe.com/passport)

---

*This document is for research purposes. Always verify platform status and terms of service before engaging in farming activities.*
