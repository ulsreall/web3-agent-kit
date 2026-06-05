"""Bridge agent — cross-chain token transfers via bridge aggregators.

Supports Li.Fi, Socket, and direct bridge contracts.

Usage:
    from web3_agent_kit.bridge.bridge import BridgeAgent

    bridge = BridgeAgent(chain_manager, wallet)
    result = bridge.transfer(
        token="ETH",
        amount=0.1,
        from_chain=Chain.ETHEREUM,
        to_chain=Chain.BASE,
    )
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from ..wallet.wallet import Wallet
from ..chains.chain import Chain, ChainManager, CHAIN_IDS

logger = logging.getLogger(__name__)


# WETH addresses
WETH = {
    Chain.ETHEREUM: "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    Chain.BASE: "0x4200000000000000000000000000000000000006",
    Chain.ARBITRUM: "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    Chain.OPTIMISM: "0x4200000000000000000000000000000000000006",
    Chain.POLYGON: "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
}

# Native token address
NATIVE = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

# Chain IDs for Li.Fi
LIFI_CHAIN_IDS = {
    Chain.ETHEREUM: "eth",
    Chain.BASE: "base",
    Chain.ARBITRUM: "arb",
    Chain.OPTIMISM: "opt",
    Chain.POLYGON: "pol",
    Chain.AVALANCHE: "ava",
    Chain.BSC: "bsc",
}

# Chain IDs for Socket
SOCKET_CHAIN_IDS = {
    Chain.ETHEREUM: 1,
    Chain.BASE: 8453,
    Chain.ARBITRUM: 42161,
    Chain.OPTIMISM: 10,
    Chain.POLYGON: 137,
    Chain.AVALANCHE: 43114,
    Chain.BSC: 56,
}


@dataclass
class BridgeRoute:
    """A bridge route with quote details."""

    bridge_name: str
    from_chain: Chain
    to_chain: Chain
    token_in: str
    token_out: str
    amount_in: float
    amount_out: float
    gas_estimate: float
    time_estimate: int  # seconds
    fee_usd: float
    steps: list[dict]

    def to_dict(self) -> dict:
        return {
            "bridge": self.bridge_name,
            "from": self.from_chain.value,
            "to": self.to_chain.value,
            "amount_in": self.amount_in,
            "amount_out": self.amount_out,
            "gas_estimate": self.gas_estimate,
            "time_minutes": self.time_estimate // 60,
            "fee_usd": self.fee_usd,
        }


@dataclass
class BridgeResult:
    """Result of a bridge transfer."""

    tx_hash: str
    from_chain: Chain
    to_chain: Chain
    token: str
    amount: float
    bridge_name: str
    estimated_arrival: int  # seconds

    def to_dict(self) -> dict:
        return {
            "tx_hash": self.tx_hash,
            "from": self.from_chain.value,
            "to": self.to_chain.value,
            "token": self.token,
            "amount": self.amount,
            "bridge": self.bridge_name,
            "eta_minutes": self.estimated_arrival // 60,
        }


class BridgeAgent:
    """
    Cross-chain bridge agent — find best routes and execute transfers.

    Supports:
    - Li.Fi (aggregator)
    - Socket (aggregator)
    - Direct bridge contracts

    Example:
        bridge = BridgeAgent(chain_manager, wallet)

        # Get best route
        routes = bridge.get_routes("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)
        best = routes[0]
        print(f"Best route: {best.bridge_name} — {best.amount_out:.6f} ETH")

        # Execute transfer
        result = bridge.transfer("ETH", 0.1, Chain.ETHEREUM, Chain.BASE)
        print(f"TX: {result.tx_hash}")
    """

    def __init__(
        self,
        chain_manager: ChainManager,
        wallet: Wallet,
        lifi_api_key: Optional[str] = None,
    ):
        self.chain_manager = chain_manager
        self.wallet = wallet
        self.lifi_api_key = lifi_api_key
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "web3-agent-kit/0.2.0",
        })

    def get_routes(
        self,
        token: str,
        amount: float,
        from_chain: Chain,
        to_chain: Chain,
    ) -> list[BridgeRoute]:
        """
        Get available bridge routes with quotes.

        Args:
            token: Token symbol or address ("ETH", "USDC", etc.)
            amount: Amount to bridge
            from_chain: Source chain
            to_chain: Destination chain

        Returns:
            List of BridgeRoute sorted by amount_out (best first)
        """
        routes = []

        # Try Li.Fi
        try:
            lifi_routes = self._get_lifi_routes(token, amount, from_chain, to_chain)
            routes.extend(lifi_routes)
        except Exception as e:
            logger.warning(f"Li.Fi failed: {e}")

        # Try Socket
        try:
            socket_routes = self._get_socket_routes(token, amount, from_chain, to_chain)
            routes.extend(socket_routes)
        except Exception as e:
            logger.warning(f"Socket failed: {e}")

        # Sort by amount_out (best first)
        routes.sort(key=lambda r: r.amount_out, reverse=True)

        return routes

    def _get_lifi_routes(
        self, token: str, amount: float, from_chain: Chain, to_chain: Chain
    ) -> list[BridgeRoute]:
        """Get routes from Li.Fi API."""
        from_chain_id = LIFI_CHAIN_IDS.get(from_chain)
        to_chain_id = LIFI_CHAIN_IDS.get(to_chain)

        if not from_chain_id or not to_chain_id:
            return []

        # Resolve token address
        token_addr = self._resolve_token(token, from_chain)
        to_token_addr = self._resolve_token(token, to_chain)

        # Get decimals
        decimals = self._get_decimals(token_addr, from_chain)
        amount_wei = str(int(amount * (10 ** decimals)))

        url = "https://li.quest/v1/quote"
        params = {
            "fromChain": from_chain_id,
            "toChain": to_chain_id,
            "fromToken": token_addr,
            "toToken": to_token_addr,
            "fromAmount": amount_wei,
            "fromAddress": self.wallet.address,
        }

        if self.lifi_api_key:
            self.session.headers["x-lifi-api-key"] = self.lifi_api_key

        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        routes = []
        if "routes" in data:
            for route in data["routes"][:3]:  # Top 3 routes
                to_amount = int(route.get("toAmount", "0"))
                to_decimals = self._get_decimals(to_token_addr, to_chain)
                amount_out = to_amount / (10 ** to_decimals)

                routes.append(BridgeRoute(
                    bridge_name=route.get("tags", ["unknown"])[0] if route.get("tags") else "Li.Fi",
                    from_chain=from_chain,
                    to_chain=to_chain,
                    token_in=token_addr,
                    token_out=to_token_addr,
                    amount_in=amount,
                    amount_out=amount_out,
                    gas_estimate=float(route.get("gasCostUSD", "0")),
                    time_estimate=int(route.get("duration", 300)),
                    fee_usd=float(route.get("gasCostUSD", "0")),
                    steps=route.get("steps", []),
                ))

        return routes

    def _get_socket_routes(
        self, token: str, amount: float, from_chain: Chain, to_chain: Chain
    ) -> list[BridgeRoute]:
        """Get routes from Socket API."""
        from_chain_id = SOCKET_CHAIN_IDS.get(from_chain)
        to_chain_id = SOCKET_CHAIN_IDS.get(to_chain)

        if not from_chain_id or not to_chain_id:
            return []

        token_addr = self._resolve_token(token, from_chain)
        to_token_addr = self._resolve_token(token, to_chain)

        decimals = self._get_decimals(token_addr, from_chain)
        amount_wei = str(int(amount * (10 ** decimals)))

        url = "https://api.socket.tech/v2/quote"
        params = {
            "fromChainId": from_chain_id,
            "toChainId": to_chain_id,
            "fromTokenAddress": token_addr,
            "toTokenAddress": to_token_addr,
            "fromAmount": amount_wei,
            "userAddress": self.wallet.address,
            "sort": "output",
            "singleTxOnly": "true",
        }
        headers = {
            "API-KEY": "demo",  # Free tier
        }

        resp = self.session.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        routes = []
        result = data.get("result", {})
        routes_data = result.get("routes", [])

        for route in routes_data[:3]:
            to_amount = int(route.get("toAmount", "0"))
            to_decimals = self._get_decimals(to_token_addr, to_chain)
            amount_out = to_amount / (10 ** to_decimals)

            bridge_name = route.get("bridgeName", "Socket")
            gas_usd = float(route.get("gasFees", {}).get("gasAmountUSD", "0"))

            routes.append(BridgeRoute(
                bridge_name=bridge_name,
                from_chain=from_chain,
                to_chain=to_chain,
                token_in=token_addr,
                token_out=to_token_addr,
                amount_in=amount,
                amount_out=amount_out,
                gas_estimate=gas_usd,
                time_estimate=int(route.get("serviceTime", 300)),
                fee_usd=gas_usd,
                steps=[],
            ))

        return routes

    def transfer(
        self,
        token: str,
        amount: float,
        from_chain: Chain,
        to_chain: Chain,
        route: Optional[BridgeRoute] = None,
    ) -> BridgeResult:
        """
        Execute a cross-chain transfer.

        Args:
            token: Token symbol or address
            amount: Amount to bridge
            from_chain: Source chain
            to_chain: Destination chain
            route: Specific route to use (optional — uses best route if None)

        Returns:
            BridgeResult with transaction hash
        """
        if route is None:
            routes = self.get_routes(token, amount, from_chain, to_chain)
            if not routes:
                raise ValueError("No bridge routes found")
            route = routes[0]
            logger.info(f"Using best route: {route.bridge_name} ({route.amount_out:.6f} {token})")

        # Execute based on bridge type
        if route.bridge_name in ("lifuel", "Li.Fi", "li.fi"):
            return self._execute_lifi(route)
        else:
            return self._execute_socket(route)

    def _execute_lifi(self, route: BridgeRoute) -> BridgeResult:
        """Execute a Li.Fi bridge transfer."""
        # Get transaction data from Li.Fi
        from_chain_id = LIFI_CHAIN_IDS.get(route.from_chain)
        to_chain_id = LIFI_CHAIN_IDS.get(route.to_chain)

        decimals = self._get_decimals(route.token_in, route.from_chain)
        amount_wei = str(int(route.amount_in * (10 ** decimals)))

        url = "https://li.quest/v1/quote"
        params = {
            "fromChain": from_chain_id,
            "toChain": to_chain_id,
            "fromToken": route.token_in,
            "toToken": route.token_out,
            "fromAmount": amount_wei,
            "fromAddress": self.wallet.address,
        }

        if self.lifi_api_key:
            self.session.headers["x-lifi-api-key"] = self.lifi_api_key

        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Get the transaction request
        tx_request = data.get("transactionRequest")
        if not tx_request:
            raise ValueError("No transaction data from Li.Fi")

        # Build and send transaction
        w3 = self.chain_manager.get_web3(route.from_chain)

        tx = {
            "from": w3.to_checksum_address(self.wallet.address),
            "to": w3.to_checksum_address(tx_request["to"]),
            "data": tx_request["data"],
            "value": int(tx_request.get("value", "0")),
            "gas": int(tx_request.get("gasLimit", "300000")),
            "gasPrice": w3.eth.gas_price,
            "nonce": w3.eth.get_transaction_count(self.wallet.address),
            "chainId": CHAIN_IDS.get(route.from_chain, 1),
        }

        signed = self.wallet.sign_transaction(tx, route.from_chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        return BridgeResult(
            tx_hash=tx_hash.hex(),
            from_chain=route.from_chain,
            to_chain=route.to_chain,
            token=route.token_in,
            amount=route.amount_in,
            bridge_name=route.bridge_name,
            estimated_arrival=route.time_estimate,
        )

    def _execute_socket(self, route: BridgeRoute) -> BridgeResult:
        """Execute a Socket bridge transfer."""
        from_chain_id = SOCKET_CHAIN_IDS.get(route.from_chain)
        to_chain_id = SOCKET_CHAIN_IDS.get(route.to_chain)

        decimals = self._get_decimals(route.token_in, route.from_chain)
        amount_wei = str(int(route.amount_in * (10 ** decimals)))

        # Get transaction data
        url = "https://api.socket.tech/v2/build-tx"
        params = {
            "fromChainId": from_chain_id,
            "toChainId": to_chain_id,
            "fromTokenAddress": route.token_in,
            "toTokenAddress": route.token_out,
            "fromAmount": amount_wei,
            "userAddress": self.wallet.address,
            "route": json.dumps(route.steps) if route.steps else "",
        }
        headers = {"API-KEY": "demo"}

        resp = self.session.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        tx_data = data.get("result", {}).get("txData", {})
        if not tx_data:
            raise ValueError("No transaction data from Socket")

        w3 = self.chain_manager.get_web3(route.from_chain)

        tx = {
            "from": w3.to_checksum_address(self.wallet.address),
            "to": w3.to_checksum_address(tx_data["to"]),
            "data": tx_data["data"],
            "value": int(tx_data.get("value", "0")),
            "gas": int(tx_data.get("gasLimit", "300000")),
            "gasPrice": w3.eth.gas_price,
            "nonce": w3.eth.get_transaction_count(self.wallet.address),
            "chainId": CHAIN_IDS.get(route.from_chain, 1),
        }

        signed = self.wallet.sign_transaction(tx, route.from_chain)
        tx_hash = w3.eth.send_raw_transaction(signed)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        return BridgeResult(
            tx_hash=tx_hash.hex(),
            from_chain=route.from_chain,
            to_chain=route.to_chain,
            token=route.token_in,
            amount=route.amount_in,
            bridge_name=route.bridge_name,
            estimated_arrival=route.time_estimate,
        )

    def _resolve_token(self, token: str, chain: Chain) -> str:
        """Resolve token symbol to address."""
        token = token.upper()
        if token in ("ETH", "NATIVE", "MATIC"):
            return NATIVE
        if chain in WETH and token == "WETH":
            return WETH[chain]
        # Check known tokens
        from ..portfolio.tracker import KNOWN_TOKENS
        chain_tokens = KNOWN_TOKENS.get(chain, {})
        if token in chain_tokens:
            return chain_tokens[token]
        # Assume it's an address
        return token

    def _get_decimals(self, token_address: str, chain: Chain) -> int:
        """Get token decimals."""
        if token_address == NATIVE:
            return 18

        w3 = self.chain_manager.get_web3(chain)
        try:
            token = w3.eth.contract(
                address=w3.to_checksum_address(token_address),
                abi=[{
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
                    "stateMutability": "view",
                    "type": "function"
                }],
            )
            return token.functions.decimals().call()
        except Exception:
            return 18  # Default to 18

    def __repr__(self) -> str:
        return f"BridgeAgent(wallet={self.wallet.address[:10]}...)"
