# Risk Disclosure

> **Last updated:** v1.15.0 (2026-07-23)

This document describes known risks of using Web3 Agent Kit. **By using this software, you accept these risks.**

---

## 1. Financial Loss

Web3 Agent Kit executes real financial transactions on blockchains. Risks include:

- **Smart contract risk:** Interacting with DeFi protocols (Uniswap, Aave, Curve) may result in total loss of funds if those contracts are exploited.
- **Slippage:** Automated swaps may execute at unfavorable rates, especially during high volatility or low liquidity.
- **Gas price spikes:** Transactions may fail or cost more than expected during network congestion.
- **User error:** Incorrect configuration (wrong address, incorrect amount, wrong chain) can result in irreversible fund loss.

**Mitigation:** Use the `SpendGovernor` to set per-transaction, daily, and session limits. Always test on testnets first.

## 2. Security Risks

- **Private key exposure:** If the machine running the agent is compromised, private keys loaded into memory could be extracted.
- **API key leaks:** Third-party API keys (RPC, blockchain explorers) configured in `.env` may be exposed if the environment is shared.
- **Dependency vulnerabilities:** Third-party packages may contain security flaws.

**Mitigation:** Run agents in isolated environments. Use environment variables for secrets. Enable CI/CD security scanning (Dependabot, pip-audit).

## 3. Agent Autonomy Risks

- **Unintended transactions:** An AI agent may misinterpret instructions and execute unintended swaps, transfers, or approvals.
- **Infinite loops:** Poorly configured agents may repeatedly execute the same action, draining funds through fees.
- **Prompt injection:** If the agent processes external input (tweets, Discord messages, web pages), it may be manipulated into executing malicious transactions.

**Mitigation:** Always enable the `SpendGovernor` with appropriate limits. Use the kill switch for emergency stops. Do not connect agents to untrusted external data sources.

## 4. Legal & Regulatory

- **Jurisdiction-dependent:** Cryptocurrency regulations vary by country. Users are responsible for ensuring their use complies with local laws.
- **No warranty:** This software is provided "as is" without warranty of any kind.

## 5. Operational Risks

- **RPC downtime:** If configured RPC endpoints are unavailable, the agent cannot execute transactions.
- **Rate limits:** Public RPC endpoints and API services may rate-limit or block automated requests.
- **Chain reorganizations:** Transactions may be reverted during blockchain reorgs.

## 6. Dependency Risks

- **Web3.py:** Core dependency, subject to its own security vulnerabilities and breaking changes.
- **Solana-py:** Solana support depends on third-party library maintenance.
- **GoPlus API:** Honeypot checks rely on an external API that may be unavailable or return incorrect data.

## Summary

| Risk | Severity | Mitigation |
|------|----------|------------|
| Financial loss | **High** | SpendGovernor, testnet testing |
| Private key exposure | **High** | Isolated environments, .env secrets |
| Agent mistakes | **Medium** | SpendGovernor, kill switch |
| Prompt injection | **Medium** | Limit external data sources |
| RPC / API downtime | **Medium** | Configure fallback providers |
| Dependency vulnerabilities | **Low-Medium** | Dependabot, pip-audit in CI |

---

*This list is not exhaustive. Use at your own risk.*