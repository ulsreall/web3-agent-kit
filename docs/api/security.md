# Token Security Module

The security module provides token and contract risk signals for pre-trade and pre-interaction checks. It is intentionally narrower than a full smart-contract audit suite.

## Public API

```python
from web3_agent_kit.security import SecurityConfig, TokenAnalyzer

config = SecurityConfig(
    rpc_url="https://your-rpc.example",
    goplus_api_key="optional",
)
analyzer = TokenAnalyzer(config)
report = analyzer.analyze_token("0x...")

print(report.safety_score)
print(report.risk_level)
print(report.is_honeypot)
```

## Signals

- Honeypot and sellability status
- Buy and sell tax estimates
- Liquidity amount, lock status, and lock duration
- Holder concentration and whale signals
- Contract patterns such as proxy, hidden mint, blacklist, pause, ownership, fee changes, and transfer restrictions
- Verified-source and ownership signals
- Safety score, risk level, warnings, and recommendations

Unknown honeypot status is treated as unsafe by `SecurityReport.is_safe`. An API failure must not be interpreted as a safe result.

## Integrations

- GoPlus token security data when configured
- DexScreener liquidity and pair data when configured
- Direct RPC reads for supported contract checks

External provider responses are signals, not guarantees. A security report does not replace transaction simulation, spend policy, allowlists, or human confirmation.

## Scope boundary

This package does not currently expose `StaticAnalyzer`, `FuzzTester`, `ExploitBuilder`, `OnchainForensics`, or `ProtocolAuditor` classes. General Slither/Echidna workflows, exploit development, and forensic tracing should be documented and shipped as separate integrations only after they exist in the package and have deterministic tests.
