"""Security Module — honeypot detection, rug pull checker, contract audit.

Provides security analysis for tokens and smart contracts before
interacting with them. Essential for snipers, traders, and airdrop farmers.

Features:
- Honeypot detection (can buy but can't sell)
- Rug pull risk assessment
- Contract audit (hidden mint, blacklist, proxy patterns)
- Tax checker (buy/sell tax)
- Liquidity analysis
- Token holder analysis
- Safety score (0-100)

Usage::

    from web3_agent_kit.security import TokenAnalyzer, SecurityConfig

    analyzer = SecurityConfig(rpc_url="https://eth.llamarpc.com")
    report = analyzer.analyze_token("0x...")
    print(f"Safety Score: {report.safety_score}/100")
    print(f"Is Honeypot: {report.is_honeypot}")
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level classification."""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ContractPattern(Enum):
    """Known contract patterns."""
    # Dangerous patterns
    HIDDEN_MINT = "hidden_mint"
    BLACKLIST = "blacklist"
    PAUSE = "pause"
    PROXY = "proxy"
    SELF_DESTRUCT = "self_destruct"
    OWNERSHIP_RENOUNCED = "ownership_renounced"
    MAX_TX_LIMIT = "max_tx_limit"
    MAX_WALLET_LIMIT = "max_wallet_limit"
    ANTI_BOT = "anti_bot"
    FEE_CHANGE = "fee_change"
    TRADING_COOLDOWN = "trading_cooldown"
    WHITELIST = "whitelist"
    TRANSFER_RESTRICTION = "transfer_restriction"

    # Positive patterns
    VERIFIED_SOURCE = "verified_source"
    LOCKED_LIQUIDITY = "locked_liquidity"
    RENOUNCED_OWNERSHIP = "renounced_ownership"
    NO_MINT = "no_mint"
    NO_PAUSE = "no_pause"


@dataclass
class TokenInfo:
    """Basic token information."""
    address: str
    name: str = ""
    symbol: str = ""
    decimals: int = 18
    total_supply: float = 0.0
    owner: str = ""
    is_verified: bool = False
    chain: str = "ethereum"
    deployer: str = ""
    deploy_time: Optional[float] = None
    holder_count: int = 0


@dataclass
class TaxInfo:
    """Token tax information."""
    buy_tax: float = 0.0
    sell_tax: float = 0.0
    is_honeypot: bool = False
    can_sell: bool = True
    buy_gas: int = 0
    sell_gas: int = 0
    error: str = ""

    @property
    def is_high_tax(self) -> bool:
        """Check if tax is suspiciously high (>10%)."""
        return self.buy_tax > 10 or self.sell_tax > 10

    @property
    def is_scam_tax(self) -> bool:
        """Check if tax indicates scam (>50%)."""
        return self.buy_tax > 50 or self.sell_tax > 50


@dataclass
class LiquidityInfo:
    """Liquidity information."""
    total_liquidity_usd: float = 0.0
    locked_percent: float = 0.0
    lock_duration_days: int = 0
    dex: str = ""
    pair_address: str = ""
    is_locked: bool = False
    lock_platform: str = ""

    @property
    def is_low_liquidity(self) -> bool:
        """Check if liquidity is low (<$10k)."""
        return self.total_liquidity_usd < 10000

    @property
    def is_well_locked(self) -> bool:
        """Check if liquidity is well locked (>80% for >30 days)."""
        return self.locked_percent > 80 and self.lock_duration_days > 30


@dataclass
class HolderInfo:
    """Token holder analysis."""
    total_holders: int = 0
    top10_percent: float = 0.0
    top20_percent: float = 0.0
    dev_hold_percent: float = 0.0
    is_concentrated: bool = False
    whale_count: int = 0

    @property
    def is_risky_concentration(self) -> bool:
        """Check if top holders hold too much (>50%)."""
        return self.top10_percent > 50


