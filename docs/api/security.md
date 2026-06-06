# Security Module

Smart contract security auditing tools — static analysis, fuzzing, and exploit development.

---

## Modules

### Static Analysis

Automated vulnerability detection using Slither.

```python
from web3_agent_kit.security import StaticAnalyzer

analyzer = StaticAnalyzer()
results = analyzer.analyze("contracts/Token.sol")

for vuln in results.vulnerabilities:
    print(f"[{vuln.severity}] {vuln.name}: {vuln.description}")
```

### Fuzzing

Property-based testing with Echidna/Foundry.

```python
from web3_agent_kit.security import FuzzTester

fuzzer = FuzzTester()
fuzzer.add_property("balance_never_negative", "assert(balanceOf(user) >= 0)")
results = fuzzer.run("contracts/Vault.sol", duration="10m")
```

### Exploit Development

Build PoC exploits for discovered vulnerabilities.

```python
from web3_agent_kit.security import ExploitBuilder

builder = ExploitBuilder(chain=Chain.ETHEREUM)
exploit = builder.build_reentrancy(
    target="0x...",
    attack_contract="contracts/Exploit.sol",
)
result = exploit.simulate()
print(f"Profit: ${result.profit_usd:.2f}")
```

### Forensics

On-chain transaction tracing and analysis.

```python
from web3_agent_kit.security import OnchainForensics

forensics = OnchainForensics(chain=Chain.ETHEREUM)
trace = forensics.trace_tx("0x...")
print(f"From: {trace.from_addr}")
print(f"Total value moved: ${trace.total_value_usd:.2f}")
print(f"Contracts involved: {trace.contracts}")
```

### Protocol Audit

Full DeFi protocol security audit.

```python
from web3_agent_kit.security import ProtocolAuditor

auditor = ProtocolAuditor()
report = auditor.audit(
    contracts=["contracts/Vault.sol", "contracts/Token.sol"],
    checks=["reentrancy", "overflow", "access_control", "oracle_manipulation"],
)
report.save("audit-report.md")
```

---

## Supported Tools

| Tool | Purpose |
|------|---------|
| **Slither** | Static analysis |
| **Echidna** | Property-based fuzzing |
| **Foundry** | Fuzz testing + simulation |
| **Mythril** | Symbolic execution |
| **Securify2** | Security patterns |

---

## 10 Built-in Skills

The security module includes 10 specialized skills for different attack vectors:

- `smart-contract-exploit` — Exploit development
- `smart-contract-static-analysis` — Automated detection
- `smart-contract-fuzzing` — Property-based testing
- `onchain-forensics` — Transaction tracing
- `recon-and-osint` — Target reconnaissance
- `web-app-pentest` — Web application testing
- `defi-protocol-audit` — Full protocol audit
- `wallet-compromise-rescue` — Rescue compromised assets
- `evm-7702-rescue` — EIP-7702 asset rescue
- `web3-bug-bounty-hunter` — Bug bounty automation
