"""Tests for src/nft/ — NFT manager, marketplace, minter, whitelist, utils."""

import pytest
from unittest.mock import MagicMock, patch

from src.nft import (
    NFTManager,
    NFTMarketplace,
    NFTMinter,
    WhitelistManager,
    WhitelistEntry,
    WhitelistResult,
    NFTConfig,
    NFTCollection,
    NFTItem,
    NFTListing,
    MintResult,
    NFTStandard,
    calculate_rarity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_collection(**overrides):
    defaults = dict(
        address="0xABC", name="TestNFT", symbol="TNFT",
        total_supply=10000, floor_price_eth=0.5, chain="ethereum",
    )
    defaults.update(overrides)
    return NFTCollection(**defaults)


def _sample_item(**overrides):
    defaults = dict(
        contract="0xABC", token_id="1", name="TestNFT #1",
        image_url="https://example.com/1.png",
        attributes=[{"trait_type": "Background", "value": "Blue"}],
    )
    defaults.update(overrides)
    return NFTItem(**defaults)


def _sample_listing(**overrides):
    defaults = dict(
        contract="0xABC", token_id="1", marketplace="opensea",
        price=0.5, currency="ETH", seller="0xSeller",
    )
    defaults.update(overrides)
    return NFTListing(**defaults)


# ===========================================================================
# Enums & constants
# ===========================================================================

class TestNFTStandard:
    def test_erc721(self):
        assert NFTStandard.ERC721.value == "ERC721"

    def test_erc1155(self):
        assert NFTStandard.ERC1155.value == "ERC1155"


class TestNFTConfig:
    def test_defaults(self):
        config = NFTConfig()
        assert config.chain == "ethereum"
        assert config.max_gas_gwei == 100
        assert config.slippage_percent == 5.0
        assert config.opensea_api_key == ""

    def test_custom(self):
        config = NFTConfig(chain="base", opensea_api_key="key123")
        assert config.chain == "base"
        assert config.opensea_api_key == "key123"


# ===========================================================================
# Data classes
# ===========================================================================

class TestNFTCollection:
    def test_fields(self):
        col = _sample_collection()
        assert col.address == "0xABC"
        assert col.name == "TestNFT"
        assert col.floor_price_eth == 0.5

    def test_to_dict(self):
        col = _sample_collection()
        d = col.to_dict()
        assert d["address"] == "0xABC"
        assert d["name"] == "TestNFT"
        assert "standard" in d


class TestNFTItem:
    def test_fields(self):
        item = _sample_item()
        assert item.contract == "0xABC"
        assert item.token_id == "1"
        assert item.name == "TestNFT #1"

    def test_opensea_url(self):
        item = _sample_item(contract="0xABC", token_id="42")
        assert "0xABC/42" in item.opensea_url
        assert "opensea.io" in item.opensea_url

    def test_to_dict(self):
        item = _sample_item()
        d = item.to_dict()
        assert d["contract"] == "0xABC"
        assert d["token_id"] == "1"

    def test_default_standard(self):
        item = _sample_item()
        assert item.standard == NFTStandard.ERC721


class TestNFTListing:
    def test_fields(self):
        listing = _sample_listing()
        assert listing.price == 0.5
        assert listing.marketplace == "opensea"

    def test_to_dict(self):
        listing = _sample_listing()
        d = listing.to_dict()
        assert d["contract"] == "0xABC"
        assert d["price"] == 0.5


class TestMintResult:
    def test_fields(self):
        mr = MintResult(contract="0xABC", token_id="1", tx_hash="0xtx", success=True)
        assert mr.success is True
        assert mr.error == ""

    def test_to_dict(self):
        mr = MintResult(contract="0xABC", success=False)
        d = mr.to_dict()
        assert d["success"] is False


# ===========================================================================
# calculate_rarity
# ===========================================================================

class TestCalculateRarity:
    def test_empty_list(self):
        assert calculate_rarity([]) == []

    def test_single_nft(self):
        items = [_sample_item(attributes=[{"trait_type": "Hat", "value": "Crown"}])]
        result = calculate_rarity(items)
        assert len(result) == 1
        assert result[0].rarity_rank == 1

    def test_rarity_scores_assigned(self):
        items = [
            _sample_item(token_id="1", attributes=[
                {"trait_type": "Bg", "value": "Red"},    # unique
                {"trait_type": "Hat", "value": "Crown"}, # rare
            ]),
            _sample_item(token_id="2", attributes=[
                {"trait_type": "Bg", "value": "Blue"},   # common
                {"trait_type": "Hat", "value": "Cap"},   # common
            ]),
            _sample_item(token_id="3", attributes=[
                {"trait_type": "Bg", "value": "Blue"},   # common
                {"trait_type": "Hat", "value": "Crown"}, # rare
            ]),
        ]
        result = calculate_rarity(items)
        # Item 1 has the most unique traits -> highest score
        assert result[0].rarity_rank == 1
        assert result[0].rarity_score >= result[-1].rarity_score

    def test_sorted_by_score_desc(self):
        items = [
            _sample_item(token_id=str(i), attributes=[
                {"trait_type": "Bg", "value": "Red" if i < 2 else "Blue"},
            ])
            for i in range(5)
        ]
        result = calculate_rarity(items)
        for i in range(len(result) - 1):
            assert result[i].rarity_score >= result[i+1].rarity_score

    def test_ranks_sequential(self):
        items = [_sample_item(token_id=str(i)) for i in range(3)]
        result = calculate_rarity(items)
        ranks = [n.rarity_rank for n in result]
        assert sorted(ranks) == [1, 2, 3]


# ===========================================================================
# WhitelistManager
# ===========================================================================

class TestWhitelistManager:
    def test_add_and_check(self):
        wl = WhitelistManager()
        assert wl.add("0xABC") is True
        result = wl.check("0xABC")
        assert result.is_whitelisted is True
        assert result.max_mint == 1

    def test_add_duplicate(self):
        wl = WhitelistManager()
        assert wl.add("0xABC") is True
        assert wl.add("0xABC") is False

    def test_check_not_whitelisted(self):
        wl = WhitelistManager()
        result = wl.check("0xUnknown")
        assert result.is_whitelisted is False
        assert "not on whitelist" in result.message.lower()

    def test_remove(self):
        wl = WhitelistManager()
        wl.add("0xABC")
        assert wl.remove("0xABC") is True
        assert wl.check("0xABC").is_whitelisted is False

    def test_remove_nonexistent(self):
        wl = WhitelistManager()
        assert wl.remove("0xNope") is False

    def test_mark_used(self):
        wl = WhitelistManager()
        wl.add("0xABC")
        assert wl.mark_used("0xABC") is True
        result = wl.check("0xABC")
        assert result.is_whitelisted is False
        assert "already used" in result.message.lower()

    def test_mark_used_not_found(self):
        wl = WhitelistManager()
        assert wl.mark_used("0xNope") is False

    def test_bulk_add(self):
        wl = WhitelistManager()
        count = wl.bulk_add(["0xA", "0xB", "0xC"], max_mint=3, tier="og")
        assert count == 3
        assert len(wl.get_all()) == 3

    def test_bulk_add_with_duplicates(self):
        wl = WhitelistManager()
        wl.add("0xA")
        count = wl.bulk_add(["0xA", "0xB"])
        assert count == 1

    def test_clear(self):
        wl = WhitelistManager()
        wl.add("0xA")
        wl.add("0xB")
        assert wl.clear() == 2
        assert len(wl.get_all()) == 0

    def test_case_insensitive(self):
        wl = WhitelistManager()
        wl.add("0xABC")
        result = wl.check("0xabc")
        assert result.is_whitelisted is True

    def test_tier_and_max_mint(self):
        wl = WhitelistManager()
        wl.add("0xABC", max_mint=5, tier="og")
        result = wl.check("0xABC")
        assert result.max_mint == 5
        assert result.tier == "og"


# ===========================================================================
# NFTMinter
# ===========================================================================

class TestNFTMinter:
    def test_mint_placeholder(self):
        minter = NFTMinter(NFTConfig())
        result = minter.mint("0xContract", quantity=1)
        assert isinstance(result, MintResult)
        assert result.error != ""  # placeholder says requires web3

    def test_batch_mint(self):
        minter = NFTMinter(NFTConfig())
        results = minter.batch_mint("0xContract", quantity=3)
        assert len(results) == 3
        for r in results:
            assert isinstance(r, MintResult)


# ===========================================================================
# NFTMarketplace
# ===========================================================================

class TestNFTMarketplace:
    def test_init(self):
        mp = NFTMarketplace(NFTConfig(chain="ethereum"))
        assert mp.config.chain == "ethereum"

    def test_get_collection_api_key_set(self):
        mp = NFTMarketplace(NFTConfig(opensea_api_key="mykey"))
        assert mp.session.headers.get("X-API-KEY") == "mykey"

    @patch("src.nft.marketplace.requests.Session.get")
    def test_get_collection_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "name": "TestCol", "symbol": "TC",
            "total_supply": 5000,
            "floor_price": {"value": 1e18},
            "description": "A test collection",
            "image_url": "https://img.png",
            "safelist_request_status": "verified",
        }
        mock_get.return_value = mock_resp

        mp = NFTMarketplace(NFTConfig())
        col = mp.get_collection("0xABC")
        assert col is not None
        assert col.name == "TestCol"
        assert col.floor_price_eth == 1.0
        assert col.verified is True

    @patch("src.nft.marketplace.requests.Session.get")
    def test_get_collection_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        mp = NFTMarketplace(NFTConfig())
        col = mp.get_collection("0xABC")
        assert col is None

    @patch("src.nft.marketplace.requests.Session.get")
    def test_get_collection_request_error(self, mock_get):
        mock_get.side_effect = ConnectionError("timeout")
        mp = NFTMarketplace(NFTConfig())
        col = mp.get_collection("0xABC")
        assert col is None

    @patch("src.nft.marketplace.requests.Session.get")
    def test_get_wallet_nfts_with_alchemy(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ownedNfts": [{
                "contract": {"address": "0xNFT"},
                "tokenId": "42",
                "metadata": {
                    "name": "Cool NFT",
                    "description": "desc",
                    "image": "https://img.png",
                    "attributes": [{"trait_type": "Bg", "value": "Red"}],
                },
            }]
        }
        mock_get.return_value = mock_resp

        mp = NFTMarketplace(NFTConfig(alchemy_api_key="akey"))
        nfts = mp.get_wallet_nfts("0xOwner")
        assert len(nfts) == 1
        assert nfts[0].name == "Cool NFT"
        assert nfts[0].token_id == "42"

    @patch("src.nft.marketplace.requests.Session.get")
    def test_get_wallet_nfts_no_alchemy_key(self, mock_get):
        mp = NFTMarketplace(NFTConfig())
        nfts = mp.get_wallet_nfts("0xOwner")
        assert nfts == []

    @patch("src.nft.marketplace.requests.Session.get")
    def test_get_floor_price(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "name": "Col", "symbol": "C", "total_supply": 100,
            "floor_price": {"value": 2e18},
            "safelist_request_status": "verified",
        }
        mock_get.return_value = mock_resp

        mp = NFTMarketplace(NFTConfig())
        price = mp.get_floor_price("0xABC")
        assert price == 2.0

    @patch("src.nft.marketplace.requests.Session.get")
    def test_get_floor_price_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        mp = NFTMarketplace(NFTConfig())
        price = mp.get_floor_price("0xABC")
        assert price == 0.0

    @patch("src.nft.marketplace.requests.Session.get")
    def test_get_listings(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "listings": [{
                "token_id": "1",
                "price": {"value": 5e17, "currency": "ETH"},
                "seller": "0xSeller",
                "url": "https://opensea.io/1",
            }]
        }
        mock_get.return_value = mock_resp

        mp = NFTMarketplace(NFTConfig())
        listings = mp.get_listings("0xABC")
        assert len(listings) == 1
        assert listings[0].price == 0.5

    @patch("src.nft.marketplace.requests.Session.get")
    def test_get_trending(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "collections": [{
                "address": "0xCOL",
                "name": "Trending NFT",
                "floor_price": {"value": 1e18},
                "volume": 500,
            }]
        }
        mock_get.return_value = mock_resp

        mp = NFTMarketplace(NFTConfig())
        trending = mp.get_trending()
        assert len(trending) == 1
        assert trending[0].name == "Trending NFT"

    @patch("src.nft.marketplace.requests.Session.get")
    def test_search_collections(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [{
                "address": "0xCOL",
                "name": "Found NFT",
                "floor_price": {"value": 3e17},
            }]
        }
        mock_get.return_value = mock_resp

        mp = NFTMarketplace(NFTConfig())
        results = mp.search_collections("cool nft")
        assert len(results) == 1
        assert results[0].name == "Found NFT"


