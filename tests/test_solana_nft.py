"""Tests for Solana NFT (Metaplex DAS) module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from web3_agent_kit.solana.nft import SolanaNFT, SolanaNFTConfig
from web3_agent_kit.solana.client import SolanaClientConfig


@pytest.fixture
def nft():
    return SolanaNFT(SolanaNFTConfig(helius_api_key="test-key"))


class TestSolanaNFTConfig:
    def test_default_config(self):
        config = SolanaNFTConfig()
        assert config.helius_api_key is None

    def test_custom_config(self):
        config = SolanaNFTConfig(helius_api_key="test-helius-key")
        assert config.helius_api_key == "test-helius-key"


class TestSolanaNFT:
    def test_init(self, nft):
        assert nft.config.helius_api_key == "test-key"
        assert "helius-rpc.com" in nft._das_url

    def test_init_no_helius(self):
        nft2 = SolanaNFT()
        assert "mainnet-beta.solana.com" in nft2._das_url

    @pytest.mark.asyncio
    async def test_get_nfts_by_owner(self, nft):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {
                "total": 2,
                "limit": 100,
                "page": 1,
                "items": [
                    {
                        "id": "asset_1",
                        "content": {
                            "metadata": {"name": "NFT #1", "symbol": "TEST"},
                            "links": {"image": "https://example.com/1.png"},
                        },
                        "ownership": {"owner": "owner_address"},
                    },
                    {
                        "id": "asset_2",
                        "content": {
                            "metadata": {"name": "NFT #2", "symbol": "TEST"},
                            "links": {"image": "https://example.com/2.png"},
                        },
                        "ownership": {"owner": "owner_address"},
                    },
                ],
            }
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            result = await nft.get_nfts_by_owner("owner_address")
            assert result["total"] == 2
            assert len(result["items"]) == 2
            assert result["items"][0]["id"] == "asset_1"

    @pytest.mark.asyncio
    async def test_get_all_nfts(self, nft):
        """Test pagination — first page has items, second is empty."""
        mock_page1 = MagicMock()
        mock_page1.json.return_value = {
            "result": {
                "total": 3,
                "limit": 1000,
                "page": 1,
                "items": [
                    {"id": "asset_1"},
                    {"id": "asset_2"},
                    {"id": "asset_3"},
                ],
            }
        }
        mock_page1.raise_for_status = MagicMock()

        mock_page2 = MagicMock()
        mock_page2.json.return_value = {
            "result": {"total": 3, "limit": 1000, "page": 2, "items": []}
        }
        mock_page2.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(side_effect=[mock_page1, mock_page2])):
            items = await nft.get_all_nfts("owner_address")
            assert len(items) == 3

    @pytest.mark.asyncio
    async def test_get_asset(self, nft):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {
                "id": "asset_1",
                "content": {
                    "metadata": {
                        "name": "Cool NFT",
                        "symbol": "COOL",
                        "description": "A very cool NFT",
                    },
                    "links": {"image": "https://example.com/cool.png"},
                },
                "ownership": {"owner": "owner_address", "frozen": False},
                "creators": [{"address": "creator_1", "share": 100}],
                "royalty": {"royalty_model": "creators", "basis_points": 500},
            }
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            asset = await nft.get_asset("asset_1")
            assert asset["id"] == "asset_1"
            assert asset["content"]["metadata"]["name"] == "Cool NFT"

    @pytest.mark.asyncio
    async def test_get_assets_batch(self, nft):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": [
                {"id": "asset_1", "content": {"metadata": {"name": "NFT #1"}}},
                {"id": "asset_2", "content": {"metadata": {"name": "NFT #2"}}},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            assets = await nft.get_assets_batch(["asset_1", "asset_2"])
            assert len(assets) == 2

    @pytest.mark.asyncio
    async def test_search_assets(self, nft):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {
                "total": 1,
                "items": [{"id": "asset_1", "grouping": []}],
            }
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            result = await nft.search_assets("owner_address")
            assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_search_assets_with_grouping(self, nft):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "result": {
                "total": 1,
                "items": [{"id": "asset_1", "grouping": []}],
            }
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_resp)):
            result = await nft.search_assets(
                "owner_address",
                grouping=("collection", "collection_address"),
                sort_by={"sortBy": "created", "sortDirection": "asc"},
            )
            assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_get_collections_by_owner(self, nft):
        """Test collection grouping logic."""
        # Mock get_all_nfts to return 2 collections
        with patch.object(nft, "get_all_nfts", AsyncMock(return_value=[
            {
                "id": "asset_1",
                "grouping": [
                    {"group_key": "collection", "group_value": "Cool Cats"},
                ],
                "content": {"links": {"image": "https://cats.png"}},
            },
            {
                "id": "asset_2",
                "grouping": [
                    {"group_key": "collection", "group_value": "Cool Cats"},
                ],
                "content": {"links": {"image": "https://cats.png"}},
            },
            {
                "id": "asset_3",
                "grouping": [
                    {"group_key": "collection", "group_value": "Bored Dogs"},
                ],
                "content": {"links": {"image": "https://dogs.png"}},
            },
        ])):
            collections = await nft.get_collections_by_owner("owner")
            assert len(collections) == 2
            # Cool Cats should be first (count=2 > count=1)
            assert collections[0]["name"] == "Cool Cats"
            assert collections[0]["count"] == 2
            assert collections[1]["name"] == "Bored Dogs"
            assert collections[1]["count"] == 1

    @pytest.mark.asyncio
    async def test_get_collections_by_owner_empty(self, nft):
        with patch.object(nft, "get_all_nfts", AsyncMock(return_value=[])):
            collections = await nft.get_collections_by_owner("empty_owner")
            assert collections == []

    @pytest.mark.asyncio
    async def test_get_portfolio_summary(self, nft):
        with patch.object(nft, "get_all_nfts", AsyncMock(return_value=[
            {
                "id": "asset_1",
                "grouping": [{"group_key": "collection", "group_value": "Test Collection"}],
                "content": {"links": {"image": "https://example.com/1.png"}},
                "ownership": {"updateTime": "2026-01-15T10:00:00Z"},
            },
            {
                "id": "asset_2",
                "grouping": [{"group_key": "collection", "group_value": "Test Collection"}],
                "content": {"links": {"image": "https://example.com/2.png"}},
                "ownership": {"updateTime": "2026-01-20T12:00:00Z"},
            },
        ])):
            summary = await nft.get_portfolio_summary("owner")
            assert summary["total_nfts"] == 2
            assert summary["total_collections"] == 1
            assert len(summary["collections"]) == 1
            assert len(summary["recent_acquisitions"]) == 2
            # Most recent first
            assert summary["recent_acquisitions"][0]["id"] == "asset_2"

    @pytest.mark.asyncio
    async def test_close(self, nft):
        mock_client = AsyncMock()
        nft._client._client = mock_client
        await nft.close()
        mock_client.aclose.assert_called_once()