"""Solana NFT — Metaplex read operations and NFT portfolio management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .client import SolanaClient, SolanaClientConfig


@dataclass
class SolanaNFTConfig:
    """Configuration for Solana NFT operations."""

    client_config: SolanaClientConfig = field(default_factory=SolanaClientConfig)
    helius_api_key: Optional[str] = None  # Helius RPC for DAS API (Digital Asset Standard)


class SolanaNFT:
    """Solana NFT operations using Metaplex DAS API (Helius/QuickNode).

    Usage:
        nft = SolanaNFT(SolanaNFTConfig(helius_api_key="your_key"))
        nfts = await nft.get_nfts_by_owner("WalletAddress")
        metadata = await nft.get_asset("AssetId")
    """

    def __init__(self, config: Optional[SolanaNFTConfig] = None):
        self.config = config or SolanaNFTConfig()
        self._client = SolanaClient(self.config.client_config)
        self._das_url = (
            f"https://mainnet.helius-rpc.com/?api-key={self.config.helius_api_key}"
            if self.config.helius_api_key
            else self.config.client_config.rpc_url
        )

    async def _das_rpc(self, method: str, params: dict) -> dict:
        """Make a DAS API RPC call."""
        import httpx

        payload = {
            "jsonrpc": "2.0",
            "id": "nft-1",
            "method": method,
            "params": params,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self._das_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", {})

    # ── Get NFTs by Owner ────────────────────────────

    async def get_nfts_by_owner(
        self,
        owner: str,
        limit: int = 100,
        page: int = 1,
    ) -> dict:
        """Get all NFTs owned by a wallet using DAS API.

        Returns:
            {
                "total": int,
                "limit": int,
                "page": int,
                "items": list[dict],
            }
        """
        return await self._das_rpc(
            "getAssetsByOwner",
            {
                "ownerAddress": owner,
                "limit": limit,
                "page": page,
                "displayOptions": {
                    "showFungible": False,
                    "showNativeBalance": False,
                    "showInscription": True,
                },
            },
        )

    async def get_all_nfts(self, owner: str) -> list[dict]:
        """Get ALL NFTs — paginates through all pages."""
        all_items = []
        page = 1
        while True:
            result = await self.get_nfts_by_owner(owner, limit=1000, page=page)
            items = result.get("items", [])
            if not items:
                break
            all_items.extend(items)
            if len(items) < 1000:
                break
            page += 1
        return all_items

    # ── Get Asset Details ────────────────────────────

    async def get_asset(self, asset_id: str) -> dict:
        """Get full metadata for a single NFT asset.

        Args:
            asset_id: The asset ID (mint address or token account)

        Returns:
            Full DAS asset metadata including name, symbol, image, attributes, etc.
        """
        return await self._das_rpc(
            "getAsset",
            {
                "id": asset_id,
            },
        )

    async def get_assets_batch(self, asset_ids: list[str]) -> dict:
        """Get metadata for multiple assets."""
        return await self._das_rpc(
            "getAssetBatch",
            {
                "ids": asset_ids,
            },
        )

    # ── Search NFTs ──────────────────────────────────

    async def search_assets(
        self,
        owner: str,
        grouping: Optional[tuple[str, str]] = None,
        sort_by: Optional[dict] = None,
        limit: int = 100,
        page: int = 1,
    ) -> dict:
        """Search assets with filtering.

        Args:
            owner: Wallet address
            grouping: (group_key, group_value) e.g., ("collection", "collection_address")
            sort_by: {"sortBy": "created", "sortDirection": "asc"}
        """
        params: dict[str, Any] = {
            "ownerAddress": owner,
            "limit": limit,
            "page": page,
            "displayOptions": {"showFungible": False},
        }
        if grouping:
            params["grouping"] = {"group_key": grouping[0], "group_value": grouping[1]}
        if sort_by:
            params["sortBy"] = sort_by

        return await self._das_rpc("searchAssets", params)

    # ── Collection Info ──────────────────────────────

    async def get_collections_by_owner(self, owner: str) -> list[dict]:
        """Get unique NFT collections owned by an address."""
        assets = await self.get_all_nfts(owner)
        collections = {}
        for asset in assets:
            grouping = asset.get("grouping", [])
            for g in grouping:
                if g.get("group_key") == "collection":
                    name = g.get("group_value", "Unknown")
                    if name not in collections:
                        collections[name] = {
                            "name": name,
                            "count": 0,
                            "first_asset": asset.get("id"),
                            "image": asset.get("content", {}).get("links", {}).get("image", ""),
                        }
                    collections[name]["count"] += 1

        return sorted(collections.values(), key=lambda x: x["count"], reverse=True)

    # ── NFT Portfolio Summary ────────────────────────

    async def get_portfolio_summary(self, owner: str) -> dict:
        """Get a quick portfolio summary."""
        assets = await self.get_all_nfts(owner)
        collections = await self.get_collections_by_owner(owner)

        return {
            "total_nfts": len(assets),
            "total_collections": len(collections),
            "collections": collections[:10],  # Top 10 by count
            "recent_acquisitions": sorted(
                assets,
                key=lambda x: x.get("ownership", {}).get("updateTime", ""),
                reverse=True,
            )[:5],
        }

    # ── Cleanup ──────────────────────────────────────

    async def close(self):
        await self._client.close()