# ===========================================================================
# NFTManager
# ===========================================================================

class TestNFTManager:
    def test_init(self):
        nm = NFTManager(NFTConfig(chain="ethereum"))
        assert nm.config.chain == "ethereum"
        assert nm.marketplace is not None
        assert nm.minter is not None
        assert nm.whitelist is not None

    def test_init_with_api_key(self):
        nm = NFTManager(NFTConfig(opensea_api_key="testkey"))
        assert nm.session.headers.get("X-API-KEY") == "testkey"

    @patch("src.nft.marketplace.requests.Session.get")
    def test_delegates_get_collection(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "name": "Delegated", "symbol": "DEL", "total_supply": 100,
            "floor_price": {"value": 1e18},
        }
        mock_get.return_value = mock_resp

        nm = NFTManager(NFTConfig())
        col = nm.get_collection("0xABC")
        assert col is not None
        assert col.name == "Delegated"

    def test_delegates_mint(self):
        nm = NFTManager(NFTConfig())
        result = nm.mint("0xContract")
        assert isinstance(result, MintResult)

    def test_delegates_calculate_rarity(self):
        nm = NFTManager(NFTConfig())
        items = [_sample_item(token_id=str(i)) for i in range(3)]
        result = nm.calculate_rarity(items)
        assert len(result) == 3
        assert result[0].rarity_rank == 1
