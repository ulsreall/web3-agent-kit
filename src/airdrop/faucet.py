"""Faucet Claimer — auto-claim testnet tokens from faucets.

Automates claiming testnet tokens from various blockchain faucets
for testnet airdrop farming and development.

Usage::

    from web3_agent_kit.airdrop.faucet import FaucetClaimer

    claimer = FaucetClaimer()
    results = claimer.claim_all(wallet="0x...", chain="base_sepolia")
    claimer.print_results()
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class FaucetConfig:
    """Configuration for a faucet."""
    name: str
    chain: str
    url: str
    api_url: str = ""
    token: str = "ETH"
    amount: str = "0.1"
    cooldown_hours: int = 24
    requires_captcha: bool = False
    requires_social: bool = False
    captcha_site_key: str = ""
    headers: dict = field(default_factory=dict)
    method: str = "POST"
    body_template: dict = field(default_factory=dict)
    success_indicator: str = "success"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "chain": self.chain,
            "url": self.url,
            "token": self.token,
            "amount": self.amount,
            "cooldown_hours": self.cooldown_hours,
            "requires_captcha": self.requires_captcha,
        }


@dataclass
class ClaimResult:
    """Result of a faucet claim attempt."""
    faucet: str
    chain: str
    token: str
    success: bool = False
    tx_hash: str = ""
    amount: str = ""
    error: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "faucet": self.faucet,
            "chain": self.chain,
            "token": self.token,
            "success": self.success,
            "tx_hash": self.tx_hash,
            "amount": self.amount,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


# Known testnet faucets (as of 2025-2026)
FAUCETS: dict[str, FaucetConfig] = {
    # Ethereum Testnets
    "ethereum_sepolia": FaucetConfig(
        name="Alchemy Sepolia Faucet",
        chain="ethereum_sepolia",
        url="https://sepoliafaucet.com",
        api_url="https://faucet-api.alchemy.com/api/sendGasToken",
        token="ETH",
        amount="0.1",
        cooldown_hours=24,
        requires_captcha=True,
        captcha_site_key="6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI",
    ),
    "ethereum_holesky": FaucetConfig(
        name="Holesky PoW Faucet",
        chain="ethereum_holesky",
        url="https://holesky-faucet.pk910.de",
        api_url="https://holesky-faucet.pk910.de/api/claim",
        token="ETH",
        amount="0.1",
        cooldown_hours=24,
    ),
    # L2 Testnets
    "base_sepolia": FaucetConfig(
        name="QuickNode Base Sepolia",
        chain="base_sepolia",
        url="https://faucet.quicknode.com/base/sepolia",
        api_url="https://faucet.quicknode.com/api/claim",
        token="ETH",
        amount="0.1",
        cooldown_hours=24,
    ),
    "arbitrum_sepolia": FaucetConfig(
        name="QuickNode Arbitrum Sepolia",
        chain="arbitrum_sepolia",
        url="https://faucet.quicknode.com/arbitrum/sepolia",
        api_url="https://faucet.quicknode.com/api/claim",
        token="ETH",
        amount="0.1",
        cooldown_hours=24,
    ),
    "optimism_sepolia": FaucetConfig(
        name="QuickNode Optimism Sepolia",
        chain="optimism_sepolia",
        url="https://faucet.quicknode.com/optimism/sepolia",
        api_url="https://faucet.quicknode.com/api/claim",
        token="ETH",
        amount="0.1",
        cooldown_hours=24,
    ),
    "scroll_sepolia": FaucetConfig(
        name="Scroll Sepolia Faucet",
        chain="scroll_sepolia",
        url="https://scroll.io/faucet",
        api_url="https://scroll.io/api/faucet/claim",
        token="ETH",
        amount="0.1",
        cooldown_hours=24,
    ),
    "linea_sepolia": FaucetConfig(
        name="Linea Sepolia Faucet",
        chain="linea_sepolia",
        url="https://faucet.linea.build",
        api_url="https://faucet.linea.build/api/claim",
        token="ETH",
        amount="0.1",
        cooldown_hours=24,
    ),
    "zksync_sepolia": FaucetConfig(
        name="zkSync Sepolia Portal",
        chain="zksync_sepolia",
        url="https://portal.zksync.io/faucet",
        api_url="https://portal.zksync.io/api/faucet",
        token="ETH",
        amount="0.1",
        cooldown_hours=24,
    ),
    # Other Chains
    "polygon_amoy": FaucetConfig(
        name="Polygon Amoy Faucet",
        chain="polygon_amoy",
        url="https://faucet.polygon.technology",
        api_url="https://faucet.polygon.technology/api/claim",
        token="POL",
        amount="0.5",
        cooldown_hours=24,
    ),
    "avalanche_fuji": FaucetConfig(
        name="Avalanche Fuji Faucet",
        chain="avalanche_fuji",
        url="https://faucet.avax.network",
        api_url="https://faucet.avax.network/api/claim",
        token="AVAX",
        amount="2.0",
        cooldown_hours=24,
    ),
    "bnb_testnet": FaucetConfig(
        name="BNB Testnet Faucet",
        chain="bnb_testnet",
        url="https://testnet.bnbchain.org/faucet-smart",
        api_url="https://testnet.bnbchain.org/api/faucet",
        token="tBNB",
        amount="0.1",
        cooldown_hours=24,
    ),
    "monad_testnet": FaucetConfig(
        name="Monad Testnet Faucet",
        chain="monad_testnet",
        url="https://faucet.monad.xyz",
        api_url="https://faucet.monad.xyz/api/claim",
        token="MONAD",
        amount="1.0",
        cooldown_hours=24,
    ),
}


class FaucetClaimer:
    """Auto-claim testnet tokens from faucets.

    Manages multiple faucet configurations and automates claiming
    testnet tokens for various chains. Supports CAPTCHA solving
    integration and cooldown tracking.

    Example::

        claimer = FaucetClaimer()

        # Claim from all faucets
        results = claimer.claim_all(wallet="0x...")

        # Claim from specific chain
        results = claimer.claim_chain("base_sepolia", wallet="0x...")

        claimer.print_results()
    """

    def __init__(
        self,
        captcha_api_key: Optional[str] = None,
        proxy: Optional[str] = None,
    ):
        """Initialize faucet claimer.

        Args:
            captcha_api_key: API key for CAPTCHA solving.
            proxy: HTTP proxy URL.
        """
        self._captcha_api_key = captcha_api_key
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        if proxy:
            self._session.proxies = {"http": proxy, "https": proxy}
        self._faucets: dict[str, FaucetConfig] = FAUCETS.copy()
        self._results: list[ClaimResult] = []
        self._cooldowns: dict[str, datetime] = {}
        self._load_cooldowns()
        logger.info(f"FaucetClaimer initialized: {len(self._faucets)} faucets")

    def add_faucet(self, key: str, config: FaucetConfig) -> None:
        """Add a custom faucet configuration.

        Args:
            key: Unique faucet key.
            config: Faucet configuration.
        """
        self._faucets[key] = config
        logger.info(f"Added faucet: {key}")

    def claim_all(
        self,
        wallet: str,
        chains: Optional[list[str]] = None,
        skip_cooldown: bool = False,
    ) -> list[ClaimResult]:
        """Claim from all available faucets.

        Args:
            wallet: Wallet address to receive tokens.
            chains: Specific chains to claim (None = all).
            skip_cooldown: Skip cooldown checks.

        Returns:
            List of claim results.
        """
        self._results = []
        faucets = (
            {k: v for k, v in self._faucets.items() if k in chains}
            if chains
            else self._faucets
        )

        for key, faucet in faucets.items():
            # Check cooldown
            if not skip_cooldown and self._in_cooldown(key):
                logger.info(f"Skipping {key}: in cooldown")
                self._results.append(ClaimResult(
                    faucet=faucet.name,
                    chain=faucet.chain,
                    token=faucet.token,
                    success=False,
                    error="In cooldown",
                ))
                continue

            logger.info(f"Claiming from {faucet.name}...")
            result = self._claim_faucet(faucet, wallet)
            self._results.append(result)

            if result.success:
                self._set_cooldown(key, faucet.cooldown_hours)
                logger.info(f"✓ {faucet.name}: {result.amount} {result.token}")
            else:
                logger.warning(f"✗ {faucet.name}: {result.error}")

            time.sleep(2)  # TODO: convert to async  # Rate limiting

        return self._results

    async def async_claim_all(
        self,
        wallet: str,
        chains: Optional[list[str]] = None,
        skip_cooldown: bool = False,
    ) -> list[ClaimResult]:
        """Async version of claim_all — non-blocking sleep for rate limiting.

        Args:
            wallet: Wallet address to receive tokens.
            chains: Specific chains to claim (None = all).
            skip_cooldown: Skip cooldown checks.

        Returns:
            List of claim results.
        """
        self._results = []
        faucets = (
            {k: v for k, v in self._faucets.items() if k in chains}
            if chains
            else self._faucets
        )

        for key, faucet in faucets.items():
            if not skip_cooldown and self._in_cooldown(key):
                logger.info(f"Skipping {key}: in cooldown")
                self._results.append(ClaimResult(
                    faucet=faucet.name,
                    chain=faucet.chain,
                    token=faucet.token,
                    success=False,
                    error="In cooldown",
                ))
                continue

            logger.info(f"Claiming from {faucet.name}...")
            result = self._claim_faucet(faucet, wallet)
            self._results.append(result)

            if result.success:
                self._set_cooldown(key, faucet.cooldown_hours)
                logger.info(f"✓ {faucet.name}: {result.amount} {result.token}")
            else:
                logger.warning(f"✗ {faucet.name}: {result.error}")

            await asyncio.sleep(2)  # Rate limiting

        return self._results

    def claim_chain(
        self,
        chain: str,
        wallet: str,
        skip_cooldown: bool = False,
    ) -> list[ClaimResult]:
        """Claim from a specific chain's faucet.

        Args:
            chain: Chain key (e.g., 'base_sepolia').
            wallet: Wallet address.
            skip_cooldown: Skip cooldown checks.

        Returns:
            List of claim results.
        """
        faucet = self._faucets.get(chain)
        if not faucet:
            logger.error(f"Unknown chain: {chain}")
            return []

        if not skip_cooldown and self._in_cooldown(chain):
            return [ClaimResult(
                faucet=faucet.name,
                chain=faucet.chain,
                token=faucet.token,
                success=False,
                error="In cooldown",
            )]

        result = self._claim_faucet(faucet, wallet)
        if result.success:
            self._set_cooldown(chain, faucet.cooldown_hours)
        return [result]

    def get_available(self, wallet: str) -> list[FaucetConfig]:
        """Get faucets that are not in cooldown.

        Args:
            wallet: Wallet address.

        Returns:
            List of available faucet configs.
        """
        return [
            f for k, f in self._faucets.items()
            if not self._in_cooldown(k)
        ]

    def get_all_faucets(self) -> dict[str, FaucetConfig]:
        """Get all faucet configurations.

        Returns:
            Dict of faucet key to config.
        """
        return self._faucets.copy()

    def get_results(self) -> list[ClaimResult]:
        """Get claim results.

        Returns:
            List of claim results.
        """
        return self._results

    def print_results(self) -> str:
        """Print formatted claim results.

        Returns:
            Formatted results string.
        """
        if not self._results:
            return "No results yet. Call claim_all() first."

        lines = [
            "╔══════════════════════════════════════════════╗",
            "║          🚰 FAUCET CLAIM RESULTS             ║",
            "╠══════════════════════════════════════════════╣",
        ]

        success = sum(1 for r in self._results if r.success)
        failed = len(self._results) - success

        for result in self._results:
            status = "✓" if result.success else "✗"
            amount = f"{result.amount} {result.token}" if result.success else result.error
            lines.append(f"║  {status} {result.faucet:30} │ {amount}")

        lines.extend([
            "╠══════════════════════════════════════════════╣",
            f"║  Total: {len(self._results)} | Success: {success} | Failed: {failed}",
            "╚══════════════════════════════════════════════╝",
        ])

        summary = "\n".join(lines)
        logger.info(summary)
        return summary

    def export_json(self, path: Optional[str] = None) -> str:
        """Export results to JSON.

        Args:
            path: Optional file path to save.

        Returns:
            JSON string.
        """
        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "results": [r.to_dict() for r in self._results],
            "cooldowns": {
                k: v.isoformat() for k, v in self._cooldowns.items()
            },
        }
        json_str = json.dumps(data, indent=2, default=str)

        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json_str)
            logger.info(f"Exported results to {path}")

        return json_str

    # ─── Private Methods ─────────────────────────────────────────

    def _claim_faucet(
        self, faucet: FaucetConfig, wallet: str
    ) -> ClaimResult:
        """Claim tokens from a single faucet."""
        result = ClaimResult(
            faucet=faucet.name,
            chain=faucet.chain,
            token=faucet.token,
            amount=faucet.amount,
        )

        try:
            # Prepare request
            url = faucet.api_url or faucet.url
            headers = {**faucet.headers}
            body = {**faucet.body_template} if faucet.body_template else {}

            # Replace placeholders in body
            for key, value in body.items():
                if isinstance(value, str):
                    body[key] = value.replace("{wallet}", wallet)

            # If no template, use default
            if not body:
                body = {"address": wallet}

            # Handle CAPTCHA if needed
            if faucet.requires_captcha and self._captcha_api_key:
                captcha_token = self._solve_captcha(faucet)
                if captcha_token:
                    body["captcha"] = captcha_token
                else:
                    result.error = "CAPTCHA solving failed"
                    return result

            # Make request
            if faucet.method.upper() == "POST":
                resp = self._session.post(
                    url, json=body, headers=headers, timeout=30
                )
            else:
                resp = self._session.get(
                    url, params=body, headers=headers, timeout=30
                )

            # Check response
            if resp.status_code in (200, 201):
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                if isinstance(data, dict):
                    result.success = (
                        data.get("success", False)
                        or data.get("status", "") == "success"
                        or faucet.success_indicator in str(data)
                    )
                    result.tx_hash = data.get("txHash", data.get("tx_hash", ""))
                    result.amount = str(data.get("amount", faucet.amount))
                else:
                    result.success = True
            else:
                result.error = f"HTTP {resp.status_code}: {resp.text[:200]}"

        except requests.Timeout:
            result.error = "Request timeout"
        except requests.RequestException as e:
            result.error = str(e)[:200]
        except Exception as e:
            result.error = f"Unexpected: {str(e)[:200]}"

        return result

    def _solve_captcha(self, faucet: FaucetConfig) -> Optional[str]:
        """Solve CAPTCHA for a faucet."""
        if not self._captcha_api_key:
            return None

        try:
            # Use AntiCaptcha or similar service
            resp = self._session.post(
                "https://api.anti-captcha.com/createTask",
                json={
                    "clientKey": self._captcha_api_key,
                    "task": {
                        "type": "RecaptchaV2TaskProxyless",
                        "websiteURL": faucet.url,
                        "websiteKey": faucet.captcha_site_key,
                    },
                },
                timeout=30,
            )
            data = resp.json()
            task_id = data.get("taskId")

            if not task_id:
                return None

            # Poll for result
            for _ in range(30):
                time.sleep(5)  # TODO: convert to async
                result = self._session.post(
                    "https://api.anti-captcha.com/getTaskResult",
                    json={
                        "clientKey": self._captcha_api_key,
                        "taskId": task_id,
                    },
                    timeout=30,
                ).json()

                if result.get("status") == "ready":
                    return result.get("solution", {}).get("gRecaptchaResponse")

        except requests.RequestException as e:
            logger.error(f"CAPTCHA solving failed: {e}")

        return None

    async def _async_solve_captcha(self, faucet: FaucetConfig) -> Optional[str]:
        """Async version of _solve_captcha — non-blocking poll sleep."""
        if not self._captcha_api_key:
            return None

        try:
            resp = self._session.post(
                "https://api.anti-captcha.com/createTask",
                json={
                    "clientKey": self._captcha_api_key,
                    "task": {
                        "type": "RecaptchaV2TaskProxyless",
                        "websiteURL": faucet.url,
                        "websiteKey": faucet.captcha_site_key,
                    },
                },
                timeout=30,
            )
            data = resp.json()
            task_id = data.get("taskId")

            if not task_id:
                return None

            for _ in range(30):
                await asyncio.sleep(5)
                result = self._session.post(
                    "https://api.anti-captcha.com/getTaskResult",
                    json={
                        "clientKey": self._captcha_api_key,
                        "taskId": task_id,
                    },
                    timeout=30,
                ).json()

                if result.get("status") == "ready":
                    return result.get("solution", {}).get("gRecaptchaResponse")

        except requests.RequestException as e:
            logger.error(f"CAPTCHA solving failed: {e}")

        return None

    def _in_cooldown(self, key: str) -> bool:
        """Check if a faucet is in cooldown."""
        cooldown_end = self._cooldowns.get(key)
        if not cooldown_end:
            return False
        return datetime.now(timezone.utc) < cooldown_end

    def _set_cooldown(self, key: str, hours: int) -> None:
        """Set cooldown for a faucet."""
        self._cooldowns[key] = (
            datetime.now(timezone.utc) + timedelta(hours=hours)
        )
        self._save_cooldowns()

    def _load_cooldowns(self) -> None:
        """Load cooldowns from file."""
        path = Path("~/.hermes/cache/faucet_cooldowns.json").expanduser()
        if path.exists():
            try:
                data = json.loads(path.read_text())
                for k, v in data.items():
                    self._cooldowns[k] = datetime.fromisoformat(v)
                logger.info(f"Loaded {len(self._cooldowns)} cooldowns")
            except Exception as e:
                logger.debug(f"Failed to load cooldowns: {e}")

    def _save_cooldowns(self) -> None:
        """Save cooldowns to file."""
        path = Path("~/.hermes/cache/faucet_cooldowns.json").expanduser()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {k: v.isoformat() for k, v in self._cooldowns.items()}
            path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.debug(f"Failed to save cooldowns: {e}")