@dataclass
class ContractAudit:
    """Smart contract audit results."""
    is_verified: bool = False
    is_proxy: bool = False
    has_hidden_mint: bool = False
    has_blacklist: bool = False
    has_pause: bool = False
    has_self_destruct: bool = False
    has_ownership: bool = False
    is_ownership_renounced: bool = False
    has_max_tx: bool = False
    has_max_wallet: bool = False
    has_anti_bot: bool = False
    has_fee_change: bool = False
    has_cooldown: bool = False
    has_whitelist: bool = False
    has_transfer_restriction: bool = False
    detected_patterns: list[ContractPattern] = field(default_factory=list)
    risk_factors: list[str] = field(default_factory=list)

    @property
    def risk_score(self) -> int:
        """Calculate risk score (0=safe, 100=dangerous)."""
        score = 0
        if not self.is_verified:
            score += 30
        if self.is_proxy:
            score += 20
        if self.has_hidden_mint:
            score += 40
        if self.has_blacklist:
            score += 25
        if self.has_pause:
            score += 20
        if self.has_self_destruct:
            score += 30
        if self.has_ownership and not self.is_ownership_renounced:
            score += 15
        if self.has_fee_change:
            score += 20
        if self.has_transfer_restriction:
            score += 15
        return min(100, score)


@dataclass
class SecurityReport:
    """Complete security analysis report."""
    token: TokenInfo
    tax: TaxInfo
    liquidity: LiquidityInfo
    holders: HolderInfo
    contract: ContractAudit
    safety_score: int = 0
    risk_level: RiskLevel = RiskLevel.MEDIUM
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    analyzed_at: float = field(default_factory=time.time)

    @property
    def is_safe(self) -> bool:
        """Check if token is considered safe."""
        return self.safety_score >= 70 and not self.tax.is_honeypot

    @property
    def is_honeypot(self) -> bool:
        """Check if token is a honeypot."""
        return self.tax.is_honeypot

    @property
    def is_rug_risk(self) -> bool:
        """Check if token has rug pull risk."""
        return (
            self.contract.has_hidden_mint
            or self.liquidity.locked_percent < 50
            or self.holders.is_risky_concentration
        )

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "token": {
                "address": self.token.address,
                "name": self.token.name,
                "symbol": self.token.symbol,
                "chain": self.token.chain,
            },
            "safety_score": self.safety_score,
            "risk_level": self.risk_level.value,
            "is_safe": self.is_safe,
            "is_honeypot": self.is_honeypot,
            "is_rug_risk": self.is_rug_risk,
            "tax": {
                "buy_tax": self.tax.buy_tax,
                "sell_tax": self.tax.sell_tax,
                "can_sell": self.tax.can_sell,
            },
            "liquidity": {
                "total_usd": self.liquidity.total_liquidity_usd,
                "locked_percent": self.liquidity.locked_percent,
                "is_locked": self.liquidity.is_locked,
            },
            "holders": {
                "total": self.holders.total_holders,
                "top10_percent": self.holders.top10_percent,
                "is_concentrated": self.holders.is_concentrated,
            },
            "contract": {
                "is_verified": self.contract.is_verified,
                "has_hidden_mint": self.contract.has_hidden_mint,
                "has_blacklist": self.contract.has_blacklist,
                "has_pause": self.contract.has_pause,
                "risk_score": self.contract.risk_score,
            },
            "warnings": self.warnings,
            "recommendations": self.recommendations,
        }

    def print_report(self) -> str:
        """Print formatted security report."""
        lines = [
            "╔══════════════════════════════════════════════════════════╗",
            "║              🔒 SECURITY ANALYSIS REPORT                ║",
            "╠══════════════════════════════════════════════════════════╣",
            f"║  Token: {self.token.name} ({self.token.symbol})",
            f"║  Address: {self.token.address[:20]}...",
            f"║  Chain: {self.token.chain}",
            "╠══════════════════════════════════════════════════════════╣",
        ]

        # Safety Score
        score_bar = "█" * (self.safety_score // 5) + "░" * (20 - self.safety_score // 5)
        lines.append(f"║  Safety Score: {self.safety_score}/100 [{score_bar}]")

        # Risk Level
        risk_emoji = {
            RiskLevel.SAFE: "🟢",
            RiskLevel.LOW: "🟡",
            RiskLevel.MEDIUM: "🟠",
            RiskLevel.HIGH: "🔴",
            RiskLevel.CRITICAL: "⛔",
        }
        lines.append(f"║  Risk Level: {risk_emoji.get(self.risk_level, '⚪')} {self.risk_level.value.upper()}")

        # Tax
        lines.extend([
            "╠══════════════════════════════════════════════════════════╣",
            "║  TAX INFO",
            f"║    Buy Tax: {self.tax.buy_tax}%",
            f"║    Sell Tax: {self.tax.sell_tax}%",
            f"║    Can Sell: {'✓' if self.tax.can_sell else '✗ HONEYPOT!'}",
        ])

        # Liquidity
        lines.extend([
            "╠══════════════════════════════════════════════════════════╣",
            "║  LIQUIDITY",
            f"║    Total: ${self.liquidity.total_liquidity_usd:,.0f}",
            f"║    Locked: {self.liquidity.locked_percent}%",
            f"║    Lock Duration: {self.liquidity.lock_duration_days} days",
        ])

        # Holders
        lines.extend([
            "╠══════════════════════════════════════════════════════════╣",
            "║  HOLDERS",
            f"║    Total: {self.holders.total_holders:,}",
            f"║    Top 10 Hold: {self.holders.top10_percent}%",
            f"║    Concentrated: {'⚠️ YES' if self.holders.is_concentrated else '✓ No'}",
        ])

        # Contract
        lines.extend([
            "╠══════════════════════════════════════════════════════════╣",
            "║  CONTRACT",
            f"║    Verified: {'✓' if self.contract.is_verified else '✗'}",
            f"║    Proxy: {'⚠️ YES' if self.contract.is_proxy else '✓ No'}",
            f"║    Hidden Mint: {'⚠️ YES' if self.contract.has_hidden_mint else '✓ No'}",
            f"║    Blacklist: {'⚠️ YES' if self.contract.has_blacklist else '✓ No'}",
            f"║    Pause: {'⚠️ YES' if self.contract.has_pause else '✓ No'}",
        ])

        # Warnings
        if self.warnings:
            lines.extend([
                "╠══════════════════════════════════════════════════════════╣",
                "║  ⚠️ WARNINGS",
            ])
            for w in self.warnings[:5]:
                lines.append(f"║    • {w}")

        # Recommendations
        if self.recommendations:
            lines.extend([
                "╠══════════════════════════════════════════════════════════╣",
                "║  💡 RECOMMENDATIONS",
            ])
            for r in self.recommendations[:3]:
                lines.append(f"║    • {r}")

        lines.append("╚══════════════════════════════════════════════════════════╝")
        report = "\n".join(lines)
        print(report)
        return report


@dataclass
class SecurityConfig:
    """Configuration for security analysis."""
    rpc_url: str = ""
    chain: str = "ethereum"
    # API keys
    etherscan_api_key: str = ""
    goplus_api_key: str = ""
    # Thresholds
    max_buy_tax: float = 10.0
    max_sell_tax: float = 10.0
    min_liquidity_usd: float = 10000.0
    min_locked_percent: float = 50.0
    max_top10_percent: float = 50.0
    # Proxy
    proxy: Optional[str] = None


class TokenAnalyzer:
    """Analyze tokens for security risks.

    Performs comprehensive security analysis including honeypot detection,
    rug pull assessment, contract audit, and safety scoring.

    Example::

        analyzer = TokenAnalyzer(SecurityConfig(
            rpc_url="https://eth.llamarpc.com",
        ))
        report = analyzer.analyze_token("0x...")
        if report.is_honeypot:
            print("⚠️ HONEYPOT DETECTED!")
        elif report.safety_score < 50:
            print("⚠️ HIGH RISK TOKEN")
        else:
            print(f"✓ Safety Score: {report.safety_score}/100")
    """

    # Known DEX routers
    DEX_ROUTERS = {
        "ethereum": {
            "uniswap_v2": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
            "uniswap_v3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
            "sushiswap": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
        },
        "base": {
            "uniswap_v3": "0x2626664c2603336E57B271c5C0b26F421741e481",
            "aerodrome": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
        },
        "arbitrum": {
            "uniswap_v3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
            "sushiswap": "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
        },
    }

    # Known honeypot patterns
    HONEYPOT_SELECTORS = [
        "0xa9059cbb",  # transfer
        "0x23b872dd",  # transferFrom
        "0x095ea7b3",  # approve
    ]

    # ERC20 ABI (minimal)
    ERC20_ABI = [
        {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "owner", "outputs": [{"name": "", "type": "address"}], "type": "function"},
    ]

    def __init__(self, config: Optional[SecurityConfig] = None):
        """Initialize token analyzer.

        Args:
            config: Security configuration.
        """
        self.config = config or SecurityConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "web3-agent-kit/1.1.0",
        })
        if self.config.proxy:
            self.session.proxies = {
                "http": self.config.proxy,
                "https": self.config.proxy,
            }
        self._web3 = None
        if self.config.rpc_url:
            self._init_web3()
        logger.info("TokenAnalyzer initialized")

    def _init_web3(self) -> None:
        """Initialize Web3 connection."""
        try:
            from web3 import Web3
            self._web3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
            if self._web3.is_connected():
                logger.info(f"Connected to {self.config.rpc_url}")
        except ImportError:
            logger.warning("web3 not installed")
        except Exception as e:
            logger.error(f"Web3 init failed: {e}")

    def analyze_token(self, address: str) -> SecurityReport:
        """Perform full security analysis on a token.

        Args:
            address: Token contract address.

        Returns:
            SecurityReport with all analysis results.
        """
        logger.info(f"Analyzing token: {address}")

        # Gather all info
        token_info = self._get_token_info(address)
        tax_info = self._check_tax(address)
        liquidity_info = self._check_liquidity(address)
        holder_info = self._check_holders(address)
        contract_audit = self._audit_contract(address)

        # Calculate safety score
        safety_score = self._calculate_safety_score(
            token_info, tax_info, liquidity_info, holder_info, contract_audit
        )

        # Determine risk level
        risk_level = self._determine_risk_level(safety_score)

        # Generate warnings
        warnings = self._generate_warnings(
            token_info, tax_info, liquidity_info, holder_info, contract_audit
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            safety_score, tax_info, liquidity_info, contract_audit
        )

        report = SecurityReport(
            token=token_info,
            tax=tax_info,
            liquidity=liquidity_info,
            holders=holder_info,
            contract=contract_audit,
            safety_score=safety_score,
            risk_level=risk_level,
            warnings=warnings,
            recommendations=recommendations,
        )

        logger.info(
            f"Analysis complete: {token_info.symbol} — "
            f"Score: {safety_score}/100, Risk: {risk_level.value}"
        )
        return report

    def quick_check(self, address: str) -> dict:
        """Quick security check (API-only, no on-chain calls).

        Args:
            address: Token contract address.

        Returns:
            Quick check results dict.
        """
        result = {
            "address": address,
            "is_honeypot": False,
            "buy_tax": 0.0,
            "sell_tax": 0.0,
            "risk_level": "unknown",
        }

        try:
            # Use GoPlus API for quick check
            resp = self.session.get(
                f"https://api.gopluslabs.io/api/v1/token_security/{self._chain_id()}",
                params={"contract_addresses": address},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                token_data = data.get("result", {}).get(address.lower(), {})
                if token_data:
                    result["is_honeypot"] = token_data.get("is_honeypot") == "1"
                    result["buy_tax"] = float(token_data.get("buy_tax", "0"))
                    result["sell_tax"] = float(token_data.get("sell_tax", "0"))
                    result["risk_level"] = "high" if result["is_honeypot"] else "low"
        except Exception as e:
            logger.error(f"Quick check failed: {e}")

        return result

    def check_honeypot(self, address: str) -> TaxInfo:
        """Check if token is a honeypot.

        Args:
            address: Token contract address.

        Returns:
            TaxInfo with honeypot status.
        """
        return self._check_tax(address)

    def check_rug_risk(self, address: str) -> dict:
        """Check rug pull risk.

        Args:
            address: Token contract address.

        Returns:
            Rug risk assessment dict.
        """
        liquidity = self._check_liquidity(address)
        holders = self._check_holders(address)
        contract = self._audit_contract(address)

        risk_factors = []
        risk_score = 0

        if liquidity.locked_percent < 50:
            risk_factors.append("Low locked liquidity")
            risk_score += 30

        if holders.is_risky_concentration:
            risk_factors.append("Concentrated holdings")
            risk_score += 25

        if contract.has_hidden_mint:
            risk_factors.append("Hidden mint function")
            risk_score += 40

        if contract.is_proxy:
            risk_factors.append("Proxy contract (upgradeable)")
            risk_score += 15

        if not contract.is_ownership_renounced and contract.has_ownership:
            risk_factors.append("Ownership not renounced")
            risk_score += 10

        return {
            "address": address,
            "risk_score": min(100, risk_score),
            "risk_factors": risk_factors,
            "is_rug_risk": risk_score >= 50,
        }

    # ─── Internal Methods ─────────────────────────────────────────

    def _get_token_info(self, address: str) -> TokenInfo:
        """Get basic token information."""
        info = TokenInfo(address=address, chain=self.config.chain)

        if not self._web3:
            return info

        try:
            from web3 import Web3
            contract = self._web3.eth.contract(
                address=Web3.to_checksum_address(address),
                abi=self.ERC20_ABI,
            )

            info.name = contract.functions.name().call()
            info.symbol = contract.functions.symbol().call()
            info.decimals = contract.functions.decimals().call()
            info.total_supply = contract.functions.totalSupply().call() / (10 ** info.decimals)

            try:
                info.owner = contract.functions.owner().call()
                info.is_verified = True
            except Exception:
                info.owner = ""

        except Exception as e:
            logger.error(f"Failed to get token info: {e}")

        return info

    def _check_tax(self, address: str) -> TaxInfo:
        """Check token tax and honeypot status."""
        tax = TaxInfo()

        try:
            # Try GoPlus API
            resp = self.session.get(
                f"https://api.gopluslabs.io/api/v1/token_security/{self._chain_id()}",
                params={"contract_addresses": address},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                token_data = data.get("result", {}).get(address.lower(), {})
                if token_data:
                    tax.buy_tax = float(token_data.get("buy_tax", "0")) * 100
                    tax.sell_tax = float(token_data.get("sell_tax", "0")) * 100
                    tax.is_honeypot = token_data.get("is_honeypot") == "1"
                    tax.can_sell = not tax.is_honeypot
        except Exception as e:
            logger.error(f"Tax check failed: {e}")

        return tax

    def _check_liquidity(self, address: str) -> LiquidityInfo:
        """Check token liquidity."""
        liquidity = LiquidityInfo()

        try:
            # Try DexScreener API
            resp = self.session.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{address}",
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                pairs = data.get("pairs", [])
                if pairs:
                    pair = pairs[0]
                    liquidity.total_liquidity_usd = float(pair.get("liquidity", {}).get("usd", 0))
                    liquidity.dex = pair.get("dexId", "")
                    liquidity.pair_address = pair.get("pairAddress", "")
        except Exception as e:
            logger.error(f"Liquidity check failed: {e}")

        return liquidity

    def _check_holders(self, address: str) -> HolderInfo:
        """Check token holder distribution."""
        holders = HolderInfo()

        try:
            # Try GoPlus API for holder info
            resp = self.session.get(
                f"https://api.gopluslabs.io/api/v1/token_security/{self._chain_id()}",
                params={"contract_addresses": address},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                token_data = data.get("result", {}).get(address.lower(), {})
                if token_data:
                    holders.total_holders = int(token_data.get("holder_count", 0))
                    # Top holder percentage from GoPlus
                    top_holders = token_data.get("holders", [])
                    if top_holders:
                        top10 = sorted(
                            top_holders,
                            key=lambda x: float(x.get("percent", "0")),
                            reverse=True,
                        )[:10]
                        holders.top10_percent = sum(
                            float(h.get("percent", "0")) * 100 for h in top10
                        )
                        holders.is_concentrated = holders.top10_percent > 50
        except Exception as e:
            logger.error(f"Holders check failed: {e}")

        return holders

    def _audit_contract(self, address: str) -> ContractAudit:
        """Audit smart contract for dangerous patterns."""
        audit = ContractAudit()

        try:
            # Try GoPlus API for contract info
            resp = self.session.get(
                f"https://api.gopluslabs.io/api/v1/token_security/{self._chain_id()}",
                params={"contract_addresses": address},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                token_data = data.get("result", {}).get(address.lower(), {})
                if token_data:
                    audit.is_verified = token_data.get("is_open_source") == "1"
                    audit.is_proxy = token_data.get("is_proxy") == "1"
                    audit.has_hidden_mint = token_data.get("hidden_owner") == "1"
                    audit.has_blacklist = token_data.get("is_blacklisted") == "1"
                    audit.has_pause = token_data.get("can_take_back_ownership") == "1"
                    audit.has_ownership = token_data.get("owner_change_balance") == "1"
                    audit.is_ownership_renounced = token_data.get("owner_can_not_set_fee") == "1"
                    audit.has_fee_change = token_data.get("can_set_fee") == "1"
                    audit.has_cooldown = token_data.get("trading_cooldown") == "1"

                    # Build detected patterns
                    if audit.has_hidden_mint:
                        audit.detected_patterns.append(ContractPattern.HIDDEN_MINT)
                    if audit.has_blacklist:
                        audit.detected_patterns.append(ContractPattern.BLACKLIST)
                    if audit.has_pause:
                        audit.detected_patterns.append(ContractPattern.PAUSE)
                    if audit.is_proxy:
                        audit.detected_patterns.append(ContractPattern.PROXY)

        except Exception as e:
            logger.error(f"Contract audit failed: {e}")

        return audit

    def _calculate_safety_score(
        self,
        token: TokenInfo,
        tax: TaxInfo,
        liquidity: LiquidityInfo,
        holders: HolderInfo,
        contract: ContractAudit,
    ) -> int:
        """Calculate overall safety score (0-100)."""
        score = 100

        # Tax deductions
        if tax.is_honeypot:
            return 0
        if tax.buy_tax > 10:
            score -= 20
        if tax.sell_tax > 10:
            score -= 20
        if tax.buy_tax > 50 or tax.sell_tax > 50:
            score -= 30

        # Liquidity deductions
        if liquidity.is_low_liquidity:
            score -= 20
        if not liquidity.is_locked:
            score -= 15

        # Holder deductions
        if holders.is_risky_concentration:
            score -= 20

        # Contract deductions
        if not contract.is_verified:
            score -= 25
        if contract.has_hidden_mint:
            score -= 30
        if contract.has_blacklist:
            score -= 15
        if contract.has_pause:
            score -= 10
        if contract.is_proxy:
            score -= 10

        return max(0, min(100, score))

    def _determine_risk_level(self, safety_score: int) -> RiskLevel:
        """Determine risk level from safety score."""
        if safety_score >= 80:
            return RiskLevel.SAFE
        elif safety_score >= 60:
            return RiskLevel.LOW
        elif safety_score >= 40:
            return RiskLevel.MEDIUM
        elif safety_score >= 20:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    def _generate_warnings(
        self,
        token: TokenInfo,
        tax: TaxInfo,
        liquidity: LiquidityInfo,
        holders: HolderInfo,
        contract: ContractAudit,
    ) -> list[str]:
        """Generate security warnings."""
        warnings = []

        if tax.is_honeypot:
            warnings.append("🚨 HONEYPOT: Cannot sell tokens!")
        if tax.is_high_tax:
            warnings.append(f"⚠️ High tax: Buy {tax.buy_tax}%, Sell {tax.sell_tax}%")
        if liquidity.is_low_liquidity:
            warnings.append(f"⚠️ Low liquidity: ${liquidity.total_liquidity_usd:,.0f}")
        if not liquidity.is_locked:
            warnings.append("⚠️ Liquidity not locked")
        if holders.is_risky_concentration:
            warnings.append(f"⚠️ Top 10 holders own {holders.top10_percent:.1f}%")
        if contract.has_hidden_mint:
            warnings.append("🚨 Hidden mint function detected")
        if contract.has_blacklist:
            warnings.append("⚠️ Blacklist function detected")
        if contract.is_proxy:
            warnings.append("⚠️ Proxy contract (can be upgraded)")
        if not contract.is_verified:
            warnings.append("⚠️ Contract source not verified")

        return warnings

    def _generate_recommendations(
        self,
        safety_score: int,
        tax: TaxInfo,
        liquidity: LiquidityInfo,
        contract: ContractAudit,
    ) -> list[str]:
        """Generate security recommendations."""
        recs = []

        if safety_score < 30:
            recs.append("❌ DO NOT BUY — extremely high risk")
        elif safety_score < 50:
            recs.append("⚠️ High risk — only invest what you can afford to lose")
        elif safety_score < 70:
            recs.append("⚠️ Medium risk — proceed with caution")

        if tax.buy_tax > 5:
            recs.append(f"💡 Buy tax is {tax.buy_tax}% — factor into profit calculations")
        if not liquidity.is_locked:
            recs.append("💡 Check if liquidity is locked on Unicrypt/Team.Finance")
        if contract.is_proxy:
            recs.append("💡 Review proxy implementation for upgrade risks")

        return recs

    def _chain_id(self) -> str:
        """Get chain ID for API calls."""
        chain_ids = {
            "ethereum": "1",
            "base": "8453",
            "arbitrum": "42161",
            "optimism": "10",
            "polygon": "137",
            "bnb": "56",
            "avalanche": "43114",
        }
        return chain_ids.get(self.config.chain, "1")
